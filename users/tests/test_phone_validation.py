from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from users.models import Profile


class TestPhoneValidation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="phoneuser", password="pass123"
        )
        self.profile = self.user.profile

    def _set_phone(self, phone):
        self.profile.phone_number = phone
        try:
            self.profile.full_clean()
            return None
        except ValidationError as e:
            return e.message_dict

    def test_valid_10_digit_mobile_passes(self):
        errors = self._set_phone("9876543210")
        self.assertIsNone(errors)

    def test_phone_starts_with_5_rejected(self):
        errors = self._set_phone("5123456789")
        self.assertIn("phone_number", errors)

    def test_phone_too_short_rejected(self):
        errors = self._set_phone("987654321")
        self.assertIn("phone_number", errors)

    def test_phone_too_long_rejected(self):
        errors = self._set_phone("98765432100")
        self.assertIn("phone_number", errors)

    def test_phone_with_alphabets_rejected(self):
        errors = self._set_phone("98765ABCDE")
        self.assertIn("phone_number", errors)

    def test_phone_all_zeros_rejected(self):
        errors = self._set_phone("0000000000")
        self.assertIn("phone_number", errors)

    def test_empty_phone_allowed(self):
        errors = self._set_phone("")
        self.assertIsNone(errors)
