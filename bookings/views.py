import json
import logging
from django.shortcuts import render

# Create your views here.
# appointment/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.views.decorators.http import require_POST

from users.models import Profile
from users.notifications import send_push_notification
from .forms import EngagementRequestForm, CancelEngagementForm, DisputeForm, ReviewForm
from .models import Engagement, Payment, Review
from .services.payments import PaymentService

logger = logging.getLogger(__name__)


@login_required
def create_hire_request(request, performer_id):
    """
    Entry point from a performer's profile (Rule 5).
    Creates a pending Engagement if the client and performer are allowed.
    """
    performer_profile = get_object_or_404(Profile, user_id=performer_id)
    client_profile = request.user.profile

    if request.user == performer_profile.user:
        messages.error(request, "You can't hire yourself.")
        return redirect("profile-detail", user_id=performer_profile.user.id)

    # Client role checks (2, 3, 4, 15)
    if not client_profile.is_potential_client:
        messages.error(
            request,
            "Turn on the 'I hire performers' toggle on your profile before sending requests.",
        )
        return redirect("profile")

    if not client_profile.client_approved:
        messages.error(request, "Admin has not approved you for hiring performers yet.")
        return redirect("profile")

    if client_profile.client_blacklisted:
        messages.error(request, "You are currently blocked from hiring performers.")
        return redirect("profile")

    # Performer checks (2, 15)
    if not performer_profile.is_performer or performer_profile.performer_blacklisted:
        messages.error(request, "This user is not available for hire right now.")
        return redirect("profile-detail", user_id=performer_profile.user.id)

    # Stats for the hire-card footer — cached 5 min (slowly-changing data).
    stats = cache.get("hire_form:stats")
    if stats is None:
        stats = {
            "total_events": Engagement.objects.filter(
                status=Engagement.STATUS_ACCEPTED
            ).count(),
            "total_artists": Profile.objects.filter(is_performer=True).count(),
            "total_artforms": (
                Profile.objects.filter(is_performer=True)
                .exclude(profession="")
                .values("profession")
                .distinct()
                .count()
            ),
        }
        cache.set("hire_form:stats", stats, 300)

    if request.method == "POST":
        form = EngagementRequestForm(request.POST)
        if form.is_valid():
            engagement = form.save(commit=False)

            # Attach client & performer BEFORE running model validation
            engagement.client = request.user
            engagement.performer = performer_profile.user

            # Snapshot the performer's current fee onto this engagement so
            # later changes to the profile fee can't affect open bookings.
            # Falls back to None if the performer hasn't set a fee yet —
            # the engagement is still legal, it just can't be paid until
            # the performer sets a fee (the Pay button won't render).
            engagement.fee = performer_profile.performer_fee

            try:
                engagement.full_clean()  # runs model.clean()
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
                return render(
                    request,
                    "bookings/hire_form.html",
                    {"form": form, "performer_profile": performer_profile, **stats},
                )

            engagement.save()
            send_push_notification(
                user=performer_profile.user,
                title="New hire request!",
                body=f"{request.user.username} wants to book you for {engagement.occasion}",
                data={"screen": "Bookings", "id": engagement.pk},
            )
            messages.success(request, "Hiring request sent.")
            return redirect("bookings:client-engagements")
    else:
        form = EngagementRequestForm()

    return render(
        request,
        "bookings/hire_form.html",
        {"form": form, "performer_profile": performer_profile, **stats},
    )


# Maps Engagement.status → (CSS class, human label, front-end filter bucket).
# Used by client_engagement_list to annotate each object for the template.
_STATUS_DISPLAY = {
    Engagement.STATUS_ACCEPTED: ("status-accepted", "Accepted", "accepted"),
    Engagement.STATUS_PENDING: ("status-pending", "Pending", "pending"),
    Engagement.STATUS_DECLINED: ("status-declined", "Declined", "other"),
    Engagement.STATUS_AUTO_EXPIRED: ("status-expired", "Expired", "other"),
    Engagement.STATUS_CANCELLED_CLIENT: ("status-cancelled", "Cancelled", "other"),
    Engagement.STATUS_CANCELLED_PERFORMER: ("status-cancelled", "Cancelled", "other"),
}

_STATUS_FALLBACK = ("status-cancelled", "Cancelled", "other")


