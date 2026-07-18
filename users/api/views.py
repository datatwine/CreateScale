from datetime import date

from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.cache import cache_control

from django.conf import settings as django_settings

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from users.models import Profile, Upload
from bookings.models import Engagement

from .presign import generate_upload_presign
from .serializers import (
    MeProfileSerializer,
    GlobalFeedProfileSerializer,
    PublicProfileDetailSerializer,
    PresignedUploadSerializer,
    UploadSerializer,
    SignupSerializer,
    ForgotPasswordSerializer,
)


def _cached(key, timeout, compute_fn):
    """Try cache first; fall through to compute_fn on miss."""
    data = cache.get(key)
    if data is None:
        data = compute_fn()
        cache.set(key, data, timeout)
    return data


# -------------------------------------------------------------------
# AUTH (Token) — required for Expo. Leanest solution: DRF authtoken.
# -------------------------------------------------------------------

class TokenLoginAPIView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(cache_control(no_store=True))
    def post(self, request):
        """
        POST /api/auth/token/
        Body: {"username": "...", "password": "..."}
        Returns: {"token": "...", "user_id": 1, "username": "..."}
        """
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""

        if not username or not password:
            return Response({"detail": "username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_400_BAD_REQUEST)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user_id": user.id, "username": user.username})


class TokenLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_control(no_store=True))
    def post(self, request):
        """
        POST /api/auth/logout/
        Deletes the token so the mobile client is effectively logged out.
        """
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Logged out."})


class TokenMeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_control(no_store=True))
    def get(self, request):
        """
        GET /api/auth/me/
        A tiny 'who am I' endpoint used by mobile apps to confirm auth state.
        """
        profile = request.user.profile
        return Response({
            "user_id": request.user.id,
            "username": request.user.username,
            "profile": MeProfileSerializer(profile, context={"request": request}).data,
        })


class SignupAPIView(APIView):
    """
    POST /api/auth/signup/
    Body: {"username", "email", "password1", "password2", "profession"?, "location"?}
    Returns: {"token", "user_id", "username"}  (same shape as TokenLoginAPIView)

    Mirrors the web signup view in users.views.signup but returns JSON + token
    so the Expo app can auto-login immediately after registration.
    """
    permission_classes = [AllowAny]

    @method_decorator(cache_control(no_store=True))
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 with field errors on failure

        # Create User + Profile (signal-based)
        user = serializer.save()

        # Generate auth token for immediate login (exactly like TokenLoginAPIView)
        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {"token": token.key, "user_id": user.id, "username": user.username},
            status=status.HTTP_201_CREATED,
        )

