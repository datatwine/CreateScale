"""
TDD — written BEFORE implementation (issue #69, Parts 1c/1d/1e).

Tests for:
  POST /api/bookings/engagements/<pk>/pay/
  POST /api/bookings/engagements/<pk>/verify/
  POST /api/bookings/engagements/<pk>/dispute/

These mirror the web views create_payment_order, verify_payment, and
raise_dispute in bookings/views.py — same PaymentService calls, same
client-only gating, token auth instead of session auth.

Uses the shared engagement/client_user/performer_user/mock_razorpay
fixtures from conftest.py: performer_user is payable in both Route and
Payouts mode, engagement is pending, 10 days out, fee=2000.
"""
import hashlib
import hmac
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Engagement, Payment


def _pay_url(pk):
    return f"/api/bookings/engagements/{pk}/pay/"


def _verify_url(pk):
    return f"/api/bookings/engagements/{pk}/verify/"


def _dispute_url(pk):
    return f"/api/bookings/engagements/{pk}/dispute/"


def _accept(engagement):
    engagement.status = Engagement.STATUS_ACCEPTED
    engagement.accepted_at = timezone.now()
    engagement.save()


# ---------------------------------------------------------------------------
# pay
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPayAction:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self, engagement):
        r = self.api.post(_pay_url(engagement.pk))
        assert r.status_code == 401

    def test_only_client_can_pay(self, engagement, performer_user):
        _accept(engagement)
        self.api.force_authenticate(user=performer_user)
        r = self.api.post(_pay_url(engagement.pk))
        assert r.status_code == 403

    def test_third_party_cannot_pay(self, engagement, django_user_model):
        _accept(engagement)
        stranger = django_user_model.objects.create_user("stranger", password="x")
        self.api.force_authenticate(user=stranger)
        r = self.api.post(_pay_url(engagement.pk))
        assert r.status_code == 403

    def test_rejects_when_not_accepted(self, engagement, client_user):
        # Still pending — never accepted.
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_pay_url(engagement.pk))
        assert r.status_code == 400

    def test_returns_order_data_on_success(self, engagement, client_user, mock_razorpay, settings):
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        _accept(engagement)
        mock_razorpay.order.create.return_value = {"id": "order_X"}

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_pay_url(engagement.pk))

        assert r.status_code == 200
        assert r.data["order_id"] == "order_X"
        assert r.data["amount"] == 200000
        assert r.data["key_id"] == "rzp_test_key"
        assert Payment.objects.filter(engagement=engagement, razorpay_order_id="order_X").exists()

    def test_400_when_performer_not_payable(self, engagement, client_user, performer_user, mock_razorpay):
        _accept(engagement)
        performer_user.profile.bank_account_holder_name = ""
        performer_user.profile.bank_account_number = ""
        performer_user.profile.bank_ifsc = ""
        performer_user.profile.razorpay_account_id = ""
        performer_user.profile.razorpay_kyc_status = ""
        performer_user.profile.save()

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_pay_url(engagement.pk))

        assert r.status_code == 400
        assert "payment setup is incomplete" in r.data["error"]

    def test_400_when_already_paid(self, engagement, client_user, mock_razorpay):
        _accept(engagement)
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_pay_url(engagement.pk))

        assert r.status_code == 400


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestVerifyAction:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self, engagement):
        r = self.api.post(_verify_url(engagement.pk), data={}, format="json")
        assert r.status_code == 401

    def test_only_client_can_verify(self, engagement, performer_user):
        self.api.force_authenticate(user=performer_user)
        r = self.api.post(_verify_url(engagement.pk), data={
            "razorpay_order_id": "order_X",
            "razorpay_payment_id": "pay_Y",
            "razorpay_signature": "whatever",
        }, format="json")
        assert r.status_code == 403

    def test_happy_path_marks_paid(self, engagement, client_user, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement, amount=2000,
            razorpay_order_id="order_X", status="created",
        )
        body = b"order_X|pay_Y"
        sig = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_verify_url(engagement.pk), data={
            "razorpay_order_id": "order_X",
            "razorpay_payment_id": "pay_Y",
            "razorpay_signature": sig,
        }, format="json")

        assert r.status_code == 200
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID

    def test_400_on_bad_signature(self, engagement, client_user, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement, amount=2000,
            razorpay_order_id="order_X", status="created",
        )
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_verify_url(engagement.pk), data={
            "razorpay_order_id": "order_X",
            "razorpay_payment_id": "pay_Y",
            "razorpay_signature": "bogus",
        }, format="json")
        assert r.status_code == 400

    def test_400_on_missing_fields(self, engagement, client_user):
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_verify_url(engagement.pk), data={
            "razorpay_order_id": "order_X",
        }, format="json")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# dispute
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDisputeAction:

    def setup_method(self):
        self.api = APIClient()

    def _make_disputable(self, engagement):
        """Paid engagement whose event just ended (inside the 24h window)."""
        soon_past = timezone.now() - timedelta(hours=1)
        engagement.date = soon_past.date()
        engagement.time = soon_past.time().replace(microsecond=0)
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        return engagement

    def test_requires_authentication(self, engagement):
        r = self.api.post(_dispute_url(engagement.pk), data={"reason": "x" * 20}, format="json")
        assert r.status_code == 401

    def test_only_client_can_dispute(self, engagement, performer_user):
        self._make_disputable(engagement)
        self.api.force_authenticate(user=performer_user)
        r = self.api.post(_dispute_url(engagement.pk), data={"reason": "x" * 20}, format="json")
        assert r.status_code == 403

    def test_400_when_not_disputable(self, engagement, client_user):
        # Never paid, event still 10 days out — can_dispute is False.
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_dispute_url(engagement.pk), data={"reason": "x" * 20}, format="json")
        assert r.status_code == 400

    def test_400_on_reason_too_short(self, engagement, client_user):
        self._make_disputable(engagement)
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_dispute_url(engagement.pk), data={"reason": "too short"}, format="json")
        assert r.status_code == 400

    def test_success_sets_disputed_fields(self, engagement, client_user):
        self._make_disputable(engagement)
        self.api.force_authenticate(user=client_user)
        r = self.api.post(_dispute_url(engagement.pk), data={
            "reason": "The performer never showed up to the venue.",
        }, format="json")

        assert r.status_code == 200
        engagement.refresh_from_db()
        assert engagement.disputed_at is not None
        assert engagement.dispute_reason == "The performer never showed up to the venue."

    def test_400_when_already_disputed(self, engagement, client_user):
        self._make_disputable(engagement)
        engagement.disputed_at = timezone.now()
        engagement.save()

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_dispute_url(engagement.pk), data={"reason": "x" * 20}, format="json")
        assert r.status_code == 400
