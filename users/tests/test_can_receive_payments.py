from django.test import TestCase
from django.contrib.auth.models import User


class TestCanReceivePayments(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pay.user", password="pass123"
        )
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
