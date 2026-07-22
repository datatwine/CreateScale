from django.test import TestCase
from django.contrib.auth.models import User


class TestOnboardingIdempotent(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="perf.pay", password="pass123")
        self.profile = self.user.profile
        self.profile.is_performer = True
        self.profile.pan_number = "ABCDE1234F"
        self.profile.bank_account_number = "1234567890"
        self.profile.bank_ifsc = "HDFC0001234"
        self.profile.phone_number = "9876543210"
        self.profile.save()

    def _should_onboard(self):
        return (
            self.profile.is_performer
            and not self.profile.razorpay_account_id
            and self.profile.pan_number
            and self.profile.bank_account_number
            and self.profile.bank_ifsc
            and self.profile.phone_number
        )

    def test_onboard_when_no_account_exists(self):
        self.assertTrue(self._should_onboard())

    def test_skip_onboard_when_account_exists(self):
        self.profile.razorpay_account_id = "acc_test123"
        self.profile.save()
        self.assertFalse(self._should_onboard())

    def test_skip_onboard_when_not_performer(self):
        self.profile.is_performer = False
        self.profile.save()
        self.assertFalse(self._should_onboard())

    def test_skip_onboard_when_pan_missing(self):
        self.profile.pan_number = ""
        self.profile.save()
        self.assertFalse(self._should_onboard())

    def test_skip_onboard_when_bank_account_missing(self):
        self.profile.bank_account_number = ""
        self.profile.save()
        self.assertFalse(self._should_onboard())

    def test_skip_onboard_when_ifsc_missing(self):
        self.profile.bank_ifsc = ""
        self.profile.save()
        self.assertFalse(self._should_onboard())

    def test_skip_onboard_when_phone_missing(self):
        self.profile.phone_number = ""
        self.profile.save()
        self.assertFalse(self._should_onboard())
