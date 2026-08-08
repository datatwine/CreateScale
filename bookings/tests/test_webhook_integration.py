"""
Razorpay + RazorpayX webhook integration tests.

Webhooks are Razorpay's server-to-server confirmation channel: no browser,
no CSRF token — authenticity comes from an HMAC-SHA256 over the raw body.
Covers signature enforcement, idempotent event handling (payment.captured,
refund.processed, transfer.processed, payout.processed), unknown-order
robustness, and CSRF exemption.
"""

import hashlib
import hmac
import json
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from bookings.models import Engagement, Payment
from users.models import Profile


@override_settings(
    RAZORPAY_WEBHOOK_SECRET="whsec_test",
    RAZORPAYX_WEBHOOK_SECRET="whsecx_test",
    RAZORPAY_ROUTE_ENABLED=True,
)
class TestGatewayWebhookIntegration(TestCase):
    """POST /bookings/webhook/razorpay/"""

    def setUp(self):
        self.meera = User.objects.create_user("meera", password="testpass")
        Profile.objects.filter(user=self.meera).update(
            is_potential_client=True, client_approved=True
        )
        self.ravi = User.objects.create_user("ravi", password="testpass")
        Profile.objects.filter(user=self.ravi).update(
            is_performer=True,
            performer_fee=2000,
            razorpay_account_id="acc_test123",
            razorpay_kyc_status="approved",
        )

        self.engagement = Engagement.objects.create(
            client=self.meera,
            performer=self.ravi,
            date=date.today() + timedelta(days=10),
            time=time(19, 0),
            venue="V",
            occasion="O",
            fee=2000,
            status=Engagement.STATUS_ACCEPTED,
        )
        self.payment = Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            razorpay_order_id="order_wh",
            status="created",
        )

    @property
    def url(self):
        return "/bookings/webhook/razorpay/"

    def _post(self, event, entity_key, entity, sig=None, secret="whsec_test"):
        body = json.dumps(
            {"event": event, "payload": {entity_key: {"entity": entity}}}
        ).encode()
        if sig is None:
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )

    # ── payment.captured ─────────────────────────────────────────────
    def test_payment_captured_marks_paid(self):
        resp = self._post(
            "payment.captured",
            "payment",
            {"order_id": "order_wh", "id": "pay_wh"},
        )
        self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "captured")
        self.assertEqual(self.payment.razorpay_payment_id, "pay_wh")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)
        self.assertIsNotNone(self.engagement.paid_at)

    def test_payment_captured_idempotent(self):
        for _ in range(2):
            resp = self._post(
                "payment.captured",
                "payment",
                {"order_id": "order_wh", "id": "pay_wh"},
            )
            self.assertEqual(resp.status_code, 200)

        self.assertEqual(Payment.objects.filter(engagement=self.engagement).count(), 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "captured")
        self.assertEqual(self.payment.razorpay_payment_id, "pay_wh")

    def test_payment_captured_unknown_order_returns_200(self):
        # A webhook for an order we never created must not 500 — log and ack.
        resp = self._post(
            "payment.captured",
            "payment",
            {"order_id": "order_unknown", "id": "pay_unknown"},
        )
        self.assertEqual(resp.status_code, 200)

    # ── refund.processed ─────────────────────────────────────────────
    def test_refund_processed_marks_refunded(self):
        self.payment.status = "refunded"
        self.payment.razorpay_refund_id = "rfnd_wh"
        self.payment.save()

        resp = self._post(
            "refund.processed",
            "refund",
            {"id": "rfnd_wh"},
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refunded")

    # ── transfer.processed ───────────────────────────────────────────
    def test_transfer_processed_marks_released(self):
        self.payment.status = "captured"
        self.payment.razorpay_transfer_id = "trf_wh"
        self.payment.save()

        resp = self._post(
            "transfer.processed",
            "transfer",
            {"id": "trf_wh"},
        )
        self.assertEqual(resp.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "released")

    # ── Signature / CSRF enforcement ─────────────────────────────────
    def test_bad_signature_returns_400(self):
        resp = self._post(
            "payment.captured",
            "payment",
            {"order_id": "order_wh", "id": "pay_wh"},
            sig="deadbeef",
        )
        self.assertEqual(resp.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "created")

    def test_missing_signature_returns_400(self):
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {"payment": {"entity": {"order_id": "order_wh"}}},
            }
        ).encode()
        resp = self.client.post(self.url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_malformed_json_returns_400(self):
        body = b"{not json"
        sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
        resp = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        self.assertEqual(resp.status_code, 400)

    def test_unknown_event_type_returns_200_no_crash(self):
        # payment.failed (or a brand-new event Razorpay adds) — log and ack
        # with 200 so Razorpay stops retrying, without touching the DB.
        before = Payment.objects.get(engagement=self.engagement)
        resp = self._post(
            "payment.failed",
            "payment",
            {"order_id": "order_wh", "id": "pay_wh"},
        )
        self.assertEqual(resp.status_code, 200)
        after = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(after.status, before.status)

    def test_webhook_exempt_from_csrf(self):
        # No browser → no CSRF cookie/token. The view must accept the POST.
        csrf_client = Client(enforce_csrf_checks=True)
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {"entity": {"order_id": "order_wh", "id": "pay_wh"}}
                },
            }
        ).encode()
        sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
        resp = csrf_client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        self.assertEqual(resp.status_code, 200)


