"""
TDD — written BEFORE implementation (issue #23).

MeProfileSerializer must accept KYC writes (phone, PAN, bank account,
IFSC, account holder name, performer fee) and replicate the Razorpay
linked-account onboarding side effect that
users.views.update_payment_details has today, so PATCH /api/users/me/
becomes the mobile equivalent of the web KYC form.
"""
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from users.api.serializers import MeProfileSerializer
from users.models import Profile


def _make_profile(**overrides):
    user = User.objects.create_user(
        username=overrides.pop("username", "performer_kyc"),
        password="x",
    )
    profile, _ = Profile.objects.update_or_create(
        user=user,
        defaults={"is_performer": True, **overrides},
    )
    user.__dict__.pop("profile", None)
    return profile


@pytest.fixture
def mock_razorpay(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr(
        "bookings.services.razorpay_client.get_client",
        lambda: mock_client,
    )
    return mock_client


@pytest.mark.django_db
class TestMeProfileSerializerKYCWrites:

    def test_accepts_phone_pan_bank_fields(self):
        profile = _make_profile()
        ser = MeProfileSerializer(profile, data={
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Jane Doe",
        }, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()
        assert updated.phone_number == "9876543210"
        assert updated.pan_number == "ABCDE1234F"
        assert updated.bank_account_number == "1234567890"
        assert updated.bank_ifsc == "HDFC0001234"
        assert updated.bank_account_holder_name == "Jane Doe"

    def test_bank_account_number_is_write_only(self):
        profile = _make_profile(bank_account_number="1234567890")
        data = MeProfileSerializer(profile).data
        assert "bank_account_number" not in data
        assert data["bank_account_last4"] == "7890"

    def test_performer_fee_is_now_writable(self):
        profile = _make_profile()
        ser = MeProfileSerializer(profile, data={"performer_fee": 3000}, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()
        assert updated.performer_fee == 3000

    def test_performer_fee_rejects_below_minimum(self):
        profile = _make_profile()
        ser = MeProfileSerializer(profile, data={"performer_fee": 100}, partial=True)
        assert not ser.is_valid()
        assert "performer_fee" in ser.errors

    def test_performer_fee_rejects_above_maximum(self):
        profile = _make_profile()
        ser = MeProfileSerializer(profile, data={"performer_fee": 1000000}, partial=True)
        assert not ser.is_valid()
        assert "performer_fee" in ser.errors


@pytest.mark.django_db
class TestMeProfileSerializerRazorpayOnboarding:

    def test_creates_linked_account_when_all_fields_filled(self, mock_razorpay):
        mock_razorpay.account.create.return_value = {"id": "acc_new123"}
        profile = _make_profile()

        ser = MeProfileSerializer(profile, data={
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Jane Doe",
        }, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()

        mock_razorpay.account.create.assert_called_once()
        assert updated.razorpay_account_id == "acc_new123"
        assert updated.razorpay_kyc_status == "pending"

    def test_does_not_onboard_when_fields_incomplete(self, mock_razorpay):
        profile = _make_profile()
        # Only phone provided — PAN/bank details still missing
        ser = MeProfileSerializer(profile, data={"phone_number": "9876543210"}, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()

        mock_razorpay.account.create.assert_not_called()
        assert updated.razorpay_account_id == ""

    def test_does_not_re_onboard_when_account_already_exists(self, mock_razorpay):
        profile = _make_profile(
            razorpay_account_id="acc_existing",
            razorpay_kyc_status="approved",
            phone_number="9876543210",
            pan_number="ABCDE1234F",
            bank_account_number="1234567890",
            bank_ifsc="HDFC0001234",
            bank_account_holder_name="Jane Doe",
        )
        ser = MeProfileSerializer(profile, data={"bank_ifsc": "ICIC0005678"}, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()

        mock_razorpay.account.create.assert_not_called()
        assert updated.razorpay_account_id == "acc_existing"
        assert updated.razorpay_kyc_status == "approved"

    def test_does_not_onboard_non_performers(self, mock_razorpay):
        profile = _make_profile(is_performer=False, is_potential_client=True)
        ser = MeProfileSerializer(profile, data={
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Jane Doe",
        }, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()

        mock_razorpay.account.create.assert_not_called()
        assert updated.razorpay_account_id == ""

    def test_saves_fields_even_if_razorpay_call_fails(self, mock_razorpay):
        mock_razorpay.account.create.side_effect = Exception("Razorpay is down")
        profile = _make_profile()

        ser = MeProfileSerializer(profile, data={
            "phone_number": "9876543210",
            "pan_number": "ABCDE1234F",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "bank_account_holder_name": "Jane Doe",
        }, partial=True)
        assert ser.is_valid(), ser.errors
        updated = ser.save()

        # Details are saved despite onboarding failure — user can retry
        # without re-entering everything (mirrors update_payment_details).
        assert updated.bank_account_number == "1234567890"
        assert updated.razorpay_account_id == ""
