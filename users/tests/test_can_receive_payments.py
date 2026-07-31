from django.test import TestCase, override_settings
from django.contrib.auth.models import User


@override_settings(RAZORPAY_ROUTE_ENABLED=True)
class TestCanReceivePayments(TestCase):
    """Route mode: payable iff linked account exists AND KYC approved."""

    def setUp(self):
        self.user = User.objects.create_user(username="pay.user", password="pass123")
        self.profile = self.user.profile

    def test_false_when_no_account_id(self):
        self.profile.razorpay_account_id = ""
        self.profile.razorpay_kyc_status = "approved"
        self.assertFalse(self.profile.can_receive_payments)

    def test_false_when_kyc_pending(self):
        self.profile.razorpay_account_id = "acc_test123"
        self.profile.razorpay_kyc_status = "pending"
        self.assertFalse(self.profile.can_receive_payments)

    def test_false_when_kyc_rejected(self):
        self.profile.razorpay_account_id = "acc_test123"
        self.profile.razorpay_kyc_status = "rejected"
        self.assertFalse(self.profile.can_receive_payments)

    def test_false_when_both_missing(self):
        self.profile.razorpay_account_id = ""
        self.profile.razorpay_kyc_status = ""
        self.assertFalse(self.profile.can_receive_payments)

    def test_true_when_account_exists_and_kyc_approved(self):
        self.profile.razorpay_account_id = "acc_test123"
        self.profile.razorpay_kyc_status = "approved"
        self.assertTrue(self.profile.can_receive_payments)


@override_settings(RAZORPAY_ROUTE_ENABLED=False)
class TestCanReceivePaymentsPayoutsMode(TestCase):
    """Payouts mode (default): payable iff complete bank details on file; the
    linked account / KYC status is irrelevant."""

    def setUp(self):
        self.user = User.objects.create_user(username="pay.user2", password="pass123")
        self.profile = self.user.profile
        self.profile.bank_account_holder_name = "Performer One"
        self.profile.bank_account_number = "1234567890"
        self.profile.bank_ifsc = "HDFC0001234"

    def test_true_with_bank_details_and_no_linked_account(self):
        self.profile.razorpay_account_id = ""
        self.profile.razorpay_kyc_status = ""
        self.assertTrue(self.profile.can_receive_payments)

    def test_false_when_holder_name_missing(self):
        self.profile.bank_account_holder_name = ""
        self.assertFalse(self.profile.can_receive_payments)

    def test_false_when_account_number_missing(self):
        self.profile.bank_account_number = ""
        self.assertFalse(self.profile.can_receive_payments)

    def test_false_when_ifsc_missing(self):
        self.profile.bank_ifsc = ""
        self.assertFalse(self.profile.can_receive_payments)

    def test_linked_account_alone_is_not_enough(self):
        self.profile.bank_account_holder_name = ""
        self.profile.bank_account_number = ""
        self.profile.bank_ifsc = ""
        self.profile.razorpay_account_id = "acc_test123"
        self.profile.razorpay_kyc_status = "approved"
        self.assertFalse(self.profile.can_receive_payments)
