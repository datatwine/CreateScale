from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from users.models import Profile


class TestIFSCValidation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ifscuser", password="pass123"
        )
        self.profile = self.user.profile

    def _set_ifsc(self, ifsc):
        self.profile.bank_ifsc = ifsc
        try:
            self.profile.full_clean()
            return None
        except ValidationError as e:
            return e.message_dict

    def test_valid_ifsc_HDFC0001234_passes(self):
        errors = self._set_ifsc("HDFC0001234")
        self.assertIsNone(errors)

    def test_valid_ifsc_lowercase_is_uppercased(self):
        errors = self._set_ifsc("hdfc0001234")
        self.assertIsNone(errors)
        self.assertEqual(self.profile.bank_ifsc, "HDFC0001234")

    def test_ifsc_too_short_rejected(self):
        errors = self._set_ifsc("HDFC123")
        self.assertIn("bank_ifsc", errors)

    def test_ifsc_too_long_rejected(self):
        errors = self._set_ifsc("HDFC00012345")
        self.assertIn("bank_ifsc", errors)

    def test_ifsc_wrong_prefix_rejected(self):
        errors = self._set_ifsc("1234HDFC000")
        self.assertIn("bank_ifsc", errors)

    def test_ifsc_no_zero_rejected(self):
        errors = self._set_ifsc("HDFC1234567")
        self.assertIn("bank_ifsc", errors)

    def test_ifsc_special_chars_rejected(self):
        errors = self._set_ifsc("HDFC@001234")
        self.assertIn("bank_ifsc", errors)

    def test_empty_ifsc_allowed(self):
        errors = self._set_ifsc("")
        self.assertIsNone(errors)
