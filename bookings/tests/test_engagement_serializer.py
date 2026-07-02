"""
TDD — written BEFORE implementation (issue #23).

EngagementSerializer must expose fee, payment_status, and payment_deadline
so the mobile app can compute "Pay Now" visibility (accepted + unpaid +
fee set) without a second round-trip.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.api.serializers import EngagementSerializer
from bookings.models import Engagement


@pytest.mark.django_db
class TestEngagementSerializerPaymentFields:

    def test_includes_fee(self, engagement):
        data = EngagementSerializer(engagement).data
        assert data["fee"] == 2000

    def test_includes_payment_status(self, engagement):
        data = EngagementSerializer(engagement).data
        assert data["payment_status"] == Engagement.PAYMENT_UNPAID

    def test_payment_deadline_is_null_before_acceptance(self, engagement):
        # conftest's `engagement` fixture is pending, never accepted
        data = EngagementSerializer(engagement).data
        assert data["payment_deadline"] is None

    def test_payment_deadline_is_set_after_acceptance(self, engagement):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.accepted_at = timezone.now()
        engagement.save(update_fields=["status", "accepted_at"])

        data = EngagementSerializer(engagement).data

        assert data["payment_deadline"] is not None
        # Deadline should be in the future relative to acceptance
        deadline = engagement.payment_deadline()
        assert data["payment_deadline"] == deadline.isoformat()
