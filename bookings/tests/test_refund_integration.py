"""
Refund-on-cancel integration tests (Route mode).

Covers the full cancel → refund path on BOTH surfaces:
  - Web: POST /bookings/engagement/<pk>/  (engagement_detail view)
  - API: POST /api/bookings/engagements/<pk>/action/

Razorpay is mocked at bookings.services.payments.get_client. Route mode is
pinned ON so the refund carries reverse_all=1 (unwinds the held escrow
transfer back to the client). Refund failures must never 500 the request —
the cancel commits and an admin-follow-up message is shown (Fix #2).
"""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from bookings.models import Engagement, Payment
from users.models import Profile


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_PLATFORM_FEE_PERCENT=5,
)
class TestRefundWebIntegration(TestCase):
    """Cancel + refund through the Django web views (force_login)."""

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
            payment_status=Engagement.PAYMENT_PAID,
        )
        self.payment = Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            platform_fee=100,
            performer_share=1900,
            razorpay_order_id="order_ref",
            razorpay_payment_id="pay_ref",
            status="captured",
        )

        self.mock_rzp = MagicMock()
        self.mock_rzp.payment.refund.return_value = {"id": "rfnd_ref123"}
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @property
    def detail_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/"

    def _cancel(self, action, reason):
        return self.client.post(
            self.detail_url,
            {"action": action, "cancellation_reason": reason},
        )

    def test_client_cancel_paid_refunds_with_reverse_all(self):
        self.client.force_login(self.meera)
        resp = self._cancel("cancel_client", "Client cancelled the booking.")

        self.assertEqual(resp.status_code, 302)  # redirect to my bookings
        self.assertRedirects(resp, "/bookings/client/")

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "cancelled_client")
        self.assertEqual(self.engagement.cancelled_by, "client")
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(self.engagement.refunded_at)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refunded")
        self.assertEqual(self.payment.razorpay_refund_id, "rfnd_ref123")

        # Route mode: reverse_all unwinds the performer's held escrow transfer.
        self.mock_rzp.payment.refund.assert_called_once_with(
            "pay_ref",
            {
                "notes": {
                    "engagement_id": str(self.engagement.pk),
                    "reason": "Client cancelled the booking.",
                },
                "reverse_all": 1,
            },
        )

    def test_performer_cancel_paid_refunds(self):
        self.client.force_login(self.ravi)
        resp = self._cancel("cancel_performer", "Performer is unavailable.")

        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, "/bookings/performer/")

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "cancelled_performer")
        self.assertEqual(self.engagement.cancelled_by, "performer")
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(self.engagement.refunded_at)
        self.mock_rzp.payment.refund.assert_called_once()

    def test_cancel_unpaid_does_not_call_refund(self):
        self.engagement.payment_status = Engagement.PAYMENT_UNPAID
        self.engagement.save(update_fields=["payment_status"])

        self.client.force_login(self.meera)
        resp = self._cancel("cancel_client", "No payment happened yet.")

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_UNPAID)
        self.mock_rzp.payment.refund.assert_not_called()

    @patch("bookings.services.payments.PaymentService.refund_to_client")
    def test_refund_failure_no_500_cancel_still_commits(self, mock_refund):
        # Simulate a Razorpay outage: refund raises. The page must NOT 500.
        mock_refund.side_effect = Exception("Razorpay timeout")

        self.client.force_login(self.meera)
        resp = self._cancel("cancel_client", "Client cancelled despite outage.")

        # Cancel already committed; only the refund failed.
        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "cancelled_client")
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)
        self.assertIsNone(self.engagement.refunded_at)
        mock_refund.assert_called_once_with(self.engagement)


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_PLATFORM_FEE_PERCENT=5,
)
class TestRefundAPIIntegration(TestCase):
    """Cancel + refund through the DRF action endpoint (Token auth)."""

    def setUp(self):
        self.client = APIClient()

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
        self.client_token = Token.objects.create(user=self.meera)
        self.performer_token = Token.objects.create(user=self.ravi)

        self.engagement = Engagement.objects.create(
            client=self.meera,
            performer=self.ravi,
            date=date.today() + timedelta(days=10),
            time=time(19, 0),
            venue="V",
            occasion="O",
            fee=2000,
            status=Engagement.STATUS_ACCEPTED,
            payment_status=Engagement.PAYMENT_PAID,
        )
        self.payment = Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            platform_fee=100,
            performer_share=1900,
            razorpay_order_id="order_ref_api",
            razorpay_payment_id="pay_ref_api",
            status="captured",
        )

        self.mock_rzp = MagicMock()
        self.mock_rzp.payment.refund.return_value = {"id": "rfnd_ref_api"}
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @property
    def action_url(self):
        return f"/api/bookings/engagements/{self.engagement.pk}/action/"

    def _action(self, token, action, reason):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return self.client.post(
            self.action_url,
            {"action": action, "emergency_reason": reason},
            format="json",
        )

    def test_api_client_cancel_paid_refunds(self):
        resp = self._action(self.client_token, "cancel_client", "Client cancelled.")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detail"], "Cancelled by client.")

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.assertIsNotNone(self.engagement.refunded_at)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refunded")
        self.assertEqual(self.payment.razorpay_refund_id, "rfnd_ref_api")
        self.mock_rzp.payment.refund.assert_called_once()

    def test_api_performer_cancel_paid_refunds(self):
        resp = self._action(self.performer_token, "cancel_performer", "Performer busy.")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["detail"], "Cancelled by performer.")

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.mock_rzp.payment.refund.assert_called_once()

    def test_api_double_cancel_does_not_refund_twice(self):
        self._action(self.client_token, "cancel_client", "First valid reason here.")
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)

        resp = self._action(self.client_token, "cancel_client", "Second attempt text.")
        self.assertEqual(resp.status_code, 400)  # terminal state → no re-cancel

        # refund fires exactly once — no double refund.
        self.mock_rzp.payment.refund.assert_called_once()

    def test_api_refund_failure_returns_200_with_admin_note(self):
        self.mock_rzp.payment.refund.side_effect = Exception("Razorpay down")

        resp = self._action(self.client_token, "cancel_client", "Cancel during outage.")

        # No 500: cancel committed, API tells the client an admin will follow up.
        self.assertEqual(resp.status_code, 200)
        self.assertIn("refund could not be processed", resp.json()["detail"])

        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, "cancelled_client")
        # C4 crash-safe marker: Step 1 flips to refund_pending BEFORE the API
        # call, so a failed refund leaves the row looking refund-pending (never
        # re-capturable), not silently "captured". Money stays in escrow.
        self.assertEqual(
            self.engagement.payment_status, Engagement.PAYMENT_REFUND_PENDING
        )
        self.assertIsNone(self.engagement.refunded_at)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refund_pending")

    def test_api_cancel_unpaid_does_not_call_refund(self):
        self.engagement.payment_status = Engagement.PAYMENT_UNPAID
        self.engagement.save(update_fields=["payment_status"])

        resp = self._action(self.client_token, "cancel_client", "No payment made yet.")

        self.assertEqual(resp.status_code, 200)
        self.mock_rzp.payment.refund.assert_not_called()

    def test_refund_to_client_second_call_is_noop(self):
        # Issue requirement: refund_to_client() called twice on the same
        # engagement. First call reverses the money; the second must no-op
        # via the payment_status != PAID guard — no second Razorpay call,
        # refunded_at and refund id stay untouched.
        from bookings.services.payments import PaymentService

        PaymentService.refund_to_client(self.engagement)
        self.mock_rzp.payment.refund.assert_called_once()

        self.engagement.refresh_from_db()
        refunded_at = self.engagement.refunded_at

        PaymentService.refund_to_client(self.engagement)

        self.mock_rzp.payment.refund.assert_called_once()  # still exactly once
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.refunded_at, refunded_at)
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_REFUNDED)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refunded")
