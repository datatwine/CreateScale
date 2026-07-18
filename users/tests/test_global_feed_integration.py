from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from users.models import Profile


class TestGlobalFeedWebIntegration(TestCase):
    """GET /users/global-feed/ — browse and filter artist profiles."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("viewer", password="testpass")
        self.client.login(username="viewer", password="testpass")

        self.artist1 = User.objects.create_user("alice", password="testpass")
        Profile.objects.filter(user=self.artist1).update(
            profession="Dancer", location="Mumbai"
        )

        self.artist2 = User.objects.create_user("bob", password="testpass")
        Profile.objects.filter(user=self.artist2).update(
            profession="Singer", location="Delhi"
        )

    def test_feed_shows_other_profiles_excludes_self(self):
        resp = self.client.get("/users/global-feed/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertContains(resp, "bob")
        self.assertNotContains(resp, "viewer")

    def test_filter_by_profession(self):
        resp = self.client.get("/users/global-feed/", {"professions": "Dancer"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_empty_state_when_no_other_users(self):
        User.objects.exclude(id=self.user.id).delete()
        resp = self.client.get("/users/global-feed/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No artists found")

    def test_unauthenticated_user_gets_redirected_to_login(self):
        self.client.logout()
        resp = self.client.get("/users/global-feed/")
        self.assertRedirects(resp, "/users/login/?next=/users/global-feed/")