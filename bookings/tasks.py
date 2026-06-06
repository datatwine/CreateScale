"""
Celery tasks for time-based payment automation.

Two scheduled tasks:
  - expire_unpaid_engagements: hourly. Marks accepted engagements as
    auto_expired when the client missed the payment window. Uses
    Engagement.payment_deadline() which handles short-notice bookings.
  - release_completed_event_payouts: daily at 02:00. Unholds the Razorpay
    transfer for events that ended N hours ago (24h dispute window passed).
    Disputed engagements are explicitly skipped.

Both tasks are safe to run multiple times — every state transition is
idempotent at the model/PaymentService layer.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Engagement
from .services.payments import PaymentService

logger = logging.getLogger(__name__)


@shared_task
def expire_unpaid_engagements() -> int:
    """
    Cancel accepted engagements where the client missed the payment window.

    Returns the count of engagements marked as expired so the scheduler can
    log meaningful output. Uses Engagement.payment_deadline() per row —
    standard 24h window, clamped to event_time - 2h for short-notice
    bookings.
    """
    candidates = Engagement.objects.filter(
        status=Engagement.STATUS_ACCEPTED,
        payment_status=Engagement.PAYMENT_UNPAID,
        accepted_at__isnull=False,
    )

    now = timezone.now()
    to_expire = [
        e.pk for e in candidates
        if (d := e.payment_deadline()) and now > d
    ]

    if to_expire:
        Engagement.objects.filter(pk__in=to_expire).update(
            status=Engagement.STATUS_AUTO_EXPIRED
        )

    expired_count = len(to_expire)
    logger.info(
        "expire_unpaid_engagements: marked %d engagements as expired",
        expired_count,
    )
    return expired_count


@shared_task
def release_completed_event_payouts() -> int:
    """
    Release payouts for events that ended N hours ago. The dispute window
    (default 24h after event end) must have closed first. Disputed
    engagements are skipped entirely — they wait for admin action.
    """
    cutoff = timezone.now() - timedelta(
        hours=settings.RAZORPAY_DISPUTE_WINDOW_HOURS
    )

    ready = Engagement.objects.filter(
        status=Engagement.STATUS_ACCEPTED,
        payment_status=Engagement.PAYMENT_PAID,
        disputed_at__isnull=True,    # critical: skip disputed
    ).prefetch_related("payments")

    released_count = 0
    for e in ready:
        if e.event_datetime() < cutoff:
            try:
                PaymentService.release_to_performer(e)
                released_count += 1
            except Exception as exc:
                # Don't let one bad row stop the whole batch.
                logger.exception(
                    "Payout release failed for engagement %s: %s",
                    e.pk, exc,
                )

    logger.info(
        "release_completed_event_payouts: released %d engagements",
        released_count,
    )
    return released_count
