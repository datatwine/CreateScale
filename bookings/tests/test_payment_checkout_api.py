"""
TDD — written BEFORE implementation (issue #23).

Tests for:
  POST /api/bookings/payments/<pk>/create-order/
  POST /api/bookings/payments/<pk>/verify/

Thin DRF wrappers around PaymentService.create_order() and
PaymentService.verify_and_capture() — token auth instead of session auth,
same business logic as the web views (bookings/views.py:288-323).
"""
import hashlib
import hmac
import json

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Engagement, Payment


def _create_order_url(pk):
    return f"/api/bookings/payments/{pk}/create-order/"


def _verify_url(pk):
    return f"/api/bookings/payments/{pk}/verify/"


# ---------------------------------------------------------------------------
# create-order
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCreatePaymentOrderAPI:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self, engagement):
        r = self.api.post(_create_order_url(engagement.pk))
        assert r.status_code == 401

    def test_only_client_can_pay(self, engagement, performer_user):
        self.api.force_authenticate(user=performer_user)
        r = self.api.post(_create_order_url(engagement.pk))
        assert r.status_code == 403

    def test_returns_order_data(self, engagement, client_user, mock_razorpay, settings):
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.accepted_at = timezone.now()
        engagement.save()
        mock_razorpay.order.create.return_value = {"id": "order_X"}

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_create_order_url(engagement.pk))

        assert r.status_code == 200
        assert r.data["order_id"] == "order_X"
        assert r.data["amount"] == 200000
        assert r.data["key_id"] == "rzp_test_key"

    def test_400_on_service_failure(self, engagement, client_user, mock_razorpay):
        engagement.performer.profile.razorpay_kyc_status = ""
        engagement.performer.profile.save()
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.save()

        self.api.force_authenticate(user=client_user)
        r = self.api.post(_create_order_url(engagement.pk))

        assert r.status_code == 400
        assert "payment setup is incomplete" in r.data["error"]


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestVerifyPaymentAPI:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self, engagement):
        r = self.api.post(_verify_url(engagement.pk), data={}, format="json")
        assert r.status_code == 401

    def test_happy_path(self, engagement, client_user, settings):
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
        assert r.data["status"] == "ok"
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

    def test_only_client_can_verify(self, engagement, performer_user):
        self.api.force_authenticate(user=performer_user)
        r = self.api.post(_verify_url(engagement.pk), data={
            "razorpay_order_id": "order_X",
            "razorpay_payment_id": "pay_Y",
            "razorpay_signature": "whatever",
        }, format="json")
        assert r.status_code == 403
