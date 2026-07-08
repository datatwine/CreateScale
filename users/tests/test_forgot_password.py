from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient


class TestForgotPasswordAPIIntegration(TestCase):
    """POST /api/auth/forgot-password/"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="test.performer",
            email="performer@example.com",
            password="OldPass123!",
        )

    def test_valid_email_sends_email_and_returns_200(self):
        resp = self.client.post("/api/auth/forgot-password/", {
            "email": "performer@example.com",
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("detail", resp.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("performer@example.com", mail.outbox[0].to)

    def test_unknown_email_returns_400_not_found(self):
        resp = self.client.post("/api/auth/forgot-password/", {
            "email": "nobody@example.com",
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_case_insensitive_email_match(self):
        resp = self.client.post("/api/auth/forgot-password/", {
            "email": "Performer@Example.com",
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_invalid_email_format_returns_400(self):
        resp = self.client.post("/api/auth/forgot-password/", {
            "email": "not-an-email",
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_empty_email_returns_400(self):
        resp = self.client.post("/api/auth/forgot-password/", {
            "email": "",
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_missing_email_field_returns_400(self):
        resp = self.client.post("/api/auth/forgot-password/", {}, format="json")

        self.assertEqual(resp.status_code, 400)


class TestPasswordResetWebFlow(TestCase):
    """Web password reset views."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reset.user",
            email="reset@example.com",
            password="CurrentPass123!",
        )

    def test_password_reset_form_page_loads(self):
        resp = self.client.get("/users/password-reset/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "email")

    def test_password_reset_submit_sends_email(self):
        resp = self.client.post("/users/password-reset/", {"email": "reset@example.com"})
        self.assertRedirects(resp, "/users/password-reset/done/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)

    def test_password_reset_submit_unknown_email_shows_error(self):
        resp = self.client.post("/users/password-reset/", {"email": "unknown@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No account found")
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_done_page_loads(self):
        resp = self.client.get("/users/password-reset/done/")
        self.assertEqual(resp.status_code, 200)

    def _reset_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        return uid, token

    def _visit_confirm_form(self):
        """GET the token URL, follow the redirect, and return the clean set-password URL."""
        uid, token = self._reset_url()
        resp = self.client.get(f"/users/password-reset/{uid}/{token}/")
        self.assertEqual(resp.status_code, 302)
        clean_url = resp.url
        resp = self.client.get(clean_url)
        self.assertEqual(resp.status_code, 200)
        return clean_url

    def test_password_reset_confirm_with_valid_token(self):
        clean_url = self._visit_confirm_form()

        resp = self.client.post(clean_url, {
            "new_password1": "NewStr0ng!Pass",
            "new_password2": "NewStr0ng!Pass",
        })
        self.assertRedirects(resp, "/users/password-reset/complete/")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStr0ng!Pass"))

    def test_password_reset_confirm_same_as_old_password(self):
        clean_url = self._visit_confirm_form()

        resp = self.client.post(clean_url, {
            "new_password1": "CurrentPass123!",
            "new_password2": "CurrentPass123!",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cannot be the same")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("CurrentPass123!"))

    def test_password_reset_confirm_mismatched_passwords(self):
        clean_url = self._visit_confirm_form()

        resp = self.client.post(clean_url, {
            "new_password1": "NewStr0ng!Pass",
            "new_password2": "DifferentPass456!",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "didn")

    def test_password_reset_confirm_weak_password(self):
        clean_url = self._visit_confirm_form()

        resp = self.client.post(clean_url, {
            "new_password1": "12345678",
            "new_password2": "12345678",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "common")

    def test_password_reset_confirm_invalid_token(self):
        resp = self.client.get("/users/password-reset/abc/def/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link expired")

    def test_password_reset_confirm_reused_token(self):
        uid, token = self._reset_url()
        # Complete the full reset flow once
        resp = self.client.get(f"/users/password-reset/{uid}/{token}/")
        self.assertEqual(resp.status_code, 302)
        clean_url = resp.url
        self.client.get(clean_url)
        self.client.post(clean_url, {
            "new_password1": "NewStr0ng!Pass",
            "new_password2": "NewStr0ng!Pass",
        })

        # Now the token has been used — reusing it should show expired
        resp = self.client.get(f"/users/password-reset/{uid}/{token}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link expired")

    def test_password_reset_complete_page_loads(self):
        resp = self.client.get("/users/password-reset/complete/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Password changed")
