"""
Route-mode KYC onboarding integration tests: POST /users/settings/payment/.

Covers the full view path (users.views.update_payment_details +
users.forms.PaymentDetailsForm) with the Razorpay linked-account call mocked.
Razorpay's Account API is intercepted at bookings.services.razorpay_client
(the module the view lazily imports get_client() from) — no real API calls.

Idempotency guards and field validation are unit-tested elsewhere
(test_onboarding_idempotent.py, test_*_validation.py); this file focuses on
the view integration + the mocked account.create() call itself.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import Profile


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test_secret",
)
class TestKYCOnboardingIntegration(TestCase):
    """POST /users/settings/payment/ — Razorpay linked account creation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="ravi", password="testpass", email="ravi@artkhoj.local"
        )
        Profile.objects.filter(user=self.user).update(
            is_performer=True,
            performer_fee=None,
            razorpay_account_id="",
            razorpay_kyc_status="",
        )
        self.client.force_login(self.user)

        self.url = reverse("update-payment-details")
        self.valid_post = {
            "performer_fee": "2000",
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Ravi Sharma",
        }

        self.mock_rzp = MagicMock()
        self.mock_rzp.account.create.return_value = {"id": "acc_test_ravi"}

    def _post(self, data=None, follow=False):
        return self.client.post(self.url, data or self.valid_post, follow=follow)

    def _messages(self, response):
        return [str(m.message) for m in list(response.context["messages"])]

    # ── Happy path ─────────────────────────────────────────────────────
    def test_first_submission_creates_linked_account(self):
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post()

        # 302 = redirect back to the profile dashboard after success.
        self.assertEqual(resp.status_code, 302)
        self.assertIn("profile", resp.url)

        profile = Profile.objects.get(user=self.user)
        # The id Razorpay returned is stored on the profile.
        self.assertEqual(profile.razorpay_account_id, "acc_test_ravi")
        # KYC starts as "pending" — RBI review happens in 5-7 days.
        self.assertEqual(profile.razorpay_kyc_status, "pending")
        # Fee was snapshotted from the form.
        self.assertEqual(profile.performer_fee, 2000)

        # account.create() was called exactly once with the right payload.
        self.mock_rzp.account.create.assert_called_once()
        called_with = self.mock_rzp.account.create.call_args[0][0]
        self.assertEqual(called_with["type"], "route")
        self.assertEqual(called_with["reference_id"], f"user_{self.user.id}")
        self.assertEqual(called_with["legal_info"]["pan"], "ABCDE1234F")
        self.assertEqual(called_with["profile"]["category"], "ecommerce")

    def test_success_message_mentions_kyc_review(self):
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post(follow=True)
        self.assertIn("KYC", " ".join(self._messages(resp)))

    # ── Razorpay failure ────────────────────────────────────────────────
    def test_razorpay_exception_keeps_details_and_allows_retry(self):
        self.mock_rzp.account.create.side_effect = ConnectionError("API down")
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post(follow=True)

        # Followed the redirect → landed on the profile dashboard (200).
        self.assertEqual(resp.status_code, 200)
        # The page shows an onboarding-failure message, not a 500 crash page.
        joined = " ".join(self._messages(resp))
        self.assertIn("onboarding failed", joined.lower())

        profile = Profile.objects.get(user=self.user)
        # Ravi's typed details survive the Razorpay blip.
        self.assertEqual(profile.pan_number, "ABCDE1234F")
        self.assertEqual(profile.bank_account_number, "1234567890")
        self.assertEqual(profile.bank_ifsc, "HDFC0001234")
        self.assertEqual(profile.phone_number, "9876543210")
        self.assertEqual(profile.performer_fee, 2000)
        # No account id -> the next Save retries onboarding.
        self.assertEqual(profile.razorpay_account_id, "")

    def test_unconfigured_client_is_non_fatal(self):
        # get_client() itself raising (missing creds) must behave like any
        # other onboarding failure — details saved, no crash.
        with patch(
            "bookings.services.razorpay_client.get_client",
            side_effect=RuntimeError("Razorpay is not configured."),
        ):
            resp = self._post(follow=True)

        self.assertEqual(resp.status_code, 200)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.bank_account_number, "1234567890")
        self.assertEqual(profile.razorpay_account_id, "")

    # ── Auth ────────────────────────────────────────────────────────────
    def test_anonymous_get_redirected_to_login(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_anonymous_post_redirected_to_login(self):
        self.client.logout()
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)
        # Nothing processed, no Razorpay call.
        self.mock_rzp.account.create.assert_not_called()

    # ── Guard clauses ───────────────────────────────────────────────────
    def test_non_performer_skips_onboarding(self):
        Profile.objects.filter(user=self.user).update(is_performer=False)
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post()

        self.assertEqual(resp.status_code, 302)
        self.mock_rzp.account.create.assert_not_called()
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.razorpay_account_id, "")

    def test_resubmit_after_onboarding_is_idempotent(self):
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            self._post()  # first submit creates the account
            self._post()  # re-submit must NOT create a second one

        self.mock_rzp.account.create.assert_called_once()
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.razorpay_account_id, "acc_test_ravi")

    def test_partial_fields_skip_onboarding_but_save(self):
        data = dict(self.valid_post)
        data["bank_account_number"] = ""
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post(data=data)

        self.assertEqual(resp.status_code, 302)
        self.mock_rzp.account.create.assert_not_called()
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.pan_number, "ABCDE1234F")  # saved anyway
        self.assertEqual(profile.razorpay_account_id, "")

    # ── Validation ──────────────────────────────────────────────────────
    def test_invalid_form_data_rerenders_with_errors(self):
        data = dict(self.valid_post)
        data["pan_number"] = "12345"  # invalid PAN format
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            resp = self._post(data=data)

        # 200 = form re-rendered with validation errors.
        self.assertEqual(resp.status_code, 200)
        self.mock_rzp.account.create.assert_not_called()
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.pan_number, "")  # nothing persisted
        self.assertEqual(profile.razorpay_account_id, "")

    def test_case_normalization_uppercases_pan_and_ifsc(self):
        data = dict(self.valid_post)
        data["pan_number"] = "abcde1234f"
        data["bank_ifsc"] = "hdfc0001234"
        with patch(
            "bookings.services.razorpay_client.get_client", return_value=self.mock_rzp
        ):
            self._post(data=data)

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.pan_number, "ABCDE1234F")
        self.assertEqual(profile.bank_ifsc, "HDFC0001234")
        # The uppercased PAN is what goes to Razorpay's legal_info.
        called_with = self.mock_rzp.account.create.call_args[0][0]
        self.assertEqual(called_with["legal_info"]["pan"], "ABCDE1234F")
