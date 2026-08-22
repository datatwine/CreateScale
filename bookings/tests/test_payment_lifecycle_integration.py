"""
Full payment lifecycle integration test (Route mode).

Walks ONE booking through every stage on the real web surfaces with Razorpay
mocked at bookings.services.payments.get_client:

    hire → accept → pay (held escrow transfer) → verify/capture → release
    hire → accept → pay → verify/capture → client cancel → refund

This is the automated stand-in for the manual end-to-end smoke test the issue
planned to run separately: the same flow, exercised by code so regressions
can't silently slip back in.
"""

import hashlib
import hmac
import json
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from bookings.models import Engagement, Payment
from bookings.tasks import release_completed_event_payouts
from users.models import Profile


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test_secret",
    RAZORPAY_PLATFORM_FEE_PERCENT=5,
    RAZORPAY_DISPUTE_WINDOW_HOURS=24,
)
class TestPaymentLifecycleIntegration(TestCase):
    """One booking through the whole money flow, web client + force_login."""

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

        self.mock_rzp = MagicMock()
        self.mock_rzp.order.create.return_value = {"id": "order_life"}
        self.mock_rzp.payment.transfers.return_value = {"items": [{"id": "trf_life"}]}
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @property
    def hire_url(self):
        return f"/bookings/hire/{self.ravi.id}/"

    @property
    def detail_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/"

    @property
    def pay_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/pay/"

    @property
    def verify_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/verify/"

    def _signature(self, order_id, payment_id):
        body = f"{order_id}|{payment_id}".encode()
        return hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()

    def _hire(self):
        self.client.force_login(self.meera)
        return self.client.post(
            self.hire_url,
            {
                "date": str(date.today() + timedelta(days=30)),
                "time": "19:00",
                "venue": "Marine Drive",
                "occasion": "Wedding",
            },
        )

    def _accept(self):
        self.client.force_login(self.ravi)
        return self.client.post(self.detail_url, {"action": "accept"})

    def _pay_and_capture(self):
        self.client.force_login(self.meera)
        order_resp = self.client.post(self.pay_url)
        order_id = order_resp.json()["order_id"]
        verify_resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": "pay_life",
                    "razorpay_signature": self._signature(order_id, "pay_life"),
                }
            ),
            content_type="application/json",
        )
        return order_resp, verify_resp

    # ── Happy path: hire → accept → pay → capture → release ──────────
    def test_full_lifecycle_escrow_release(self):
        resp = self._hire()
        self.assertEqual(resp.status_code, 302)

        self.engagement = Engagement.objects.get(client=self.meera)
        self.assertEqual(self.engagement.status, Engagement.STATUS_PENDING)

        resp = self._accept()
        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_ACCEPTED)
        self.assertIsNotNone(self.engagement.accepted_at)

        order_resp, verify_resp = self._pay_and_capture()
        self.assertEqual(order_resp.status_code, 200)
        self.assertEqual(order_resp.json()["order_id"], "order_life")
        self.assertEqual(verify_resp.status_code, 200)
        self.assertEqual(verify_resp.json()["status"], "ok")

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)
        self.assertIsNotNone(self.engagement.paid_at)

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.razorpay_payment_id, "pay_life")

        # The money sat in a HELD escrow transfer until the event passed.
        transfer = self.mock_rzp.order.create.call_args[0][0]["transfers"][0]
        self.assertEqual(transfer["on_hold"], 1)
        self.assertEqual(transfer["amount"], 190000)  # performer share, paise

        # Event passes; dispute window (24h) closes; the daily task releases.
        past_date = date.today() - timedelta(days=2)
        Engagement.objects.filter(pk=self.engagement.pk).update(
            date=past_date, time=time(12, 0)
        )
        self.engagement.refresh_from_db()
        fixed_now = self.engagement.event_datetime() + timedelta(hours=48)
        with patch("bookings.tasks.timezone.now", return_value=fixed_now):
            count = release_completed_event_payouts()

        self.assertEqual(count, 1)
        self.mock_rzp.transfer.edit.assert_called_once_with("trf_life", {"on_hold": 0})

        payment.refresh_from_db()
        self.assertEqual(payment.status, "released")
        self.assertEqual(payment.razorpay_transfer_id, "trf_life")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_RELEASED)
        self.assertIsNotNone(self.engagement.released_at)

    # ── Variant: client cancels after payment → full refund ──────────
    def test_lifecycle_cancel_after_payment_refunds_client(self):
        self._hire()
        self.engagement = Engagement.objects.get(client=self.meera)
        self._accept()

        order_resp, verify_resp = self._pay_and_capture()
        self.assertEqual(verify_resp.status_code, 200)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)

        self.client.force_login(self.meera)
        self.mock_rzp.payment.refund.return_value = {"id": "rfnd_life"}
        resp = self.client.post(
            self.detail_url,
            {"action": "cancel_client", "cancellation_reason": "Plans changed."},
        )
        self.assertEqual(resp.status_code, 302)

        # Route mode: the refund reverses the held transfer (reverse_all).
        self.mock_rzp.payment.refund.assert_called_once_with(
            "pay_life",
            {
                "notes": {
                    "engagement_id": str(self.engagement.pk),
                    "reason": "Plans changed.",
                },
                "reverse_all": 1,
            },
        )

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "cancelled_client")
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(self.engagement.refunded_at)

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "refunded")
        self.assertEqual(payment.razorpay_refund_id, "rfnd_life")
