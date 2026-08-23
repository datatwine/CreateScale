import logging

from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q, Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status, viewsets

# Aliased: EngagementViewSet has a method named `action` (its own /action/
# URL) which shadows this import for every @action-decorated method defined
# below it in the class body — Python class bodies bind names sequentially.
from rest_framework.decorators import action as drf_action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import Profile
from users.api.views import _LenientPaginatorMixin
from users.notifications import send_push_notification
from bookings.models import Engagement, Payment, Review
from bookings.services.payments import PaymentService
from .serializers import (
    EngagementSerializer,
    EngagementCreateSerializer,
    ReviewCreateSerializer,
    EngagementActionSerializer,
    PaymentHistorySerializer,
    VerifyPaymentSerializer,
    DisputeSerializer,
)

logger = logging.getLogger(__name__)


class ClientEngagementsAPIView(_LenientPaginatorMixin, APIView):
    """GET /api/bookings/engagements/client/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Engagement.objects.filter(client=request.user)
            .select_related("client", "performer")
            .annotate(
                is_already_reviewed=Exists(
                    Review.objects.filter(engagement=OuterRef("pk"), author=request.user)
                )
            )
            .order_by("date", "time")
        )
        paginator, page_obj = self.paginate_lenient(qs, request)
        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "results": EngagementSerializer(page_obj.object_list, many=True, context={"request": request}).data,
        })


class PerformerEngagementsAPIView(_LenientPaginatorMixin, APIView):
    """GET /api/bookings/engagements/performer/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Engagement.objects.filter(performer=request.user)
            .select_related("client", "performer")
            .annotate(
                is_already_reviewed=Exists(
                    Review.objects.filter(engagement=OuterRef("pk"), author=request.user)
                )
            )
            .order_by("date", "time")
        )
        paginator, page_obj = self.paginate_lenient(qs, request)
        return Response({
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "page": page_obj.number,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "results": EngagementSerializer(page_obj.object_list, many=True, context={"request": request}).data,
        })


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
            return Response(
                {"detail": "You can't hire yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Client checks (same as bookings/views.py) :contentReference[oaicite:13]{index=13}
        if not client_profile.is_potential_client:
            return Response(
                {"detail": "Enable 'I hire performers' on your profile first."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not client_profile.client_approved:
            return Response(
                {"detail": "Admin has not approved you for hiring yet."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if client_profile.client_blacklisted:
            return Response(
                {"detail": "You are currently blocked from hiring performers."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Performer checks :contentReference[oaicite:14]{index=14}
        if (
            not performer_profile.is_performer
        ) or performer_profile.performer_blacklisted:
            return Response(
                {"detail": "This user is not available for hire right now."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

        # Snapshot the performer's current fee onto this engagement so
        # later changes to the profile fee can't affect open bookings.
        engagement.fee = performer_profile.performer_fee

        # Critical: keep all business rules in Engagement.clean() :contentReference[oaicite:15]{index=15}
        try:
            engagement.full_clean()
        except ValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )

        engagement.save()
        send_push_notification(
            user=performer_profile.user,
            title="New hire request!",
            body=f"{request.user.username} wants to book you for {engagement.occasion}",
            data={"screen": "Bookings", "id": engagement.pk},
        )
        return Response(
            EngagementSerializer(engagement).data, status=status.HTTP_201_CREATED
        )


_PAID_STATUSES = [
    Engagement.PAYMENT_PAID,
    Engagement.PAYMENT_PAYOUT_PROCESSING,
    Engagement.PAYMENT_PAYOUT_FAILED,
    Engagement.PAYMENT_RELEASED,
    Engagement.PAYMENT_REFUNDED,
]


class PerformerPayoutsAPIView(_LenientPaginatorMixin, APIView):
    """
    GET /api/bookings/payouts/performer/?page=1
    Returns the authenticated performer's paid/released/refunded engagements,
    mirroring the web performer_payouts view in bookings/views.py.
    Paginated the same way as GlobalFeedAPIView/LiveEventsAPIView so a
    performer with hundreds of paid gigs doesn't serialize/transfer them
    all in one response.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Engagement.objects.filter(
                performer=request.user, payment_status__in=_PAID_STATUSES
            )
            .select_related("client", "performer")
            .order_by("-date", "-time")
        )
        paginator, page_obj = self.paginate_lenient(qs, request)
        return Response(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": PaymentHistorySerializer(
                    page_obj.object_list, many=True
                ).data,
            }
        )


class ClientPaymentsAPIView(_LenientPaginatorMixin, APIView):
    """
    GET /api/bookings/payments/client/?page=1
    Returns the authenticated client's paid/released/refunded engagements,
    mirroring the web client_payments view in bookings/views.py. Paginated
    for the same reason as PerformerPayoutsAPIView above.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Engagement.objects.filter(
                client=request.user, payment_status__in=_PAID_STATUSES
            )
            .select_related("client", "performer")
            .order_by("-paid_at")
        )
        paginator, page_obj = self.paginate_lenient(qs, request)
        return Response(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "page": page_obj.number,
                "has_next": page_obj.has_next(),
                "has_previous": page_obj.has_previous(),
                "results": PaymentHistorySerializer(
                    page_obj.object_list, many=True
                ).data,
            }
        )


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
        return (
            engagement.client_id == request.user.id
            or engagement.performer_id == request.user.id
        )

    def _get_visible_qs(self, request):
        if self._is_admin(request):
            qs = Engagement.objects.all()
        else:
            qs = Engagement.objects.filter(
                Q(client=request.user) | Q(performer=request.user)
            )
        
        return qs.select_related("client", "performer").annotate(
            is_already_reviewed=Exists(
                Review.objects.filter(engagement=OuterRef("pk"), author=request.user)
            )
        )

    def list(self, request):
        """
        GET /api/bookings/engagements/
        Returns union of engagements where user is client OR performer.
        """
        qs = self._get_visible_qs(request).order_by("date", "time")
        # Ensure pagination here if needed, but if it is just a plain ViewSet, DRF handles it if pagination is configured globally. 
        # But we'll leave it returning a raw list since mobile doesn't currently call this directly.
        return Response(EngagementSerializer(qs, many=True, context={"request": request}).data)

    def retrieve(self, request, pk=None):
        """
        GET /api/bookings/engagements/<pk>/
        Allowed for participant or admin (mirrors bookings.views.engagement_detail). :contentReference[oaicite:17]{index=17}
        """
        engagement = get_object_or_404(
            Engagement.objects.select_related("client", "performer"), pk=pk
        )
        if not (self._is_admin(request) or self._is_participant(request, engagement)):
            raise PermissionDenied("You are not allowed to view this booking.")
        return Response(EngagementSerializer(engagement).data)

    @drf_action(detail=True, methods=["post"], url_path="action")
    def action(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/action/
        Body: {"action": "...", "emergency_reason": "..."}
        Uses model methods only.
        """
        engagement = get_object_or_404(
            Engagement.objects.select_related("client", "performer"), pk=pk
        )
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
                engagement.cancel_by_client(reason=reason)
                if engagement.payment_status == Engagement.PAYMENT_PAID:
                    try:
                        PaymentService.refund_to_client(engagement)
                    except Exception as exc:
                        # Cancel already committed; the client is still told
                        # the cancel worked. Money stays in escrow until an
                        # admin reconciles the failed refund.
                        logger.exception(
                            "Refund failed for cancelled engagement %s: %s",
                            engagement.pk,
                            exc,
                        )
                        return Response(
                            {
                                "detail": "Cancelled, but the refund could not be "
                                "processed automatically. An admin will follow up."
                            }
                        )
                return Response({"detail": "Cancelled by client."})

            if action == "cancel_performer" and is_performer:
                engagement.cancel_by_performer(reason=reason)
                if engagement.payment_status == Engagement.PAYMENT_PAID:
                    try:
                        PaymentService.refund_to_client(engagement)
                    except Exception as exc:
                        logger.exception(
                            "Refund failed for cancelled engagement %s: %s",
                            engagement.pk,
                            exc,
                        )
                        return Response(
                            {
                                "detail": "Cancelled, but the refund could not be "
                                "processed automatically. An admin will follow up."
                            }
                        )
                return Response({"detail": "Cancelled by performer."})

            return Response(
                {"detail": "Invalid action for your role."},
                status=status.HTTP_403_FORBIDDEN,
            )

        except ValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )

    @drf_action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/pay/
        Step 1 of checkout: mobile posts here when the client taps "Pay Now".
        Mirrors bookings.views.create_payment_order — token auth instead of
        session auth, plus an explicit "must be accepted" gate the web view
        didn't need (Engagement.clean() enforces it via full_clean() there).
        """
        engagement = get_object_or_404(Engagement, pk=pk)
        if engagement.client_id != request.user.id:
            raise PermissionDenied
        if engagement.status != Engagement.STATUS_ACCEPTED:
            return Response(
                {"error": "Only accepted bookings can be paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order_data = PaymentService.create_order(engagement)
            return Response(order_data)
        except (ValueError, RuntimeError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @drf_action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/verify/
        Step 2 of checkout: mobile posts here after the Razorpay checkout
        succeeds. Mirrors bookings.views.verify_payment.
        """
        engagement = get_object_or_404(Engagement, pk=pk)
        if engagement.client_id != request.user.id:
            raise PermissionDenied
        ser = VerifyPaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            PaymentService.verify_and_capture(
                ser.validated_data["razorpay_order_id"],
                ser.validated_data["razorpay_payment_id"],
                ser.validated_data["razorpay_signature"],
            )
            return Response({"status": "ok"})
        except (ValueError, Payment.DoesNotExist) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @drf_action(detail=True, methods=["post"], url_path="dispute")
    def dispute(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/dispute/
        Client flags an issue against a paid engagement within the 24h
        post-event dispute window. Mirrors bookings.views.raise_dispute.
        """
        engagement = get_object_or_404(Engagement, pk=pk)
        if engagement.client_id != request.user.id:
            raise PermissionDenied
        if not engagement.can_dispute:
            return Response(
                {"error": "Dispute window is not open for this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = DisputeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        engagement.disputed_at = timezone.now()
        engagement.dispute_reason = ser.validated_data["reason"]
        engagement.save(update_fields=["disputed_at", "dispute_reason"])
        return Response(
            {
                "detail": "Issue raised. An admin will review and contact you within 24-48 hours."
            }
        )

    @drf_action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        """
        POST /api/bookings/engagements/<pk>/review/
        Allows client or performer to review the other party for a past, accepted event.
        """
        engagement = get_object_or_404(
            Engagement.objects.select_related("client", "performer"), pk=pk
        )
        if not self._is_participant(request, engagement):
            raise PermissionDenied("You are not part of this booking.")

        if engagement.status != Engagement.STATUS_ACCEPTED:
            return Response(
                {"detail": "You can only review accepted bookings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not engagement.is_past_event:
            return Response(
                {"detail": "You can only review bookings that have already happened."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Review.objects.filter(engagement=engagement, author=request.user).exists():
            return Response(
                {"detail": "You have already reviewed this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = ReviewCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        review_instance = Review(engagement=engagement, author=request.user)
        # Apply the validated data manually so that clean() can validate everything
        review_instance.rating = ser.validated_data["rating"]
        review_instance.comment = ser.validated_data["comment"]

        try:
            review_instance.clean() # populate subject and direction
            review_instance.full_clean()
        except ValidationError as e:
            # Format validation errors for DRF
            return Response(
                {"detail": " ".join(e.messages) if hasattr(e, "messages") else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review_instance.save()
        return Response(
            {"detail": "Review submitted successfully."}, status=status.HTTP_201_CREATED
        )
