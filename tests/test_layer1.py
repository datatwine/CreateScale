"""
tests/test_layer1.py
====================
Layer 1 — Universal Invariant Tests

These tests verify the foundational guarantees that are true for ANY web app
with authentication and CRUD. They do NOT test domain logic (booking statuses,
engagement transitions, pricing, etc.).

WHAT THEY PROTECT:
    1. Auth boundaries — anonymous users can't access protected resources
    2. Credentials — login/logout/token flow works correctly
    3. Ownership isolation — User A can't see/modify User B's data
    4. Feed isolation — you never see yourself in the global feed
    5. Signup guardrails — uniqueness + password validation

WHEN THESE BREAK:
    Only when you intentionally change a fundamental rule. That's exactly
    when you WANT a test to stop you and make you think twice.

MAINTENANCE COST:
    Near zero. These tests don't reference specific UI elements, booking
    statuses, or business rules. They work at the HTTP level.

EXCLUDED ENDPOINTS:
    - /api/users/live-events/ and /users/live-events/
      → These will soon become public. Don't test for auth.
    - /users/send_message/, /users/inbox/, /users/message_thread/
      → Messaging being removed soon. Don't invest in testing it.
"""

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from users.models import Upload, Profile


# =============================================================================
# TEST 1: AUTH BOUNDARY
# =============================================================================
# Principle: Every endpoint marked @login_required or IsAuthenticated
# must reject anonymous requests. If even ONE endpoint accidentally
# becomes public, this test catches it immediately.
#
# Web endpoints return 302 (redirect to login page).
# API endpoints return 401 (Unauthorized JSON response).
# =============================================================================

class AuthBoundaryTests(TestCase):
    """Anonymous users must NEVER access protected resources."""

    def setUp(self):
        # We need at least one user to exist for URL patterns that
        # include <user_id> or <upload_id> in the path.
        self.user = User.objects.create_user(
            "testuser", email="test@test.com", password="TestPass123!"
        )

    # ----------------------------------------------------------------
    # API endpoints (mobile app)
    # ----------------------------------------------------------------
    # These should return 401 for anonymous requests.
    # DRF's TokenAuthentication returns 401, not 302.
    #
    # FORMAT: (HTTP method, URL path, human-readable description)
    # The description appears in error messages to tell you exactly
    # which endpoint failed.
    # ----------------------------------------------------------------

    API_PROTECTED_ENDPOINTS = [
        ("GET",    "/api/auth/me/",              "who-am-I check"),
        ("POST",   "/api/auth/logout/",           "logout"),
        ("GET",    "/api/users/me/",              "own profile read"),
        ("PATCH",  "/api/users/me/",              "own profile update"),
        ("GET",    "/api/users/me/uploads/",       "own uploads list"),
        ("POST",   "/api/users/me/uploads/",       "upload creation"),
        ("DELETE", "/api/users/me/uploads/1/",     "upload deletion"),
        ("GET",    "/api/users/feed/",             "global feed"),
        ("GET",    "/api/users/profiles/1/",       "other user profile"),
        ("GET",    "/api/users/professions/",      "professions list"),
        # EXCLUDED: /api/users/live-events/ — going public soon
    ]

    def test_api_endpoints_reject_anonymous(self):
        """
        Every API endpoint with IsAuthenticated must return 401 for
        requests without a token. Never 200, never 500.

        Uses subTest so if multiple endpoints fail, you see ALL of them
        in one test run (not just the first failure).
        """
        client = APIClient()  # no credentials set — anonymous
        for method, url, desc in self.API_PROTECTED_ENDPOINTS:
            with self.subTest(endpoint=f"{method} {url}", description=desc):
                response = getattr(client, method.lower())(url)
                self.assertEqual(
                    response.status_code, 401,
                    f"{method} {url} ({desc}) returned {response.status_code} "
                    f"for anonymous user — expected 401"
                )

    # ----------------------------------------------------------------
    # Web endpoints (browser)
    # ----------------------------------------------------------------
    # These use @login_required which returns 302 redirect to login.
    # Django's default LOGIN_URL is /accounts/login/.
    #
    # EXCLUDED:
    #   - /users/live-events/ — going public soon
    #   - /users/send_message/, /users/inbox/, /users/message_thread/
    #     — messaging being removed soon
    # ----------------------------------------------------------------

    WEB_PROTECTED_ENDPOINTS = [
        ("GET",  "/users/profile/",              "own profile page"),
        ("GET",  "/users/global-feed/",          "global feed page"),
        ("GET",  "/users/profile/1/",            "other user profile page"),
        # EXCLUDED: messaging endpoints — being removed soon
        # EXCLUDED: /users/live-events/ — going public soon

        # Booking web views — these are important to keep
        ("GET",  "/bookings/hire/1/",            "hire form page"),
        ("GET",  "/bookings/client/",            "client engagements dashboard"),
        ("GET",  "/bookings/performer/",         "performer engagements dashboard"),
        ("GET",  "/bookings/engagement/1/",      "engagement detail page"),
    ]

    def test_web_endpoints_redirect_anonymous_to_login(self):
        """
        Every web view with @login_required must redirect (302) anonymous
        users to the login page. Never 200 (data leak), never 500 (crash).

        We also verify the redirect URL contains '/login' — not some
        random redirect to a 404 or error page.
        """
        client = self.client  # Django's built-in test client, no login
        for method, url, desc in self.WEB_PROTECTED_ENDPOINTS:
            with self.subTest(endpoint=f"{method} {url}", description=desc):
                response = getattr(client, method.lower())(url)
                self.assertEqual(
                    response.status_code, 302,
                    f"{method} {url} ({desc}) returned {response.status_code} "
                    f"for anonymous user — expected 302 redirect to login"
                )
                # Verify it actually redirects to a login page
                self.assertIn(
                    "/login",
                    response.url.lower(),
                    f"{method} {url} redirected to {response.url} "
                    f"instead of login page"
                )