class ForgotPasswordAPIView(APIView):
    """
    POST /api/auth/forgot-password/
    Body: {"email": "user@example.com"}
    Returns: 200 {"detail": "Password reset link sent to your email."}
            400 {"detail": "No account found with this email address."}
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "No account found with this email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        reset_url = request.build_absolute_uri(path)

        send_mail(
            subject="Reset your ArtKhoj password",
            message=(
                f"Hi,\n\n"
                f"You requested a password reset for your ArtKhoj account.\n\n"
                f"Click the link below to set a new password:\n"
                f"{reset_url}\n\n"
                f"This link expires in 1 hour.\n\n"
                f"If you did not request this reset, ignore this email.\n\n"
                f"Thanks,\nThe ArtKhoj team"
            ),
            html_message=(
                f"<!DOCTYPE html><html><body style='font-family:sans-serif;padding:24px;'>"
                f"<h2>Reset your ArtKhoj password</h2>"
                f"<p>Click the button below to set a new password. This link expires in <strong>1 hour</strong>.</p>"
                f"<a href='{reset_url}' "
                f"style='display:inline-block;background:#e68a00;color:#1F1A17;font-weight:700;"
                f"padding:14px 28px;border-radius:18px;text-decoration:none;margin:16px 0;'>"
                f"Set new password</a>"
                f"<p style='color:#8C8077;font-size:13px;'>If you did not request this, ignore this email.</p>"
                f"</body></html>"
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response(
            {"detail": "Password reset link sent to your email."}
        )


# -------------------------------------------------------------------
# USERS API
# -------------------------------------------------------------------

class _LenientPaginatorMixin:
    """
    Your HTML global_feed uses paginator.get_page(), which never 404s on bad page values.
    We preserve that “won’t crash” behavior for the API too.
    """
    page_size = 20  # matches users.views.global_feed :contentReference[oaicite:11]{index=11}

    def paginate_lenient(self, queryset, request):
        page_number = request.query_params.get("page")
        paginator = Paginator(queryset, self.page_size)
        page_obj = paginator.get_page(page_number)
        return paginator, page_obj


class MeProfileAPIView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/users/me/
    Mirrors your /users/profile/ edit behavior, but JSON-based.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MeProfileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        # Ensure profile exists even if middleware changes.
        profile, _ = Profile.objects.select_related("user").get_or_create(user=self.request.user)
        return profile

    @method_decorator(cache_control(private=True, max_age=15))
    def retrieve(self, request, *args, **kwargs):
        key = f"me:{request.user.id}"

        def compute():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        return Response(_cached(key, 15, compute))

    @method_decorator(cache_control(no_store=True))
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        cache.delete(f"me:{request.user.id}")
        cache.delete(f"profile:{request.user.id}")
        return response


class PresignUploadAPIView(APIView):
    """POST /api/users/me/uploads/presign/ — returns presigned POST data for R2."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not getattr(django_settings, "USE_S3", False):
            return Response(
                {"error": "Direct upload not available in local dev (USE_S3=0)"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        content_type = request.data.get("content_type", "image/jpeg")
        allowed = ("image/jpeg", "image/png", "video/mp4")
        if content_type not in allowed:
            return Response(
                {"error": f"content_type must be one of {allowed}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = 120 * 1024 * 1024 if "video" in content_type else 25 * 1024 * 1024
        data = generate_upload_presign(request.user.id, content_type, max_bytes)
        return Response(data)


class MyUploadsAPIView(generics.ListCreateAPIView):
    """
    GET/POST /api/users/me/uploads/
    Mirrors the uploads section in users.views.profile:
    - newest first
    - hide avatar file if it exists among uploads
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UploadSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        profile = self.request.user.profile
        qs = Upload.objects.filter(profile=profile).order_by("-upload_date")

        if profile.profile_picture:
            qs = qs.exclude(image=profile.profile_picture.name)

        return qs

    @method_decorator(cache_control(private=True, max_age=30))
    def list(self, request, *args, **kwargs):
        key = f"uploads:{request.user.id}"

        def compute():
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        return Response(_cached(key, 30, compute))

    def create(self, request, *args, **kwargs):
        # --- Presigned flow: JSON body with { key, caption } ---
        if "key" in request.data and "image" not in request.FILES and "video" not in request.FILES:
            ser = PresignedUploadSerializer(data=request.data)
            ser.is_valid(raise_exception=True)

            profile = request.user.profile
            key = ser.validated_data["key"]
            caption = ser.validated_data.get("caption", "")

            upload = Upload(profile=profile, caption=caption)
            is_video = key.endswith(".mp4")

            if is_video:
                upload.video.name = key    # points django-storages at the R2 object
            else:
                upload.image.name = key    # same — no re-upload, no Pillow in save()

            upload.save()  # is_fresh_upload() returns False (name is already committed)

            cache.delete(f"uploads:{request.user.id}")
            cache.delete(f"profile:{request.user.id}")

            # Background tasks
            if is_video:
                from users.tasks import compress_upload_video
                compress_upload_video.delay(upload.id)
            else:
                from users.tasks import process_uploaded_image
                process_uploaded_image.delay(upload.id)

            out = UploadSerializer(upload, context={"request": request})
            return Response(out.data, status=status.HTTP_201_CREATED)

        # --- Legacy multipart flow (web forms, old clients) ---
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Legacy multipart path — called by super().create() above."""
        profile = self.request.user.profile
        upload = serializer.save(profile=profile)
        cache.delete(f"uploads:{self.request.user.id}")
        cache.delete(f"profile:{self.request.user.id}")
        # Background ffmpeg re-encode for videos (no-op for images).
        # If the worker is offline, the message queues in Redis silently.
        if upload.video:
            from users.tasks import compress_upload_video
            compress_upload_video.delay(upload.id)


class MyUploadDeleteAPIView(generics.UpdateAPIView, generics.DestroyAPIView):
    """
    PATCH /api/users/me/uploads/<upload_id>/  — edit caption
    DELETE /api/users/me/uploads/<upload_id>/ — delete upload
    Strictly scoped: user can only modify their own uploads.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UploadSerializer
    lookup_url_kwarg = "upload_id"

    def get_queryset(self):
        return Upload.objects.filter(profile__user=self.request.user)

    def perform_update(self, serializer):
        serializer.save()
        cache.delete(f"uploads:{self.request.user.id}")
        cache.delete(f"profile:{self.request.user.id}")

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        cache.delete(f"uploads:{self.request.user.id}")
        cache.delete(f"profile:{self.request.user.id}")


class GlobalFeedAPIView(_LenientPaginatorMixin, generics.GenericAPIView):
    """
    GET /api/users/feed/?professions=A&professions=B&page=1

    Shared cache: one Redis entry per (page, profession-filter) serves ALL users.
    Self-exclusion happens after cache retrieval — a microsecond list filter
    instead of a per-user DB query + serialization.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GlobalFeedProfileSerializer

    @method_decorator(cache_control(private=True, max_age=30))
    def get(self, request):
        profs = ",".join(sorted(request.query_params.getlist("profession", [])))
        page = request.query_params.get("page", "1")
        key = f"feed:{page}:{profs}"

        def compute():
            qs = (
                Profile.objects
                .select_related("user")
                .only("user__id", "user__username", "profession", "profile_picture", "is_performer")
            )

            professions = [p for p in request.query_params.getlist("profession") if p]
            if professions:
                qs = qs.filter(profession__in=professions)

            paginator, page_obj = self.paginate_lenient(qs, request)
            ser = self.get_serializer(page_obj.object_list, many=True, context={"request": request})

            return {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": ser.data,
            }

        data = _cached(key, 30, compute)

        # Post-cache: strip the requesting user from results
        filtered = [p for p in data["results"] if p["user_id"] != request.user.id]

        return Response({
            "count":        max(data["count"] - 1, 0),
            "num_pages":    data["num_pages"],
            "page":         data["page"],
            "has_next":     data["has_next"],
            "has_previous": data["has_previous"],
            "results":      filtered,
        })


class ProfileDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/users/profiles/<user_id>/
    Mirrors users.views.profile_detail: other user's profile + uploads.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PublicProfileDetailSerializer

    def get_object(self):
        return get_object_or_404(Profile.objects.select_related("user"), user__id=self.kwargs["user_id"])

    @method_decorator(cache_control(private=True, max_age=60))
    def retrieve(self, request, *args, **kwargs):
        user_id = self.kwargs["user_id"]
        key = f"profile:{user_id}"

        def compute():
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return serializer.data

        return Response(_cached(key, 300, compute))


class ProfessionsAPIView(APIView):
    """
    GET /api/users/professions/
    Helps frontend build the same filter options as your ProfessionFilterForm.
    Cached for 5 minutes — profession list changes very rarely.
    """
    permission_classes = [IsAuthenticated]

    @method_decorator(cache_control(private=True, max_age=300))
    def get(self, request):
        def compute():
            return list(
                Profile.objects
                .exclude(profession__isnull=True)
                .exclude(profession__exact="")
                .values_list("profession", flat=True)
                .distinct()
                .order_by("profession")
            )

        return Response({"professions": _cached("professions", 300, compute)})


class LiveEventsAPIView(_LenientPaginatorMixin, APIView):
    """
    GET /api/users/live-events/?page=1
    Mirrors users.views.live_events: accepted upcoming engagements, paginated.
    """
    permission_classes = [IsAuthenticated]
    page_size = 10  # matches users.views.live_events page size

    @method_decorator(cache_control(private=True, max_age=30))
    def get(self, request):
        scope = request.query_params.get("scope", "upcoming")
        page = request.query_params.get("page", "1")
        key = f"events:{scope}:{page}"

        def compute():
            if scope == "past":
                # Past accepted events, newest first
                qs = (
                    Engagement.objects.filter(
                        status=Engagement.STATUS_ACCEPTED,
                        date__lt=date.today(),
                    )
                    .select_related("client", "performer")
                    .order_by("-date", "-time")
                )
            else:
                # Default: upcoming accepted events, soonest first
                qs = (
                    Engagement.objects.filter(
                        status=Engagement.STATUS_ACCEPTED,
                        date__gte=date.today(),
                    )
                    .select_related("client", "performer")
                    .order_by("date", "time")
                )

            paginator, page_obj = self.paginate_lenient(qs, request)

            results = [{
                "id": e.id,
                "date": e.date,
                "time": e.time,
                "venue": e.venue,
                "occasion": e.occasion,
                "status": e.status,
                "client": {"id": e.client.id, "username": e.client.username},
                "performer": {"id": e.performer.id, "username": e.performer.username},
            } for e in page_obj.object_list]

            return {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": results,
            }

        return Response(_cached(key, 30, compute))