@override_settings(
    RAZORPAYX_WEBHOOK_SECRET="whsecx_test",
)
class TestRazorpayXWebhookIntegration(TestCase):
    """POST /bookings/webhook/razorpayx/ — payout.processed → released."""

    def setUp(self):
        self.meera = User.objects.create_user("meera", password="testpass")
        Profile.objects.filter(user=self.meera).update(
            is_potential_client=True, client_approved=True
        )
        self.ravi = User.objects.create_user("ravi", password="testpass")
        Profile.objects.filter(user=self.ravi).update(
            is_performer=True,
            performer_fee=2000,
            razorpay_account_id="acc_test123",
            razorpay_kyc_status="approved",
        )

        self.engagement = Engagement.objects.create(
            client=self.meera,
            performer=self.ravi,
            date=date.today() + timedelta(days=10),
            time=time(19, 0),
            venue="V",
            occasion="O",
            fee=2000,
            status=Engagement.STATUS_ACCEPTED,
            payment_status=Engagement.PAYMENT_PAYOUT_PROCESSING,
        )
        self.payment = Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            performer_share=1900,
            razorpay_order_id="order_whx",
            razorpayx_payout_id="pout_wh",
            status="payout_processing",
        )

    @property
    def url(self):
        return "/bookings/webhook/razorpayx/"

    def _post(self, event, entity, sig=None, secret="whsecx_test"):
        body = json.dumps(
            {"event": event, "payload": {"payout": {"entity": entity}}}
        ).encode()
        if sig is None:
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            self.url,
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )

    def test_payout_processed_releases(self):
        resp = self._post(
            "payout.processed",
            {"id": "pout_wh", "utr": "UTR123456"},
        )
        self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "released")
        self.assertEqual(self.payment.payout_reference, "UTR123456")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_RELEASED)
        self.assertIsNotNone(self.engagement.released_at)

    def test_payout_processed_idempotent(self):
        for _ in range(2):
            resp = self._post("payout.processed", {"id": "pout_wh"})
            self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "released")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_RELEASED)

    def test_payout_unknown_payout_returns_200(self):
        resp = self._post("payout.processed", {"id": "pout_unknown"})
        self.assertEqual(resp.status_code, 200)

    def test_bad_signature_returns_400(self):
        resp = self._post("payout.processed", {"id": "pout_wh"}, sig="nope")
        self.assertEqual(resp.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "payout_processing")

    def test_payout_reversed_marks_failed(self):
        resp = self._post("payout.failed", {"id": "pout_wh"})
        self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "payout_failed")
        self.engagement.refresh_from_db()
        self.assertEqual(
            self.engagement.payment_status, Engagement.PAYMENT_PAYOUT_FAILED
        )
