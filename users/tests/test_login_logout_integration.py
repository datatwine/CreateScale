from django.contrib.auth.models import User
from django.test import TestCase


class TestSigninWebIntegration(TestCase):
    """GET/POST /users/login/ — session login, open-redirect probe (finding), logout."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rahul", email="rahul@example.com", password="testpass"
        )

    def test_login_page_renders(self):
        resp = self.client.get("/users/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'method="POST"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_credentials_redirect_and_session(self):
        resp = self.client.post(
            "/users/login/",
            {"username": "rahul", "password": "testpass"},
        )
        self.assertRedirects(resp, "/users/profile/")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertIn("sessionid", resp.cookies)
        profile_resp = self.client.get("/users/profile/")
        self.assertEqual(profile_resp.status_code, 200)

    def test_valid_credentials_with_safe_next(self):
        other = User.objects.create_user("deepa", password="testpass")
        resp = self.client.post(
            "/users/login/?next=/users/profile/%d/" % other.pk,
            {"username": "rahul", "password": "testpass"},
        )
        self.assertRedirects(resp, "/users/profile/%d/" % other.pk)

    def test_wrong_password_stays_on_page_with_error(self):
        resp = self.client.post(
            "/users/login/",
            {"username": "rahul", "password": "wrongpass"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_username_same_error(self):
        resp = self.client.post(
            "/users/login/",
            {"username": "nobody", "password": "testpass"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid username or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_open_redirect_next_param_blocked(self):
        """
        Regression guard for the open-redirect fix: signin must validate
        ?next= with url_has_allowed_host_and_scheme. Protocol-relative
        (//evil.com) and absolute (https://evil.com) attacker URLs must NOT
        become the Location header — the user is redirected to their profile
        instead. Legit same-host next URLs still work (see safe_next test).
        """
        for malicious in ("//evil.com", "https://evil.com"):
            resp = self.client.post(
                "/users/login/?next=%s" % malicious,
                {"username": "rahul", "password": "testpass"},
            )
            self.assertEqual(resp.status_code, 302)
            self.assertNotEqual(resp["Location"], malicious)
            self.assertRedirects(resp, "/users/profile/")


class TestLogoutWebIntegration(TestCase):
    """POST /users/logout/ — session teardown + post-logout auth gates."""

    def setUp(self):
        self.user = User.objects.create_user(
            "rahul", email="rahul@example.com", password="testpass"
        )
        self.client.login(username="rahul", password="testpass")

    def test_logout_destroys_session(self):
        resp = self.client.post("/users/logout/")
        self.assertRedirects(resp, "/users/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_after_logout_login_required_bounces(self):
        self.client.post("/users/logout/")
        resp = self.client.get("/users/profile/")
        self.assertRedirects(resp, "/users/login/?next=/users/profile/")

    def test_logout_requires_post(self):
        resp = self.client.get("/users/logout/")
        self.assertEqual(resp.status_code, 405)
