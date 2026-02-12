from datetime import date

from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from users.models import Profile, Upload
from bookings.models import Engagement

from .serializers import (
    MeProfileSerializer,
    GlobalFeedProfileSerializer,
    PublicProfileDetailSerializer,
    UploadSerializer,
)


# -------------------------------------------------------------------
# AUTH (Token) — required for Expo. Leanest solution: DRF authtoken.
# -------------------------------------------------------------------

class TokenLoginAPIView(APIView):
    permission_classes = [AllowAny]

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

    def post(self, request):
        """
        POST /api/auth/logout/
        Deletes the token so the mobile client is effectively logged out.
        """
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Logged out."})


class TokenMeAPIView(APIView):
    permission_classes = [IsAuthenticated]

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
        profile = Profile.objects.get(user=self.request.user)
        qs = Upload.objects.filter(profile=profile).order_by("-upload_date")

        if profile.profile_picture:
            qs = qs.exclude(image=profile.profile_picture.name)

        return qs

    def perform_create(self, serializer):
        profile = Profile.objects.get(user=self.request.user)
        serializer.save(profile=profile)


class MyUploadDeleteAPIView(generics.DestroyAPIView):
    """
    DELETE /api/users/me/uploads/<upload_id>/
    Strictly scoped: user can delete only their own uploads.
    """
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "upload_id"

    def get_queryset(self):
        return Upload.objects.filter(profile__user=self.request.user)


class GlobalFeedAPIView(_LenientPaginatorMixin, generics.GenericAPIView):
    """
    GET /api/users/feed/?professions=A&professions=B&page=1

    Mirrors users.views.global_feed:
    - exclude request.user
    - filter by ProfessionFilterForm's MultipleChoice field 'professions'
    - pagination 20/page
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GlobalFeedProfileSerializer

    def get(self, request):
        qs = (
            Profile.objects
            .exclude(user=request.user)
            .select_related("user")
            .only("user__id", "user__username", "profession", "profile_picture", "is_performer")
        )

        professions = [p for p in request.query_params.getlist("profession") if p]
        if professions:
            qs = qs.filter(profession__in=professions)

        paginator, page_obj = self.paginate_lenient(qs, request)
        ser = self.get_serializer(page_obj.object_list, many=True, context={"request": request})

        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "results": ser.data,
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


class ProfessionsAPIView(APIView):
    """
    GET /api/users/professions/
    Helps frontend build the same filter options as your ProfessionFilterForm.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        professions = (
            Profile.objects
            .exclude(profession__isnull=True)
            .exclude(profession__exact="")
            .values_list("profession", flat=True)
            .distinct()
            .order_by("profession")
        )
        return Response({"professions": list(professions)})


class LiveEventsAPIView(_LenientPaginatorMixin, APIView):
    """
    GET /api/users/live-events/?page=1
    Mirrors users.views.live_events: accepted upcoming engagements, paginated.
    """
    permission_classes = [IsAuthenticated]
    page_size = 10  # matches users.views.live_events page size :contentReference[oaicite:12]{index=12}

    def get(self, request):
        scope = request.query_params.get("scope", "upcoming")

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

        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "results": results,
        })
