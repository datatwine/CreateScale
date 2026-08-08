"""
TDD — written BEFORE implementation (issue #69, Part 1a).

PATCH /api/users/me/payment/ — the Expo equivalent of the web
update_payment_details view. Mirrors its dual-mode branching:
  Payouts mode (RAZORPAY_ROUTE_ENABLED=False, default): complete bank
    details are enough; pre-creates the RazorpayX Contact + Fund Account.
  Route mode (RAZORPAY_ROUTE_ENABLED=True): creates a Razorpay linked
    account and sets kyc_status="pending".
Both onboarding calls are non-fatal on failure — details stay saved.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

URL = "/api/users/me/payment/"

VALID_PAYLOAD = {
    "performer_fee": 2000,
    "phone_number": "9876543210",
    "pan_number": "ABCDE1234F",
    "bank_account_number": "1234567890",
    "bank_ifsc": "HDFC0001234",
    "bank_account_holder_name": "Performer One",
}


def _make_performer(username):
    u = User.objects.create_user(
        username, password="x", email=f"{username}@artkhoj.local"
    )
    u.profile.is_performer = True
    u.profile.save()
    return u, u.profile


@pytest.mark.django_db
class TestPaymentDetailsAuth:
    def test_requires_authentication(self):
        api = APIClient()
        r = api.patch(URL, VALID_PAYLOAD, format="json")
        assert r.status_code == 401


@pytest.mark.django_db
class TestPaymentDetailsValidation:
    def setup_method(self):
        self.api = APIClient()

    def test_fee_below_minimum_rejected(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_fee_low")
        self.api.force_authenticate(user=user)
        r = self.api.patch(URL, {**VALID_PAYLOAD, "performer_fee": 100}, format="json")
        assert r.status_code == 400
        assert "performer_fee" in r.data

    def test_fee_above_maximum_rejected(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_fee_high")
        self.api.force_authenticate(user=user)
        r = self.api.patch(
            URL, {**VALID_PAYLOAD, "performer_fee": 1000000}, format="json"
        )
        assert r.status_code == 400
        assert "performer_fee" in r.data

    def test_invalid_phone_rejected(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_bad_phone")
        self.api.force_authenticate(user=user)
        r = self.api.patch(
            URL, {**VALID_PAYLOAD, "phone_number": "12345"}, format="json"
        )
        assert r.status_code == 400
        assert "phone_number" in r.data

    def test_invalid_pan_rejected(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_bad_pan")
        self.api.force_authenticate(user=user)
        r = self.api.patch(
            URL, {**VALID_PAYLOAD, "pan_number": "notapan"}, format="json"
        )
        assert r.status_code == 400
        assert "pan_number" in r.data

    def test_invalid_ifsc_rejected(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_bad_ifsc")
        self.api.force_authenticate(user=user)
        r = self.api.patch(URL, {**VALID_PAYLOAD, "bank_ifsc": "bad"}, format="json")
        assert r.status_code == 400
        assert "bank_ifsc" in r.data


@pytest.mark.django_db
class TestPaymentDetailsPayoutsMode:
    """RAZORPAY_ROUTE_ENABLED=False (default/active mode)."""

    def setup_method(self):
        self.api = APIClient()

    @patch("bookings.services.razorpay_client.get_client")
    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_saves_fields_and_pre_creates_destination(
        self, mock_ensure, mock_get_client, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_performer("perf_payouts_ok")
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        profile.refresh_from_db()
        assert profile.bank_account_number == "1234567890"
        assert profile.bank_ifsc == "HDFC0001234"
        assert profile.performer_fee == 2000
        mock_get_client.assert_not_called()
        mock_ensure.assert_called_once()

    @patch("bookings.services.razorpay_client.get_client")
    @patch(
        "bookings.services.payments.PaymentService.ensure_payout_destination",
        side_effect=Exception("bad IFSC"),
    )
    def test_destination_failure_is_non_fatal(
        self, mock_ensure, mock_get_client, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_performer("perf_payouts_fail")
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        profile.refresh_from_db()
        assert profile.bank_account_number == "1234567890"
        # Failure must surface as a warning, not a silent 200 (review Flag 1).
        assert "warnings" in r.data
        assert len(r.data["warnings"]) >= 1

    @patch("bookings.services.razorpay_client.get_client")
    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_no_warnings_key_on_success(self, mock_ensure, mock_get_client, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_payouts_clean")
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        assert "warnings" not in r.data

    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_does_not_re_onboard_when_fund_account_already_exists(
        self, mock_ensure, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_performer("perf_payouts_idempotent")
        profile.razorpayx_fund_account_id = "fa_existing"
        profile.save()
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        mock_ensure.assert_not_called()

    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_does_not_onboard_non_performers(self, mock_ensure, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user = User.objects.create_user("client_only", password="x")
        user.profile.is_performer = False
        user.profile.save()
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        mock_ensure.assert_not_called()

    @patch("bookings.services.payments.PaymentService.ensure_payout_destination")
    def test_response_includes_can_receive_payments(self, mock_ensure, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, _ = _make_performer("perf_payouts_response")
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        assert r.data["can_receive_payments"] is True


@pytest.mark.django_db
class TestPaymentDetailsRouteMode:
    """RAZORPAY_ROUTE_ENABLED=True (dormant, kept working for the future)."""

    def setup_method(self):
        self.api = APIClient()

    @patch("bookings.services.razorpay_client.get_client")
    def test_creates_linked_account_when_fields_complete(
        self, mock_get_client, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = True
        mock_get_client.return_value.account.create.return_value = {"id": "acc_new123"}
        user, profile = _make_performer("perf_route_ok")
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        profile.refresh_from_db()
        assert profile.razorpay_account_id == "acc_new123"
        assert profile.razorpay_kyc_status == "pending"

    @patch("bookings.services.razorpay_client.get_client")
    def test_does_not_re_onboard_when_account_already_exists(
        self, mock_get_client, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = True
        user, profile = _make_performer("perf_route_idempotent")
        profile.razorpay_account_id = "acc_existing"
        profile.save()
        self.api.force_authenticate(user=user)

        r = self.api.patch(URL, VALID_PAYLOAD, format="json")

        assert r.status_code == 200
        mock_get_client.return_value.account.create.assert_not_called()
