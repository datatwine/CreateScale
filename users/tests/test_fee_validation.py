from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class TestFeeValidation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="feeuser", password="pass123"
        )
        self.profile = self.user.profile

    def _set_fee(self, fee):
        self.profile.performer_fee = fee
        try:
            self.profile.full_clean()
            return None
        except ValidationError as e:
            return e.message_dict

    def test_fee_500_passes(self):
        errors = self._set_fee(500)
        self.assertIsNone(errors)

    def test_fee_500000_passes(self):
        errors = self._set_fee(500000)
        self.assertIsNone(errors)

    def test_fee_25000_passes(self):
        errors = self._set_fee(25000)
        self.assertIsNone(errors)

    def test_fee_below_500_rejected(self):
        errors = self._set_fee(499)
        self.assertIn("performer_fee", errors)

    def test_fee_above_500000_rejected(self):
        errors = self._set_fee(500001)
        self.assertIn("performer_fee", errors)

    def test_fee_zero_rejected(self):
        errors = self._set_fee(0)
        self.assertIn("performer_fee", errors)

    def test_fee_negative_rejected(self):
        errors = self._set_fee(-100)
        self.assertIn("performer_fee", errors)

    def test_null_fee_allowed(self):
        errors = self._set_fee(None)
        self.assertIsNone(errors)
