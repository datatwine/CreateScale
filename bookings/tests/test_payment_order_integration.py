"""
Payment order creation + verification integration tests (Route mode).

Covers the full view path (bookings.views.create_payment_order /
verify_payment) driving PaymentService.create_order / verify_and_capture.
Razorpay is mocked at bookings.services.payments.get_client — no real API
calls. Service-level preconditions are unit-tested in test_payments_unit.py;
this file exercises the HTTP layer: JSON shapes, status codes, permissions,
HMAC verification, idempotency, and terminal-state guards.
"""

import hashlib
import hmac
import json
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from bookings.models import Engagement, Payment
from bookings.services.payments import PaymentService
from users.models import Profile


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test_secret",
    RAZORPAY_PLATFORM_FEE_PERCENT=5,
)
class TestPaymentOrderIntegration(TestCase):
    """POST /bookings/engagement/<pk>/pay/ + /verify/ — Route mode."""

    def setUp(self):
        # Meera is the CLIENT paying.
        self.meera = User.objects.create_user("meera", password="testpass")
        Profile.objects.filter(user=self.meera).update(
            is_potential_client=True, client_approved=True
        )
        # Ravi is the PERFORMER, fully onboarded (approved linked account).
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

        self.client.force_login(self.meera)

        self.mock_rzp = MagicMock()
        self.mock_rzp.order.create.return_value = {"id": "order_test_abc"}
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @property
    def pay_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/pay/"

    @property
    def verify_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/verify/"

    def _signature(self, order_id, payment_id, secret="test_secret"):
        body = f"{order_id}|{payment_id}".encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # ── Order creation ──────────────────────────────────────────────────
    def test_create_order_returns_checkout_data(self):
        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data["order_id"], "order_test_abc")
        self.assertEqual(data["amount"], 200000)  # ₹2000 × 100 paise
        self.assertEqual(data["currency"], "INR")
        self.assertEqual(data["key_id"], "rzp_test_key")

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "created")
        self.assertEqual(payment.amount, 2000)
        self.assertEqual(payment.platform_fee, 100)  # 5% of ₹2000
        self.assertEqual(payment.performer_share, 1900)
        self.assertEqual(payment.razorpay_order_id, "order_test_abc")

        # Right Razorpay payload: paise amounts + a HELD route transfer.
        self.mock_rzp.order.create.assert_called_once()
        called_with = self.mock_rzp.order.create.call_args[0][0]
        self.assertEqual(called_with["amount"], 200000)
        self.assertEqual(called_with["currency"], "INR")
        self.assertEqual(called_with["receipt"], f"eng_{self.engagement.pk}")
        transfer = called_with["transfers"][0]
        self.assertEqual(transfer["account"], "acc_test123")
        self.assertEqual(transfer["amount"], 190000)  # performer share in paise
        self.assertEqual(transfer["on_hold"], 1)

    def test_second_pay_resumes_open_order(self):
        # Order reuse (C1 + H1): a second /pay/ while the first order is still
        # open must NOT mint a duplicate — the client gets the SAME order_id
        # back and can retry checkout on it. Razorpay itself is the dedup layer.
        self.mock_rzp.order.fetch.return_value = {"status": "created"}
        first = self.client.post(self.pay_url)
        self.assertEqual(first.status_code, 200)
        first_order_id = first.json()["order_id"]

        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["order_id"], first_order_id)

        self.assertEqual(Payment.objects.filter(engagement=self.engagement).count(), 1)
        self.mock_rzp.order.create.assert_called_once()

    def test_pay_rejects_already_paid(self):
        self.engagement.payment_status = Engagement.PAYMENT_PAID
        self.engagement.save()

        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 400)
        self.mock_rzp.order.create.assert_not_called()

    def test_pay_rejects_unapproved_kyc(self):
        Profile.objects.filter(user=self.ravi).update(razorpay_kyc_status="pending")

        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)
        self.mock_rzp.order.create.assert_not_called()

    def test_pay_rejects_missing_fee_snapshot(self):
        self.engagement.fee = None
        self.engagement.save()

        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)
        self.mock_rzp.order.create.assert_not_called()

    # ── Permissions ─────────────────────────────────────────────────────
    def test_performer_cannot_create_order(self):
        self.client.force_login(self.ravi)
        resp = self.client.post(self.pay_url, raise_request_exception=False)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)
        self.mock_rzp.order.create.assert_not_called()

    def test_unrelated_user_cannot_create_order(self):
        priya = User.objects.create_user("priya", password="testpass")
        self.client.force_login(priya)
        resp = self.client.post(self.pay_url, raise_request_exception=False)
        self.assertEqual(resp.status_code, 403)
        self.mock_rzp.order.create.assert_not_called()

    def test_anonymous_pay_redirects_to_login(self):
        self.client.logout()
        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_get_on_pay_is_method_not_allowed(self):
        resp = self.client.get(self.pay_url)
        self.assertEqual(resp.status_code, 405)

    # ── Verification ────────────────────────────────────────────────────
    def _create_order(self):
        resp = self.client.post(self.pay_url)
        self.assertEqual(resp.status_code, 200)

    def test_verify_with_valid_hmac_captures_payment(self):
        self._create_order()
        order_id, payment_id = "order_test_abc", "pay_test_xyz"
        signature = self._signature(order_id, payment_id)

        resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.razorpay_payment_id, payment_id)

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)
        self.assertIsNotNone(self.engagement.paid_at)

    def test_verify_with_bad_hmac_returns_400(self):
        self._create_order()
        resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": "order_test_abc",
                    "razorpay_payment_id": "pay_test",
                    "razorpay_signature": "tampered_signature",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "created")  # unchanged
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_UNPAID)

    def test_verify_missing_keys_returns_400(self):
        self._create_order()
        resp = self.client.post(
            self.verify_url,
            data=json.dumps({"razorpay_order_id": "order_test_abc"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_verify_malformed_json_returns_400(self):
        self._create_order()
        resp = self.client.post(
            self.verify_url,
            data="{not valid json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_verify_unknown_order_returns_400(self):
        # Valid HMAC but the order was never created locally.
        signature = self._signature("order_ghost", "pay_ghost")
        resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": "order_ghost",
                    "razorpay_payment_id": "pay_ghost",
                    "razorpay_signature": signature,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_double_verify_is_idempotent_and_paid_at_stable(self):
        self._create_order()
        signature = self._signature("order_test_abc", "pay_test_xyz")
        payload = json.dumps(
            {
                "razorpay_order_id": "order_test_abc",
                "razorpay_payment_id": "pay_test_xyz",
                "razorpay_signature": signature,
            }
        )

        first = self.client.post(
            self.verify_url, data=payload, content_type="application/json"
        )
        self.assertEqual(first.status_code, 200)
        self.engagement.refresh_from_db()
        paid_at_first = self.engagement.paid_at

        second = self.client.post(
            self.verify_url, data=payload, content_type="application/json"
        )
        self.assertEqual(second.status_code, 200)

        self.engagement.refresh_from_db()
        # Capture again a moment later — paid_at must not be re-stamped.
        self.assertEqual(self.engagement.paid_at, paid_at_first)

    def test_verify_after_webhook_capture_is_noop(self):
        self._create_order()
        # The payment.captured webhook gets there first.
        PaymentService.mark_captured_from_webhook("order_test_abc", "pay_webhook")
        self.engagement.refresh_from_db()
        paid_at_before = self.engagement.paid_at

        signature = self._signature("order_test_abc", "pay_webhook")
        resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": "order_test_abc",
                    "razorpay_payment_id": "pay_webhook",
                    "razorpay_signature": signature,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        payment = Payment.objects.get(engagement=self.engagement)
        self.assertEqual(payment.status, "captured")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.paid_at, paid_at_before)  # not re-stamped

    def test_verify_on_refunded_payment_returns_400(self):
        Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            platform_fee=100,
            performer_share=1900,
            razorpay_order_id="order_test_abc",
            status="refunded",
        )
        signature = self._signature("order_test_abc", "pay_test_xyz")
        resp = self.client.post(
            self.verify_url,
            data=json.dumps(
                {
                    "razorpay_order_id": "order_test_abc",
                    "razorpay_payment_id": "pay_test_xyz",
                    "razorpay_signature": signature,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── Fee split arithmetic ────────────────────────────────────────────
    def test_fee_split_tricky_amounts(self):
        # platform_fee + performer_share must always equal the fee, even when
        # 5% doesn't divide cleanly.
        self.assertEqual(PaymentService._split_amount(1), (0, 1))
        self.assertEqual(PaymentService._split_amount(99), (4, 95))
        self.assertEqual(PaymentService._split_amount(10000), (500, 9500))
        for fee in (1, 99, 10000):
            platform, performer = PaymentService._split_amount(fee)
            self.assertEqual(platform + performer, fee)
