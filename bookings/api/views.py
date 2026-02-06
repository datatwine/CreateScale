from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import Profile
from bookings.models import Engagement
from .serializers import EngagementSerializer, EngagementCreateSerializer, EngagementActionSerializer


class CreateHireRequestAPIView(APIView):
    """
    POST /api/bookings/hire/<performer_id>/

    Mirrors bookings.views.create_hire_request:
    - identical gating checks using Profile flags
    - creates Engagement with client/performer
    - calls engagement.full_clean() so Engagement.clean() enforces model rules
    - saves
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, performer_id):
        performer_profile = get_object_or_404(Profile, user_id=performer_id)
        client_profile = request.user.profile

        if request.user == performer_profile.user:
            return Response({"detail": "You can't hire yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # Client checks (same as bookings/views.py) :contentReference[oaicite:13]{index=13}
        if not client_profile.is_potential_client:
            return Response({"detail": "Enable 'I hire performers' on your profile first."}, status=status.HTTP_403_FORBIDDEN)

        if not client_profile.client_approved:
            return Response({"detail": "Admin has not approved you for hiring yet."}, status=status.HTTP_403_FORBIDDEN)

        if client_profile.client_blacklisted:
            return Response({"detail": "You are currently blocked from hiring performers."}, status=status.HTTP_403_FORBIDDEN)

        # Performer checks :contentReference[oaicite:14]{index=14}
        if (not performer_profile.is_performer) or performer_profile.performer_blacklisted:
            return Response({"detail": "This user is not available for hire right now."}, status=status.HTTP_403_FORBIDDEN)

        ser = EngagementCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        engagement = Engagement(
            client=request.user,
            performer=performer_profile.user,
            date=ser.validated_data["date"],
            time=ser.validated_data["time"],
            venue=ser.validated_data["venue"],
            occasion=ser.validated_data["occasion"],
        )

        # Critical: keep all business rules in Engagement.clean() :contentReference[oaicite:15]{index=15}
        try:
            engagement.full_clean()
        except ValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        engagement.save()
        return Response(EngagementSerializer(engagement).data, status=status.HTTP_201_CREATED)


class EngagementViewSet(viewsets.ViewSet):
    """
    Dense, router-friendly endpoints for engagements.

    We intentionally do NOT provide update/delete endpoints.
    All state transitions happen via Engagement model methods:
      accept(), decline(), cancel_by_client(), cancel_by_performer()
    :contentReference[oaicite:16]{index=16}
    """
    permission_classes = [IsAuthenticated]

    def _is_admin(self, request):
        return request.user.is_superuser

    def _is_participant(self, request, engagement: Engagement):
        return engagement.client_id == request.user.id or engagement.performer_id == request.user.id

    def _get_visible_qs(self, request):
        if self._is_admin(request):
            return Engagement.objects.all().select_related("client", "performer")
        return Engagement.objects.filter(
            client=request.user
        ).select_related("client", "performer") | Engagement.objects.filter(
            performer=request.user
        ).select_related("client", "performer")

    def list(self, request):
        """
        GET /api/bookings/engagements/
        Returns union of engagements where user is client OR performer.
        """
        qs = self._get_visible_qs(request).order_by("date", "time")
        return Response(EngagementSerializer(qs, many=True).data)

    def retrieve(self, request, pk=None):
        """
        GET /api/bookings/engagements/<pk>/
        Allowed for participant or admin (mirrors bookings.views.engagement_detail). :contentReference[oaicite:17]{index=17}
        """
        engagement = get_object_or_404(Engagement.objects.select_related("client", "performer"), pk=pk)
        if not (self._is_admin(request) or self._is_participant(request, engagement)):
            raise PermissionDenied("You are not allowed to view this booking.")
        return Response(EngagementSerializer(engagement).data)

    @action(detail=False, methods=["get"], url_path="client")
    def client(self, request):
        """
        GET /api/bookings/engagements/client/
        Mirrors bookings.views.client_engagement_list. :contentReference[oaicite:18]{index=18}
        """
        qs = Engagement.objects.filter(client=request.user).select_related("client", "performer")
        return Response(EngagementSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="performer")
    def performer(self, request):
        """
        GET /api/bookings/engagements/performer/
        Mirrors bookings.views.performer_engagement_list. :contentReference[oaicite:19]{index=19}
        """
        qs = Engagement.objects.filter(performer=request.user).select_related("client", "performer")
        return Response(EngagementSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="action")
    def action(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/action/
        Body: {"action": "...", "emergency_reason": "..."}
        Uses model methods only. :contentReference[oaicite:20]{index=20}
        """
        engagement = get_object_or_404(Engagement.objects.select_related("client", "performer"), pk=pk)
        is_client = engagement.client_id == request.user.id
        is_performer = engagement.performer_id == request.user.id
        is_admin = self._is_admin(request)

        if not (is_client or is_performer or is_admin):
            raise PermissionDenied("You are not allowed to modify this booking.")

        ser = EngagementActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        action = ser.validated_data["action"]
        reason = ser.validated_data.get("emergency_reason", "")

        try:
            if action == "accept" and is_performer:
                engagement.accept()
                return Response({"detail": "Accepted."})

            if action == "decline" and is_performer:
                engagement.decline()
                return Response({"detail": "Declined."})

            if action == "cancel_client" and is_client:
                engagement.cancel_by_client(emergency_reason=reason)
                return Response({"detail": "Cancelled by client."})

            if action == "cancel_performer" and is_performer:
                engagement.cancel_by_performer(emergency_reason=reason)
                return Response({"detail": "Cancelled by performer."})

            return Response({"detail": "Invalid action for your role."}, status=status.HTTP_403_FORBIDDEN)

        except ValidationError as e:
            return Response({"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
