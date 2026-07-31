from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User


class ProfanityFilterTest(TestCase):
    """Profession profanity filter — all four entry points."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="filteruser", password="password123"
        )
        self.client.login(username="filteruser", password="password123")

    def test_web_signup_rejects_profane_profession(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "baduser",
                "email": "bad@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "shit",
                "location": "Mumbai",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="baduser").exists())

    def test_web_signup_allows_clean_profession(self):
        self.client.logout()
        response = self.client.post(
            reverse("signup"),
            {
                "username": "gooduser",
                "email": "good@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "Musician",
                "location": "Delhi",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="gooduser").exists())

    def test_web_profile_edit_rejects_profane_profession(self):
        response = self.client.post(
            reverse("profile"),
            {
                "profile_submit": "1",
                "profession": "fuck",
                "location": "Mumbai",
                "bio": "Hello",
                "is_performer": True,
                "is_potential_client": False,
            },
        )
        self.user.profile.refresh_from_db()
        self.assertNotEqual(self.user.profile.profession, "fuck")

    def test_api_signup_rejects_profane_profession(self):
        self.client.logout()
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "apiuser",
                "email": "api@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "ass",
                "location": "Mumbai",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_api_profile_edit_rejects_profane_profession(self):
        from rest_framework.authtoken.models import Token

        token = Token.objects.create(user=self.user)
        response = self.client.patch(
            "/api/users/me/",
            {"profession": "damn shit"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_leetspeak(self):
        self.client.logout()
        response = self.client.post(
            reverse("signup"),
            {
                "username": "leet",
                "email": "leet@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "sh1t",
                "location": "Mumbai",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="leet").exists())

    def test_rejects_masked_profanity(self):
        self.client.logout()
        response = self.client.post(
            reverse("signup"),
            {
                "username": "masked",
                "email": "masked@example.com",
                "password1": "strongpassword123",
                "password2": "strongpassword123",
                "profession": "f**k",
                "location": "Mumbai",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="masked").exists())


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RateLimitTest(TestCase):
    """Verify auth endpoints are throttled at 5 req/min."""

    def test_login_throttled_after_5_attempts(self):
        for i in range(5):
            self.client.post(
                "/api/auth/token/",
                {"username": "noone", "password": f"wrong{i}"},
                content_type="application/json",
            )
        response = self.client.post(
            "/api/auth/token/",
            {"username": "noone", "password": "wrong5"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_signup_throttled_after_5_attempts(self):
        for i in range(5):
            self.client.post(
                "/api/auth/signup/",
                {
                    "username": f"u{i}",
                    "email": f"u{i}@x.com",
                    "password1": "short",
                    "password2": "short",
                },
                content_type="application/json",
            )
        response = self.client.post(
            "/api/auth/signup/",
            {
                "username": "u5",
                "email": "u5@x.com",
                "password1": "short",
                "password2": "short",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)

    def test_login_allows_normal_usage(self):
        """A user trying 3 times should not be throttled."""
        for i in range(3):
            response = self.client.post(
                "/api/auth/token/",
                {"username": "noone", "password": f"wrong{i}"},
                content_type="application/json",
            )
            self.assertNotEqual(response.status_code, 429)

    def test_authenticated_user_has_higher_limit(self):
        """Logged-in users get the global 1000/hour rate, not 5/min."""
        user = User.objects.create_user(username="rateuser", password="password123")
        from rest_framework.authtoken.models import Token

        token = Token.objects.create(user=user)
        for i in range(10):
            response = self.client.get(
                "/api/users/me/",
                HTTP_AUTHORIZATION=f"Token {token.key}",
            )
            self.assertNotEqual(response.status_code, 429)