# =============================================================================
# TEST 2: CREDENTIALS
# =============================================================================
# Principle: The login/logout/token flow must work correctly.
# Wrong password → no token. Correct password → token. Logout → token dies.
#
# These tests verify the MECHANISM, not specific users or roles.
# =============================================================================

class CredentialTests(TestCase):
    """Login must validate credentials; logout must invalidate tokens."""

    def setUp(self):
        # Create a user with known credentials for testing
        self.user = User.objects.create_user(
            "creduser",
            email="cred@test.com",
            password="CorrectPass123!",
        )
        self.client = APIClient()

    def test_wrong_password_returns_no_token(self):
        """
        Sending a wrong password must NEVER return a token.
        This is the most basic auth invariant — if this fails,
        anyone can log in as anyone.
        """
        resp = self.client.post("/api/auth/token/", {
            "username": "creduser",
            "password": "WrongPassword999!",
        })
        # Must not be 200
        self.assertNotEqual(resp.status_code, 200)
        # Response body must not contain a token
        self.assertNotIn("token", resp.json())

    def test_nonexistent_user_returns_no_token(self):
        """
        A username that doesn't exist must never produce a token.
        Prevents enumeration attacks from accidentally succeeding.
        """
        resp = self.client.post("/api/auth/token/", {
            "username": "doesnotexist",
            "password": "AnyPassword123!",
        })
        self.assertNotEqual(resp.status_code, 200)
        self.assertNotIn("token", resp.json())

    def test_empty_credentials_returns_no_token(self):
        """
        Empty username/password must be rejected.
        Catches edge cases where empty string passes validation.
        """
        resp = self.client.post("/api/auth/token/", {
            "username": "",
            "password": "",
        })
        self.assertNotEqual(resp.status_code, 200)
        self.assertNotIn("token", resp.json())

    def test_correct_credentials_returns_working_token(self):
        """
        Correct credentials must return a token, and that token
        must actually grant access to protected endpoints.
        Two checks in one: token issuance + token validation.
        """
        # Step 1: Get a token with correct credentials
        resp = self.client.post("/api/auth/token/", {
            "username": "creduser",
            "password": "CorrectPass123!",
        })
        self.assertEqual(resp.status_code, 200)
        token = resp.json().get("token")
        self.assertIsNotNone(token, "Login succeeded but no token in response")

        # Step 2: Use the token to access a protected endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(
            resp.status_code, 200,
            "Token was issued but doesn't grant access to /api/auth/me/"
        )

    def test_logout_kills_the_token(self):
        """
        After logout, the SAME token must stop working.
        If this fails, logout is cosmetic — users think they're
        logged out but their token is still valid forever.
        """
        # Step 1: Login and get a token
        resp = self.client.post("/api/auth/token/", {
            "username": "creduser",
            "password": "CorrectPass123!",
        })
        token = resp.json()["token"]

        # Step 2: Logout (deletes the token from the database)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.client.post("/api/auth/logout/")

        # Step 3: Try using the same token again — must be rejected
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(
            resp.status_code, 401,
            "Token still works after logout — logout is broken"
        )