@login_required
def client_engagement_list(request):
    """
    Client dashboard — card-based view with front-end status filtering.
    (Rule 16)
    """
    engagements = list(
        Engagement.objects.filter(client=request.user).select_related("performer")
    )

    # Annotate each engagement with display metadata so the template
    # can render badge classes and filter-bucket data-attributes directly.
    for e in engagements:
        cls, lbl, bucket = _STATUS_DISPLAY.get(e.status, _STATUS_FALLBACK)
        e.badge_class = cls
        e.badge_label = lbl
        e.filter_bucket = bucket

    return render(
        request,
        "bookings/client_engagements.html",
        {"engagements": engagements},
    )


@login_required
def performer_engagement_list(request):
    """
    Performer dashboard — card-based view with front-end status filtering,
    action pill for pending count, and "Respond within 24h" urgency badges.
    (Rule 17)
    """
    engagements = list(
        Engagement.objects.filter(performer=request.user).select_related("client")
    )

    # Annotate each engagement with display metadata (reuses _STATUS_DISPLAY).
    # Also sets is_pending / is_inactive for performer-specific UI elements.
    for e in engagements:
        cls, lbl, bucket = _STATUS_DISPLAY.get(e.status, _STATUS_FALLBACK)
        e.badge_class = cls
        e.badge_label = lbl
        e.filter_bucket = bucket
        e.is_pending = bucket == "pending"
        e.is_inactive = bucket == "other"

    return render(
        request,
        "bookings/performer_engagements.html",
        {"engagements": engagements},
    )


