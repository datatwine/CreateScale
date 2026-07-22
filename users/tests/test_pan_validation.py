from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class TestPANValidation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="panuser", password="pass123")
        self.profile = self.user.profile

    def _set_pan(self, pan):
        self.profile.pan_number = pan
        try:
            self.profile.full_clean()
            return None
        except ValidationError as e:
            return e.message_dict

    def test_valid_pan_ABCDE1234F_passes(self):
        errors = self._set_pan("ABCDE1234F")
        self.assertIsNone(errors)

    def test_valid_pan_lowercase_is_uppercased(self):
        errors = self._set_pan("abcde1234f")
        self.assertIsNone(errors)
        self.assertEqual(self.profile.pan_number, "ABCDE1234F")

    def test_valid_pan_with_spaces_rejected_by_length(self):
        self.profile.pan_number = "  ABCDE1234F  "
        with self.assertRaises(ValidationError):
            self.profile.full_clean()

    def test_pan_too_short_rejected(self):
        errors = self._set_pan("ABCDE1234")
        self.assertIn("pan_number", errors)

    def test_pan_too_long_rejected(self):
        errors = self._set_pan("ABCDE1234FX")
        self.assertIn("pan_number", errors)

    def test_pan_all_digits_rejected(self):
        errors = self._set_pan("1234567890")
        self.assertIn("pan_number", errors)

    def test_pan_all_letters_rejected(self):
        errors = self._set_pan("ABCDEFGHIJ")
        self.assertIn("pan_number", errors)

    def test_pan_wrong_pattern_rejected(self):
        errors = self._set_pan("12345ABCDE")
        self.assertIn("pan_number", errors)

    def test_empty_pan_allowed(self):
        errors = self._set_pan("")
        self.assertIsNone(errors)

    def test_blank_pan_allowed(self):
        self.profile.pan_number = ""
        self.profile.full_clean()
        self.assertEqual(self.profile.pan_number, "")
