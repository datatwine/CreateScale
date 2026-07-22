"""
Celery tasks for time-based payment automation.

Three scheduled tasks:
  - expire_unpaid_engagements: hourly. Marks accepted engagements as
    auto_expired when the client missed the payment window. Uses
    Engagement.payment_deadline() which handles short-notice bookings.
  - expire_stale_pending_engagements: hourly. Marks pending engagements
    older than 24h as auto_expired so stale requests don't pile up.
  - release_completed_event_payouts: daily at 02:00. Releases payment for
    events that ended N hours ago (24h dispute window passed). Disputed
    engagements are explicitly skipped. release_to_performer() branches on
    RAZORPAY_ROUTE_ENABLED: Route mode unholds the escrowed transfer (terminal
    'released'); payouts mode fires a RazorpayX payout (engagement lands in
    payout_processing, flipped to 'released' later by the payout.processed
    webhook). Either way this task's job is unchanged.

All tasks are safe to run multiple times — every state transition is
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
    to_expire = [e.pk for e in candidates if (d := e.payment_deadline()) and now > d]

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
def expire_stale_pending_engagements() -> int:
    """
    Mark pending engagements older than 24h as auto_expired.

    Prevents stale requests from cluttering the performer's UI when nobody
    responded in time. Idempotent — safe to run multiple times.
    """
    cutoff = timezone.now() - timedelta(hours=24)
    stale = Engagement.objects.filter(
        status=Engagement.STATUS_PENDING,
        created_at__lt=cutoff,
    )

    count = stale.update(status=Engagement.STATUS_AUTO_EXPIRED)

    logger.info(
        "expire_stale_pending_engagements: marked %d engagements as expired",
        count,
    )
    return count


@shared_task
def release_completed_event_payouts() -> int:
    """
    Release payouts for events that ended N hours ago. The dispute window
    (default 24h after event end) must have closed first. Disputed
    engagements are skipped entirely — they wait for admin action.

    release_to_performer() branches internally on RAZORPAY_ROUTE_ENABLED. In
    payouts mode engagements move to payout_processing (not released) here — the
    webhook completes them — and because processing/failed rows no longer match
    the payment_status=PAID filter, they're never re-processed by a later run.
    """
    cutoff = timezone.now() - timedelta(hours=settings.RAZORPAY_DISPUTE_WINDOW_HOURS)

    ready = Engagement.objects.filter(
        status=Engagement.STATUS_ACCEPTED,
        payment_status=Engagement.PAYMENT_PAID,
        disputed_at__isnull=True,  # critical: skip disputed
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
                    e.pk,
                    exc,
                )

    logger.info(
        "release_completed_event_payouts: released %d engagements",
        released_count,
    )
    return released_count