@login_required
def engagement_detail(request, pk):
    """
    Single engagement screen where BOTH sides can accept/decline/cancel.
    Enforces 24h rules + emergency reasons (9, 10, 11).
    """
    engagement = get_object_or_404(Engagement, pk=pk)

    is_client = engagement.client == request.user
    is_performer = engagement.performer == request.user
    is_admin = request.user.is_superuser

    if not (is_client or is_performer or is_admin):
        raise PermissionDenied("You are not allowed to view this booking.")

    if request.method == "POST":
        action = request.POST.get("action")
        # CancelEngagementForm enforces a mandatory 10-500 char reason for
        # both cancel paths. The model layer re-validates as defense-in-depth.
        cancel_form = CancelEngagementForm(request.POST)

        try:
            if action == "accept" and is_performer:
                engagement.accept()
                messages.success(request, "You accepted this booking.")
            elif action == "decline" and is_performer:
                engagement.decline()
                messages.success(request, "You declined this booking.")
            elif action == "cancel_client" and is_client:
                if cancel_form.is_valid():
                    engagement.cancel_by_client(
                        reason=cancel_form.cleaned_data["cancellation_reason"]
                    )
                    # If money was already in escrow, trigger the Razorpay
                    # refund right here. refund_to_client is idempotent and
                    # a no-op when payment_status != PAID, so this is safe
                    # even though we just changed engagement.status above.
                    if engagement.payment_status == Engagement.PAYMENT_PAID:
                        try:
                            PaymentService.refund_to_client(engagement)
                            messages.success(
                                request, "Booking cancelled. Refund initiated."
                            )
                        except Exception as exc:
                            # Cancel already committed; don't 500 the page.
                            # Money stays in escrow until admin reconciles.
                            logger.exception(
                                "Refund failed for cancelled engagement %s: %s",
                                engagement.pk,
                                exc,
                            )
                            messages.error(
                                request,
                                "Booking cancelled, but the refund could not be "
                                "processed automatically. Our team will follow up.",
                            )
                    else:
                        messages.success(request, "Booking cancelled.")
                else:
                    messages.error(
                        request,
                        "A cancellation reason of at least 10 characters is required.",
                    )
            elif action == "cancel_performer" and is_performer:
                if cancel_form.is_valid():
                    engagement.cancel_by_performer(
                        reason=cancel_form.cleaned_data["cancellation_reason"]
                    )
                    if engagement.payment_status == Engagement.PAYMENT_PAID:
                        try:
                            PaymentService.refund_to_client(engagement)
                            messages.success(
                                request, "Booking cancelled. Client will be refunded."
                            )
                        except Exception as exc:
                            logger.exception(
                                "Refund failed for cancelled engagement %s: %s",
                                engagement.pk,
                                exc,
                            )
                            messages.error(
                                request,
                                "Booking cancelled, but the refund could not be "
                                "processed automatically. Our team will follow up.",
                            )
                    else:
                        messages.success(request, "Booking cancelled.")
                else:
                    messages.error(
                        request,
                        "A cancellation reason of at least 10 characters is required.",
                    )
            else:
                messages.error(request, "Invalid action.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))

        if is_client:
            return redirect("bookings:client-engagements")
        if is_performer:
            return redirect("bookings:performer-engagements")
        return redirect("admin:index")

    else:
        cancel_form = CancelEngagementForm()

    # Has THIS user already reviewed THIS booking? (index-served by the unique
    # constraint; one cheap query on a detail page — not a list, so no N+1.)
    already_reviewed = Review.objects.filter(
        engagement=engagement, author=request.user,
    ).exists()
    # Show the "Leave a review" button only when all four hold: the viewer is a
    # party to the booking, it was accepted, the event is over, and they haven't
    # reviewed yet. Same gates the model enforces — this just decides UI.
    can_review = (
        (is_client or is_performer)
        and engagement.status == Engagement.STATUS_ACCEPTED
        and engagement.is_past_event
        and not already_reviewed
    )

    return render(
        request,
        "bookings/engagement_detail.html",
        {
            "engagement": engagement,
            "is_client": is_client,
            "is_performer": is_performer,
            "form": cancel_form,
            "can_review": can_review,
            "already_reviewed": already_reviewed,
        },
    )


# ============================================================================
# Payment endpoints — these are called by JavaScript (checkout.js) and by
# Razorpay's server (webhook). Users never see them directly.
# ============================================================================


@login_required
@require_POST
def create_payment_order(request, pk):
    """
    Step 1 of checkout: JS posts here when the client clicks "Pay Now".
    Returns the Razorpay order_id + key_id so JS can open the modal.
    """
    engagement = get_object_or_404(Engagement, pk=pk)
    if engagement.client != request.user:
        raise PermissionDenied
    try:
        order_data = PaymentService.create_order(engagement)
        return JsonResponse(order_data)
    except (ValueError, RuntimeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def verify_payment(request, pk):
    """
    Step 2 of checkout: JS posts here AFTER the Razorpay modal succeeds.
    Body is JSON containing the order_id, payment_id, and HMAC signature
    that Razorpay returned to the browser. We verify and mark captured.
    """
    engagement = get_object_or_404(Engagement, pk=pk)
    if engagement.client != request.user:
        raise PermissionDenied
    try:
        data = json.loads(request.body)
        PaymentService.verify_and_capture(
            data["razorpay_order_id"],
            data["razorpay_payment_id"],
            data["razorpay_signature"],
        )
        return JsonResponse({"status": "ok"})
    except Payment.DoesNotExist:
        return JsonResponse({"error": "Unknown order."}, status=400)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def raise_dispute(request, pk):
    """
    Client flags an issue against a paid engagement within the 24h
    post-event dispute window. Sets disputed_at on the engagement —
    release_completed_event_payouts skips engagements with disputed_at
    set, so the money stays held until an admin acts.
    """
    engagement = get_object_or_404(Engagement, pk=pk)
    if engagement.client != request.user:
        raise PermissionDenied

    # Paid + not-already-disputed are checked first so each gets its own
    # message; the window itself is gated by Engagement.can_dispute — the
    # single source of truth the API view uses too (opens midnight after
    # the event date, per M5), so web and API can't drift apart.
    if engagement.payment_status != Engagement.PAYMENT_PAID:
        messages.error(
            request,
            "Only paid bookings can be disputed.",
        )
        return redirect("bookings:engagement-detail", pk=pk)

    if engagement.disputed_at is not None:
        messages.info(request, "You have already raised an issue on this booking.")
        return redirect("bookings:engagement-detail", pk=pk)

    if not engagement.can_dispute:
        messages.error(request, "Dispute window is not open for this booking.")
        return redirect("bookings:engagement-detail", pk=pk)

    form = DisputeForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            "Please provide a valid issue description (10-1000 chars).",
        )
        return redirect("bookings:engagement-detail", pk=pk)

    engagement.disputed_at = timezone.now()
    engagement.dispute_reason = form.cleaned_data["dispute_reason"]
    engagement.save(update_fields=["disputed_at", "dispute_reason"])
    messages.success(
        request,
        "Issue raised. An admin will review and contact you within 24-48 hours.",
    )
    return redirect("bookings:engagement-detail", pk=pk)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Backup confirmation channel — Razorpay's server posts here directly,
    so we can't use Django CSRF protection (no browser involved). HMAC
    signature verification on the raw body replaces CSRF here.

    All downstream handlers are idempotent: webhook firing twice (or
    racing with the browser callback) is harmless.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not PaymentService.verify_webhook_signature(request.body, signature):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
        PaymentService.handle_webhook_event(event)
    except (json.JSONDecodeError, KeyError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)


@csrf_exempt
@require_POST
def razorpayx_webhook(request):
    """
    RazorpayX payout webhook (payouts mode). Separate endpoint + separate secret
    from the gateway webhook — RazorpayX is configured independently in its own
    dashboard. Verifies HMAC over the raw body, then routes payout.* events.
    Idempotent downstream: safe on RazorpayX's retries.
    """
    from .services.razorpayx import verify_webhook_signature

    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_webhook_signature(request.body, signature):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
        PaymentService.handle_payout_webhook_event(event)
    except (json.JSONDecodeError, KeyError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)


@login_required
def performer_payouts(request):
    """Performer's payments dashboard — paid/released/refunded engagements."""
    engagements = (
        Engagement.objects.filter(
            performer=request.user,
            payment_status__in=[
                Engagement.PAYMENT_PAID,
                Engagement.PAYMENT_PAYOUT_PROCESSING,
                Engagement.PAYMENT_PAYOUT_FAILED,
                Engagement.PAYMENT_RELEASED,
                Engagement.PAYMENT_REFUNDED,
            ],
        )
        .select_related("client")
        .prefetch_related("payments")
        .order_by("-date", "-time")
    )
    return render(
        request,
        "bookings/performer_payouts.html",
        {"engagements": engagements},
    )


@login_required
def client_payments(request):
    """Client's payment history — paid/released/refunded engagements."""
    engagements = (
        Engagement.objects.filter(
            client=request.user,
            payment_status__in=[
                Engagement.PAYMENT_PAID,
                Engagement.PAYMENT_PAYOUT_PROCESSING,
                Engagement.PAYMENT_PAYOUT_FAILED,
                Engagement.PAYMENT_RELEASED,
                Engagement.PAYMENT_REFUNDED,
            ],
        )
        .select_related("performer")
        .prefetch_related(
            Prefetch(
                "payments",
                queryset=Payment.objects.order_by("-created_at"),
            )
        )
        .order_by("-paid_at")
    )
    # Annotate each row with its latest Payment so the template can show
    # Razorpay reference IDs without a query per row.
    for e in engagements:
        prefetched = e.payments.all()  # hits prefetch cache, no DB query
        e.latest_payment = prefetched[0] if prefetched else None
    return render(
        request,
        "bookings/client_payments.html",
        {"engagements": engagements},
    )


@login_required
def leave_review(request, pk):
    # `pk` comes from the URL (see 4c). get_object_or_404 fetches that
    # Engagement or raises a clean 404 if the id is bogus.
    engagement = get_object_or_404(Engagement, pk=pk)

    # AUTHORISATION: only the two people on this booking may review it.
    # Comparing to the related User objects; anyone else gets a 403.
    if request.user not in (engagement.client, engagement.performer):
        raise PermissionDenied("You can only review your own bookings.")

    # Already reviewed? Bounce back with a friendly note. The DB unique
    # constraint would block a duplicate anyway, but checking here lets us show
    # a nice message instead of a raw error. (This .exists() is index-served by
    # the unique constraint from §3 — cheap.)
    if Review.objects.filter(engagement=engagement, author=request.user).exists():
        messages.info(request, "You have already reviewed this booking.")
        return redirect("bookings:engagement-detail", pk=pk)

    if request.method == "POST":
        # Form was submitted → bind the posted data and validate it.
        form = ReviewForm(request.POST)
        if form.is_valid():
            # commit=False → build the Review object in memory but DON'T save
            # yet, so we can attach the fields the form deliberately omitted.
            review = form.save(commit=False)
            review.engagement = engagement
            review.author = request.user
            try:
                # model.save() calls full_clean() (§3): this is where subject +
                # direction get filled in and the accepted/past-event gates run.
                review.save()
                messages.success(request, "Thanks — your review has been submitted.")
                return redirect("bookings:engagement-detail", pk=pk)
            except ValidationError as e:
                # Model-level failure (e.g. event not over yet, or two requests
                # racing past the .exists() check above). Surface it on the form
                # with add_error(None, …) → shown as a non-field error.
                form.add_error(None, e)
    else:
        # First visit (GET) → show an empty form.
        form = ReviewForm()

    # Reached on GET, or on POST when the form was invalid (re-render with the
    # user's input + error messages intact).
    return render(request, "bookings/review_form.html", {
        "form": form,
        "engagement": engagement,
    })
