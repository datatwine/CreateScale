from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from users.models import Profile


class TestSignupAPIIntegration(TestCase):
    """API signup → profile creation → auth token."""

    def setUp(self):
        self.client = APIClient()

    def test_valid_signup_returns_token_and_creates_profile(self):
        resp = self.client.post("/api/auth/signup/", {
            "username": "ragav.drums",
            "email": "ragav@example.com",
            "password1": "GrooveOn123!",
            "password2": "GrooveOn123!",
            "profession": "Drummer",
            "location": "Bangalore",
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertIn("token", resp.data)
        self.assertEqual(resp.data["username"], "ragav.drums")
        self.assertIsNotNone(resp.data["user_id"])

        user = User.objects.get(username="ragav.drums")
        self.assertEqual(user.email, "ragav@example.com")

        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.profession, "Drummer")
        self.assertEqual(profile.location, "Bangalore")

        token = resp.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        me_resp = self.client.get("/api/auth/me/")
        self.assertEqual(me_resp.status_code, 200)

    def test_duplicate_username_returns_400(self):
        User.objects.create_user("existing_user", password="SomePass123!")

        resp = self.client.post("/api/auth/signup/", {
            "username": "existing_user",
            "email": "new@example.com",
            "password1": "NewUserPass123!",
            "password2": "NewUserPass123!",
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_returns_400(self):
        User.objects.create_user(
            "some_user", email="dup@example.com", password="SomePass123!"
        )

        resp = self.client.post("/api/auth/signup/", {
            "username": "new_user",
            "email": "dup@example.com",
            "password1": "NewUserPass123!",
            "password2": "NewUserPass123!",
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_mismatched_passwords_returns_400(self):
        resp = self.client.post("/api/auth/signup/", {
            "username": "mismatch_user",
            "email": "match@example.com",
            "password1": "FirstPass123!",
            "password2": "DifferentPass456!",
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(username="mismatch_user").exists())

    def test_missing_fields_returns_400(self):
        resp = self.client.post("/api/auth/signup/", {
            "username": "half_user",
            "password1": "SomePass123!",
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(username="half_user").exists())