# =============================================================================
# TEST 3: OWNERSHIP ISOLATION
# =============================================================================
# Principle: User A's private data must NEVER be visible to User B.
#
# This is the most dangerous class of bugs — data leaks between users.
# Three things to test:
#   1. /api/users/me/ returns YOUR profile, not someone else's
#   2. /api/users/me/uploads/ shows only YOUR uploads
#   3. You can't delete another user's uploads
#
# The key code this protects (in users/api/views.py):
#   - MeProfileAPIView.get_object: returns request.user's profile
#   - MyUploadsAPIView.get_queryset: filters by request.user
#   - MyUploadDeleteAPIView.get_queryset: filters by profile__user=request.user
# =============================================================================

class OwnershipIsolationTests(TestCase):
    """User A's data must never leak to User B."""

    def setUp(self):
        # Create two completely separate users
        self.alice = User.objects.create_user(
            "alice", email="alice@test.com", password="AlicePass123!"
        )
        self.bob = User.objects.create_user(
            "bob", email="bob@test.com", password="BobPass123!"
        )

        # Get their auto-created profiles (created by post_save signal)
        self.alice_profile = Profile.objects.get(user=self.alice)
        self.bob_profile = Profile.objects.get(user=self.bob)

        # Alice has an upload; Bob does not
        self.alice_upload = Upload.objects.create(
            profile=self.alice_profile,
            caption="Alice's artwork",
        )

        # Separate API clients for each user (force_authenticate
        # skips the token flow — we already tested that above)
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(self.bob)

    def test_me_endpoint_returns_only_own_profile(self):
        """
        GET /api/users/me/ must return the caller's own data.
        If Alice calls it, she gets Alice. If Bob calls it, he gets Bob.
        Never cross-contamination.
        """
        # Alice's /me/ must say "alice"
        resp = self.alice_client.get("/api/users/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "alice")

        # Bob's /me/ must say "bob"
        resp = self.bob_client.get("/api/users/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "bob")

    def test_uploads_list_shows_only_own(self):
        """
        GET /api/users/me/uploads/ must show ONLY the caller's uploads.
        Bob must see an empty list — not Alice's uploads.
        """
        # Alice sees her upload
        resp = self.alice_client.get("/api/users/me/uploads/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

        # Bob sees nothing — he has no uploads
        resp = self.bob_client.get("/api/users/me/uploads/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            len(resp.json()), 0,
            "Bob can see uploads that don't belong to him"
        )

    def test_cannot_delete_other_users_upload(self):
        """
        DELETE /api/users/me/uploads/<id>/ must reject if the upload
        belongs to another user.

        The key protection is in MyUploadDeleteAPIView.get_queryset():
            Upload.objects.filter(profile__user=self.request.user)
        This scopes the queryset to only the requesting user's uploads.
        DRF then returns 404 because the upload doesn't exist in Bob's
        filtered queryset — not 403, not 204.
        """
        # Bob tries to delete Alice's upload
        resp = self.bob_client.delete(
            f"/api/users/me/uploads/{self.alice_upload.id}/"
        )
        # Should be 404 (not found in Bob's queryset), NEVER 204
        self.assertEqual(
            resp.status_code, 404,
            f"Bob accessed Alice's upload (status {resp.status_code})"
        )

        # Verify the upload still exists in the database
        self.assertTrue(
            Upload.objects.filter(id=self.alice_upload.id).exists(),
            "Alice's upload was deleted by Bob — critical ownership violation"
        )


# =============================================================================
# TEST 4: FEED ISOLATION
# =============================================================================
# Principle: The global feed must NEVER include the requesting user.
#
# The key code (users/api/views.py line 192):
#   Profile.objects.exclude(user=request.user)
#
# If this .exclude() accidentally gets removed during a refactor,
# you'll see yourself in the feed. This test catches that.
# =============================================================================

class FeedIsolationTests(TestCase):
    """You must never appear in your own global feed."""

    def setUp(self):
        # Create the user who will request the feed
        self.user = User.objects.create_user(
            "feeduser", email="feed@test.com", password="FeedPass123!"
        )
        # Create a second user so the feed isn't empty
        self.other = User.objects.create_user(
            "otheruser", email="other@test.com", password="OtherPass123!"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_feed_never_includes_self(self):
        """
        GET /api/users/feed/ must not include the requesting user.
        The feed shows OTHER people, never yourself.
        """
        resp = self.client.get("/api/users/feed/")
        self.assertEqual(resp.status_code, 200)

        # Extract all user_ids from the feed results
        user_ids = [r["user_id"] for r in resp.json()["results"]]

        # The requesting user must NOT appear
        self.assertNotIn(
            self.user.id,
            user_ids,
            "User appeared in their own global feed — "
            "the .exclude(user=request.user) filter is broken"
        )

    def test_feed_does_include_other_users(self):
        """
        Sanity check: the feed should include at least one other user.
        If the feed is always empty, the previous test is meaningless
        (an empty feed trivially passes "doesn't include self").
        """
        resp = self.client.get("/api/users/feed/")
        results = resp.json()["results"]
        self.assertGreater(
            len(results), 0,
            "Feed is empty — there should be at least one other user"
        )


# =============================================================================
# TEST 5: SIGNUP GUARDRAILS
# =============================================================================
# Principle: Signup must enforce uniqueness and password validation.
#
# These prevent:
#   - Duplicate accounts (same username or email)
#   - Weak passwords sneaking past validation
#   - Mismatched password confirmation
#
# The validation code is in users/api/serializers.py (SignupSerializer).
# If someone refactors and accidentally removes a validator, these tests
# will catch it.
# =============================================================================

class SignupGuardrailTests(TestCase):
    """Signup must reject invalid registrations and accept valid ones."""

    def setUp(self):
        # Pre-create a user to test duplicate rejection
        self.existing_user = User.objects.create_user(
            "existinguser",
            email="existing@test.com",
            password="ExistingPass123!",
        )
        self.client = APIClient()

    def test_duplicate_username_rejected(self):
        """
        Registering with an already-taken username must fail.
        If this passes through, you get two users with the same username
        and the login system breaks (which one gets the token?).
        """
        resp = self.client.post("/api/auth/signup/", {
            "username": "existinguser",     # ← already taken
            "email": "new@test.com",
            "password1": "BrandNewPass123!",
            "password2": "BrandNewPass123!",
        })
        self.assertNotEqual(
            resp.status_code, 201,
            "Signup accepted a duplicate username"
        )

    def test_duplicate_email_rejected(self):
        """
        Registering with an already-taken email must fail.
        Prevents the same person from creating multiple accounts.
        """
        resp = self.client.post("/api/auth/signup/", {
            "username": "brandnewuser",
            "email": "existing@test.com",   # ← already taken
            "password1": "BrandNewPass123!",
            "password2": "BrandNewPass123!",
        })
        self.assertNotEqual(
            resp.status_code, 201,
            "Signup accepted a duplicate email"
        )

    def test_mismatched_passwords_rejected(self):
        """
        password1 != password2 must be rejected.
        Prevents users from accidentally setting a password they
        didn't intend (typo in confirmation).
        """
        resp = self.client.post("/api/auth/signup/", {
            "username": "mismatchuser",
            "email": "mismatch@test.com",
            "password1": "FirstPassword123!",
            "password2": "DifferentPassword456!",   # ← doesn't match
        })
        self.assertNotEqual(
            resp.status_code, 201,
            "Signup accepted mismatched passwords"
        )

    def test_valid_signup_returns_token(self):
        """
        A completely valid signup must:
          1. Return 201 (created)
          2. Return a token (so the app can auto-login)
          3. Return a user_id (so the app knows who was created)

        This is the happy path — if this fails, nobody can register.
        """
        resp = self.client.post("/api/auth/signup/", {
            "username": "newvaliduser",
            "email": "valid@test.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("token", data, "Signup succeeded but no token returned")
        self.assertIn("user_id", data, "Signup succeeded but no user_id returned")
