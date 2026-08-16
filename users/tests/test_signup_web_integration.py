from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token

from users.models import Profile


class TestSignupWebIntegration(TestCase):
    """POST /users/signup/ — web form registration."""

    def test_valid_signup_creates_user_and_profile(self):
        resp = self.client.post(
            "/users/signup/",
            {
                "username": "testuser",
                "email": "testuser@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "Engineer",
                "location": "New York",
            },
        )
        self.assertRedirects(resp, "/users/profile/")
        self.assertTrue(User.objects.filter(username="testuser").exists())
        user = User.objects.get(username="testuser")
        self.assertEqual(user.profile.profession, "Engineer")
        self.assertEqual(user.profile.location, "New York")

    def test_invalid_signup_missing_fields_shows_form(self):
        resp = self.client.post(
            "/users/signup/",
            {
                "username": "testuser",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="testuser").exists())


class TestSignupWebAuthIntegration(TestCase):
    """POST /users/signup/ — session auth, duplicate/weak/mismatch guards, one-profile."""

    def _payload(self, **overrides):
        data = {
            "username": "deepa",
            "email": "deepa@example.com",
            "password1": "strongpassword123",
            "password2": "strongpassword123",
            "profession": "Musician",
            "location": "Mumbai",
        }
        data.update(overrides)
        return data

    def test_signup_auto_logs_in_with_session_not_token(self):
        resp = self.client.post("/users/signup/", self._payload())
        self.assertRedirects(resp, "/users/profile/")
        user = User.objects.get(username="deepa")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_duplicate_username_rerenders_with_error(self):
        User.objects.create_user(
            "deepa", email="deepa@example.com", password="strongpassword123"
        )
        resp = self.client.post(
            "/users/signup/", self._payload(email="deepa2@example.com")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("username", resp.context["form"].errors)
        self.assertContains(resp, "already exists")
        self.assertEqual(User.objects.filter(username="deepa").count(), 1)
        self.assertEqual(Profile.objects.filter(user__username="deepa").count(), 1)

    def test_duplicate_email_rerenders_with_error_case_insensitive(self):
        User.objects.create_user(
            "original", email="Deepa@Example.com", password="strongpassword123"
        )
        resp = self.client.post(
            "/users/signup/", self._payload(email="DEEPA@EXAMPLE.COM")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["form"].errors)
        self.assertContains(resp, "already exists")
        self.assertFalse(User.objects.filter(username="deepa").exists())
        self.assertEqual(Profile.objects.filter(user__username="original").count(), 1)

    def test_weak_password_rejected(self):
        resp = self.client.post(
            "/users/signup/", self._payload(password1="123", password2="123")
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("password2", resp.context["form"].errors)
        self.assertContains(resp, "too short")
        self.assertFalse(User.objects.filter(username="deepa").exists())

    def test_mismatched_passwords_rejected(self):
        resp = self.client.post(
            "/users/signup/",
            self._payload(
                password1="strongpassword123", password2="adifferentpassword123"
            ),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("password2", resp.context["form"].errors)
        self.assertContains(resp, "didn\u2019t match")
        self.assertFalse(User.objects.filter(username="deepa").exists())

    def test_malformed_and_spam_email_rejected(self):
        for email in ("not-an-email", "hireme@spam.com"):
            resp = self.client.post("/users/signup/", self._payload(email=email))
            self.assertEqual(resp.status_code, 200)
            self.assertIn("email", resp.context["form"].errors)
        self.assertFalse(User.objects.filter(username="deepa").exists())

    def test_signup_creates_exactly_one_profile(self):
        resp = self.client.post("/users/signup/", self._payload())
        self.assertRedirects(resp, "/users/profile/")
        user = User.objects.get(username="deepa")
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
        self.assertEqual(user.profile.profession, "Musician")
        self.assertEqual(user.profile.location, "Mumbai")
