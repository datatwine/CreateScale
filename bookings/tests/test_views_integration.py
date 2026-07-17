"""
Integration tests for the payment views — Django test Client + mocked
Razorpay. These verify the HTTP layer end-to-end (auth gates, permission
checks, response shapes) without touching the network.
"""
import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bookings.models import Engagement, Payment


@pytest.fixture
def client(db):
    """Django test client (renamed to avoid colliding with the `client_user` fixture)."""
    return Client()


# ─────────────────────────────────────────────────────────────────────────
# /pay/  — create_payment_order
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestCreatePaymentOrderView:

    def test_requires_login(self, client, engagement):
        # Anonymous → redirect to login
        r = client.post(reverse("bookings:create-payment-order", args=[engagement.pk]))
        assert r.status_code in (302, 403)

    def test_only_client_can_pay(self, client, engagement, performer_user):
        client.force_login(performer_user)
        r = client.post(reverse("bookings:create-payment-order", args=[engagement.pk]))
        assert r.status_code == 403

    def test_returns_order_data(self, client, engagement, client_user, mock_razorpay, settings):
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.accepted_at = timezone.now()
        engagement.save()
        mock_razorpay.order.create.return_value = {"id": "order_X"}

        client.force_login(client_user)
        r = client.post(reverse("bookings:create-payment-order", args=[engagement.pk]))

        assert r.status_code == 200
        data = r.json()
        assert data["order_id"] == "order_X"
        assert data["amount"] == 200000
        assert data["key_id"] == "rzp_test_key"

    def test_400_on_service_failure(self, client, engagement, client_user, mock_razorpay):
        # Performer setup incomplete → service raises → JSON 400. Clear ALL
        # payment-setup fields so the performer is unpayable in EITHER mode
        # (Route: linked account + KYC; payouts: bank details on file).
        p = engagement.performer.profile
        p.razorpay_account_id = ""
        p.razorpay_kyc_status = ""
        p.bank_account_holder_name = ""
        p.bank_account_number = ""
        p.bank_ifsc = ""
        p.save()
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.save()

        client.force_login(client_user)
        r = client.post(reverse("bookings:create-payment-order", args=[engagement.pk]))

        assert r.status_code == 400
        assert "payment setup is incomplete" in r.json()["error"]


# ─────────────────────────────────────────────────────────────────────────
# /verify/  — verify_payment
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestVerifyPaymentView:

    def test_happy_path(self, client, engagement, client_user, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement, amount=2000,
            razorpay_order_id="order_X", status="created",
        )
        body = b"order_X|pay_Y"
        sig = hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

        client.force_login(client_user)
        r = client.post(
            reverse("bookings:verify-payment", args=[engagement.pk]),
            data=json.dumps({
                "razorpay_order_id": "order_X",
                "razorpay_payment_id": "pay_Y",
                "razorpay_signature": sig,
            }),
            content_type="application/json",
        )

        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID

    def test_400_on_bad_signature(self, client, engagement, client_user, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement, amount=2000,
            razorpay_order_id="order_X", status="created",
        )
        client.force_login(client_user)
        r = client.post(
            reverse("bookings:verify-payment", args=[engagement.pk]),
            data=json.dumps({
                "razorpay_order_id": "order_X",
                "razorpay_payment_id": "pay_Y",
                "razorpay_signature": "bogus",
            }),
            content_type="application/json",
        )
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────
# /webhook/razorpay/  — razorpay_webhook
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestWebhookEndpoint:

    def test_rejects_bad_signature(self, client, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        r = client.post(
            reverse("bookings:razorpay-webhook"),
            data='{}', content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="bad",
        )
        assert r.status_code == 400

    def test_accepts_valid_signature(self, client, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        body = b'{"event":"some.unknown.event"}'
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()

        r = client.post(
            reverse("bookings:razorpay-webhook"),
            data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        assert r.status_code == 200

    def test_no_csrf_required(self, client, settings):
        # Just hits the endpoint without a CSRF token — should NOT 403
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        body = b"{}"
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        # client.post() handles CSRF by default in Django's test client
        # (it skips CSRF), but the explicit assertion here documents intent.
        r = client.post(
            reverse("bookings:razorpay-webhook"),
            data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        assert r.status_code in (200, 400)
        assert r.status_code != 403


# ─────────────────────────────────────────────────────────────────────────
# /dispute/  — raise_dispute
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestDisputeView:

    def test_client_can_raise_dispute_in_window(self, client, engagement, client_user):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 6 hours ago
        recent = timezone.now() - timedelta(hours=6)
        engagement.date = recent.date()
        engagement.time = recent.time().replace(microsecond=0)
        engagement.save()

        client.force_login(client_user)
        r = client.post(
            reverse("bookings:raise-dispute", args=[engagement.pk]),
            {"dispute_reason": "Performer never showed up at the venue"},
        )
        assert r.status_code == 302
        engagement.refresh_from_db()
        assert engagement.disputed_at is not None
        assert "never showed up" in engagement.dispute_reason

    def test_only_client_can_dispute(self, client, engagement, performer_user):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        recent = timezone.now() - timedelta(hours=6)
        engagement.date = recent.date()
        engagement.time = recent.time().replace(microsecond=0)
        engagement.save()

        client.force_login(performer_user)
        r = client.post(
            reverse("bookings:raise-dispute", args=[engagement.pk]),
            {"dispute_reason": "I want to mess with the client"},
        )
        assert r.status_code == 403

    def test_outside_window_rejected(self, client, engagement, client_user):
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_PAID
        # Event was 5 days ago — well outside the 24h window
        engagement.date = date.today() - timedelta(days=5)
        engagement.save()

        client.force_login(client_user)
        r = client.post(
            reverse("bookings:raise-dispute", args=[engagement.pk]),
            {"dispute_reason": "Too late but trying anyway"},
        )
        engagement.refresh_from_db()
        assert engagement.disputed_at is None


# ─────────────────────────────────────────────────────────────────────────
# /performer/payouts/ and /client/payments/
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestPaymentHistoryViews:

    def test_performer_payouts_renders(self, client, engagement, performer_user):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        client.force_login(performer_user)
        r = client.get(reverse("bookings:performer-payouts"))
        assert r.status_code == 200
        # Engagement is in the response somewhere
        assert engagement.occasion.encode() in r.content

    def test_client_payments_renders(self, client, engagement, client_user):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        client.force_login(client_user)
        r = client.get(reverse("bookings:client-payments"))
        assert r.status_code == 200
        assert engagement.occasion.encode() in r.content

    def test_empty_state(self, client, client_user):
        client.force_login(client_user)
        r = client.get(reverse("bookings:client-payments"))
        assert r.status_code == 200
        assert b"No payments yet" in r.content
