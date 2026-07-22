"""
Tests for the Celery tasks in bookings/tasks.py.

We don't actually run Celery — we call the task functions directly.
PaymentService.release_to_performer is monkey-patched so these tests
never touch Razorpay's API.
"""

from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from bookings.models import Engagement
from bookings.tasks import (
    expire_unpaid_engagements,
    release_completed_event_payouts,
)


# ─────────────────────────────────────────────────────────────────────────
# expire_unpaid_engagements
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestExpireUnpaid:
    def test_expires_engagement_past_deadline(self, engagement):
        # Backdate accepted_at by 30h so payment_deadline (24h after
        # acceptance) is comfortably in the past.
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.accepted_at = timezone.now() - timedelta(hours=30)
        engagement.save()

        count = expire_unpaid_engagements()

        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_AUTO_EXPIRED
        assert count == 1

    def test_does_not_expire_within_window(self, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.accepted_at = timezone.now() - timedelta(hours=12)
        engagement.save()

        count = expire_unpaid_engagements()

        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_ACCEPTED  # unchanged
        assert count == 0

    def test_skips_already_paid_engagement(self, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.accepted_at = timezone.now() - timedelta(hours=30)
        engagement.save()

        count = expire_unpaid_engagements()

        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_ACCEPTED  # paid, not expired
        assert count == 0

    def test_short_notice_uses_dynamic_window(self, engagement):
        # Event in 4 hours → deadline = min(24h_after_accept, event-2h)
        # → deadline = event-2h = 2 hours from now. Accept now, then jump
        # forward by setting accepted_at into the past so deadline elapses.
        soon = timezone.now() + timedelta(hours=4)
        engagement.date = soon.date()
        engagement.time = soon.time().replace(microsecond=0)
        engagement.status = Engagement.STATUS_ACCEPTED
        # Accepted_at doesn't matter much here — what matters is event-2h
        # is already past. Set accepted_at to event-3h so the standard 24h
        # window is far out, but event-2h clamps the deadline.
        engagement.accepted_at = soon - timedelta(hours=3)
        engagement.save()
        # Currently we're 4h before event; deadline = event-2h = +2h from now → NOT expired
        count = expire_unpaid_engagements()
        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_ACCEPTED  # still in window


# ─────────────────────────────────────────────────────────────────────────
# release_completed_event_payouts
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestReleasePayouts:
    @patch("bookings.tasks.PaymentService.release_to_performer")
    def test_releases_after_dispute_window(self, mock_release, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 2 days ago — well past the 24h dispute window
        engagement.date = date.today() - timedelta(days=2)
        engagement.save()

        count = release_completed_event_payouts()

        mock_release.assert_called_once_with(engagement)
        assert count == 1

    @patch("bookings.tasks.PaymentService.release_to_performer")
    def test_does_not_release_within_dispute_window(self, mock_release, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 6 hours ago — still inside 24h dispute window
        soon_past = timezone.now() - timedelta(hours=6)
        engagement.date = soon_past.date()
        engagement.time = soon_past.time().replace(microsecond=0)
        engagement.save()

        count = release_completed_event_payouts()

        mock_release.assert_not_called()
        assert count == 0

    @patch("bookings.tasks.PaymentService.release_to_performer")
    def test_skips_disputed_engagements(self, mock_release, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.disputed_at = timezone.now()
        engagement.dispute_reason = "performer no-show"
        engagement.date = date.today() - timedelta(days=2)
        engagement.save()

        count = release_completed_event_payouts()

        mock_release.assert_not_called()
        assert count == 0

    @patch("bookings.tasks.PaymentService.release_to_performer")
    def test_one_failure_doesnt_block_others(
        self, mock_release, engagement, performer_user, client_user
    ):
        # First engagement raises; second engagement should still release.
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.date = date.today() - timedelta(days=2)
        engagement.save()

        second = Engagement.objects.create(
            client=client_user,
            performer=performer_user,
            date=date.today() - timedelta(days=2),
            time=time(20, 0),
            venue="Other venue",
            occasion="Other",
            fee=3000,
            status=Engagement.STATUS_ACCEPTED,
            payment_status=Engagement.PAYMENT_PAID,
        )

        mock_release.side_effect = [Exception("boom"), None]
        count = release_completed_event_payouts()

        # Both were attempted; one succeeded
        assert mock_release.call_count == 2
        assert count == 1
