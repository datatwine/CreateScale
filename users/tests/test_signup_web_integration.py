from django.contrib.auth.models import User
from django.test import TestCase

class TestSignupWebIntegration(TestCase):
    """POST /users/signup/ — web form registration."""

    def test_valid_signup_creates_user_and_profile(self):
        resp = self.client.post("/users/signup/", {
            "username": "testuser",
            "email": "testuser@example.com",
            "password1": "strongpassword123",
            "password2": "strongpassword123",
            "profession": "Engineer",
            "location": "New York",
        })
        self.assertRedirects(resp, "/users/profile/")
        self.assertTrue(User.objects.filter(username="testuser").exists())
        user = User.objects.get(username="testuser")
        self.assertEqual(user.profile.profession, "Engineer")
        self.assertEqual(user.profile.location, "New York")

    def test_invalid_signup_missing_fields_shows_form(self):
        resp = self.client.post("/users/signup/", {
            "username": "testuser",
            "password1": "strongpassword123",
            "password2": "strongpassword123",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="testuser").exists())