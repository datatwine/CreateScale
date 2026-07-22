"""
Tests for the Engagement model's new cancel rules.

These run against the actual model methods — no Razorpay, no HTTP. They
guard the business rules:
  - Within 24h of event → cancel blocked entirely
  - Reason is mandatory and at least non-empty
  - accept() stamps accepted_at
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from bookings.models import Engagement


@pytest.mark.django_db
class TestCancelWithin24h:
    def test_block_within_24h_client(self, engagement):
        # Push the event to 12h from now
        soon = timezone.now() + timedelta(hours=12)
        engagement.date = soon.date()
        engagement.time = soon.time().replace(microsecond=0)
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.save()

        with pytest.raises(ValidationError, match="within 24 hours"):
            engagement.cancel_by_client(reason="last minute thing happened")

    def test_block_within_24h_performer(self, engagement):
        soon = timezone.now() + timedelta(hours=12)
        engagement.date = soon.date()
        engagement.time = soon.time().replace(microsecond=0)
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.save()

        with pytest.raises(ValidationError, match="within 24 hours"):
            engagement.cancel_by_performer(reason="I am sick and cannot make it")

    def test_allowed_well_outside_24h(self, engagement):
        # Default fixture: event in 10 days, status pending
        engagement.cancel_by_client(reason="Plans changed, sorry.")
        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_CANCELLED_CLIENT
        assert engagement.cancelled_by == "client"
        assert engagement.cancellation_reason == "Plans changed, sorry."


@pytest.mark.django_db
class TestCancelReasonMandatory:
    def test_empty_reason_rejected_client(self, engagement):
        with pytest.raises(ValidationError, match="reason is required"):
            engagement.cancel_by_client(reason="")

    def test_whitespace_only_reason_rejected(self, engagement):
        with pytest.raises(ValidationError, match="reason is required"):
            engagement.cancel_by_client(reason="    \t  \n")

    def test_empty_reason_rejected_performer(self, engagement):
        with pytest.raises(ValidationError, match="reason is required"):
            engagement.cancel_by_performer(reason="")


@pytest.mark.django_db
class TestCancelTerminalStates:
    def test_cannot_cancel_already_declined(self, engagement):
        engagement.status = Engagement.STATUS_DECLINED
        engagement.save()
        with pytest.raises(ValidationError, match="Only pending or accepted"):
            engagement.cancel_by_client(reason="too late")

    def test_cannot_cancel_already_cancelled(self, engagement):
        engagement.status = Engagement.STATUS_CANCELLED_CLIENT
        engagement.save()
        with pytest.raises(ValidationError, match="Only pending or accepted"):
            engagement.cancel_by_client(reason="trying again")


@pytest.mark.django_db
class TestAcceptStampsAcceptedAt:
    def test_accept_sets_accepted_at(self, engagement):
        assert engagement.accepted_at is None
        before = timezone.now()
        engagement.accept()
        engagement.refresh_from_db()
        assert engagement.status == Engagement.STATUS_ACCEPTED
        assert engagement.accepted_at is not None
        assert engagement.accepted_at >= before


@pytest.mark.django_db
class TestPaymentDeadline:
    def test_none_before_acceptance(self, engagement):
        assert engagement.payment_deadline() is None

    def test_24h_after_acceptance_in_normal_case(self, engagement, settings):
        settings.RAZORPAY_PAYMENT_WINDOW_HOURS = 24
        # Event in 10 days, so event-2h is far in the future; standard
        # 24h window wins.
        engagement.accepted_at = timezone.now()
        engagement.save()
        deadline = engagement.payment_deadline()
        expected = engagement.accepted_at + timedelta(hours=24)
        assert abs((deadline - expected).total_seconds()) < 5

    def test_clamps_for_short_notice(self, engagement, settings):
        settings.RAZORPAY_PAYMENT_WINDOW_HOURS = 24
        # Event in 4h: deadline should clamp to event - 2h = 2h from now.
        soon = timezone.now() + timedelta(hours=4)
        engagement.date = soon.date()
        engagement.time = soon.time().replace(microsecond=0)
        engagement.accepted_at = timezone.now()
        engagement.save()
        deadline = engagement.payment_deadline()
        expected = engagement.event_datetime() - timedelta(hours=2)
        assert abs((deadline - expected).total_seconds()) < 5


@pytest.mark.django_db
class TestCanDispute:
    def test_false_when_unpaid(self, engagement):
        assert engagement.can_dispute is False

    def test_false_before_event_end(self, engagement):
        # Event is 10 days out; even if paid we can't dispute yet
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        assert engagement.can_dispute is False

    def test_true_within_24h_post_event(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 6 hours ago
        recent = timezone.now() - timedelta(hours=6)
        engagement.date = recent.date()
        engagement.time = recent.time().replace(microsecond=0)
        engagement.save()
        assert engagement.can_dispute is True

    def test_false_after_window_closes(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 2 days ago
        engagement.date = date.today() - timedelta(days=2)
        engagement.save()
        assert engagement.can_dispute is False

    def test_false_when_already_disputed(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        recent = timezone.now() - timedelta(hours=6)
        engagement.date = recent.date()
        engagement.time = recent.time().replace(microsecond=0)
        engagement.disputed_at = timezone.now()
        engagement.save()
        assert engagement.can_dispute is False
