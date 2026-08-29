from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from django.test import TestCase

from users.models import Profile


class TestFeedSearchAPI(TestCase):
    """GET /api/users/feed/?search=... — trigram search across name/profession/city."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.viewer = User.objects.create_user("viewer", password="testpass")
        self.token = Token.objects.create(user=self.viewer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.artist1 = User.objects.create_user("alice", password="testpass")
        Profile.objects.filter(user=self.artist1).update(
            profession="Dancer", location="Mumbai"
        )

        self.artist2 = User.objects.create_user("bob", password="testpass")
        Profile.objects.filter(user=self.artist2).update(
            profession="Singer", location="Delhi"
        )

    def _usernames(self, payload):
        return {p["username"] for p in payload["results"]}

    def _get(self, **params):
        return self.client.get("/api/users/feed/", params)

    def test_search_by_username_partial(self):
        resp = self._get(search="ali")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"alice"})

    def test_search_by_profession_partial(self):
        resp = self._get(search="danc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"alice"})

    def test_search_by_city_partial(self):
        resp = self._get(search="del")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"bob"})

    def test_search_is_case_insensitive(self):
        resp = self._get(search="MUMBAI")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"alice"})

    def test_search_combines_with_profession_filter(self):
        resp = self._get(search="mum", profession="Singer")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), set())

    def test_search_combines_with_profession_filter_match(self):
        resp = self._get(search="mum", profession="Dancer")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"alice"})

    def test_empty_search_returns_full_feed(self):
        resp = self._get(search="")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._usernames(resp.json()), {"alice", "bob"})

    def test_no_results_returns_empty_list(self):
        resp = self._get(search="zzznomatch")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)
        self.assertEqual(self._usernames(resp.json()), set())

    def test_excludes_requesting_user(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("viewer", self._usernames(resp.json()))

    def test_location_exposed_in_serializer(self):
        resp = self._get(search="ali")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"][0]["location"], "Mumbai")

    def test_search_respects_pagination(self):
        # 21 matches → page 1 of 20 + a second page with 1 result
        for i in range(21):
            User.objects.create_user(f"artist{i}", password="testpass")
        resp = self._get(search="artist")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 20)
        self.assertTrue(resp.json()["has_next"])

        page2 = self._get(search="artist", page=2)
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(len(page2.json()["results"]), 1)
