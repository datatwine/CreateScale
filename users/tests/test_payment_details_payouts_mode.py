"""
Payouts-mode (RAZORPAY_ROUTE_ENABLED=False) onboarding: submitting the payment
details form must NOT create a Razorpay linked account (no client.account.create)
— bank details on file are enough. It SHOULD pre-create the RazorpayX payout
destination (ensure_payout_destination) and redirect to the profile page.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User


@override_settings(RAZORPAY_ROUTE_ENABLED=False)
class TestPaymentDetailsPayoutsMode(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="perf.payouts", password="pass123", email="p@artkhoj.local"
        )
        self.profile = self.user.profile
        self.profile.is_performer = True
        self.profile.save()
        self.client.force_login(self.user)

        self.url = reverse("update-payment-details")
        self.valid_post = {
            "performer_fee": "2000",
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Performer Payouts",
        }

    @patch("bookings.services.razorpay_client.get_client")
    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_form_pre_creates_destination_not_linked_account(
        self, mock_ensure, mock_get_client
    ):
        resp = self.client.post(self.url, self.valid_post, follow=False)

        # Redirects back to the profile dashboard.
        self.assertEqual(resp.status_code, 302)
        self.assertIn("profile", resp.url)

        # Payouts mode: no Route linked-account creation.
        mock_get_client.assert_not_called()
        # But the RazorpayX destination IS pre-created.
        mock_ensure.assert_called_once()

        # Details were persisted.
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bank_account_number, "1234567890")
        self.assertEqual(self.profile.bank_ifsc, "HDFC0001234")

    @patch("bookings.services.razorpay_client.get_client")
    @patch(
        "bookings.services.payments.PaymentService.ensure_payout_destination",
        side_effect=Exception("bad IFSC"),
    )
    def test_destination_failure_is_non_fatal(self, mock_ensure, mock_get_client):
        # A failing destination pre-creation must still save details + redirect.
        resp = self.client.post(self.url, self.valid_post, follow=False)
        self.assertEqual(resp.status_code, 302)
        mock_get_client.assert_not_called()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.bank_account_number, "1234567890")
