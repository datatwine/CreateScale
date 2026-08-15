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

    def _create_artist(self, username, profession):
        user = User.objects.create_user(username, password="testpass")
        Profile.objects.filter(user=user).update(profession=profession)
        return user

    def _card_count(self, resp):
        return resp.content.count(b'class="performer-card"')

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

    def test_clear_filter_restores_all_profiles(self):
        self.client.get("/users/global-feed/", {"professions": "Dancer"})
        resp = self.client.get("/users/global-feed/")
        self.assertContains(resp, "alice")
        self.assertContains(resp, "bob")
        self.assertNotContains(resp, "viewer")

    def test_pagination_page1_20_page2_5(self):
        # 25 profiles total (viewer + alice + bob + 22 musicians). The feed is
        # cached under a shared key WITHOUT self-exclusion, so paginator.count
        # includes the viewer; their own card is simply hidden in the template.
        for i in range(22):
            self._create_artist(f"artist{i}", "Musician")
        p1 = self.client.get("/users/global-feed/")
        self.assertEqual(p1.status_code, 200)
        self.assertEqual(len(p1.context["profiles"].object_list), 20)
        self.assertContains(p1, "25 artists on stage")
        self.assertNotContains(p1, "viewer")
        p2 = self.client.get("/users/global-feed/", {"page": "2"})
        self.assertEqual(p2.status_code, 200)
        self.assertEqual(len(p2.context["profiles"].object_list), 5)

    def test_page_999_clamps_to_last_page(self):
        for i in range(22):
            self._create_artist(f"artist{i}", "Musician")
        resp = self.client.get("/users/global-feed/", {"page": "999"})
        self.assertEqual(resp.status_code, 200)
        # Last page holds the 5 artists — the viewer sits on page 1.
        self.assertEqual(self._card_count(resp), 5)
        self.assertContains(resp, "Page 2 of 2")

    def test_cache_does_not_leak_between_users(self):
        rahul = User.objects.create_user("rahul", password="testpass")

        self.client.get("/users/global-feed/")

        self.client.logout()
        self.client.login(username="rahul", password="testpass")
        resp = self.client.get("/users/global-feed/")

        self.assertContains(resp, "viewer")
        self.assertNotContains(resp, "rahul")

    def test_search_by_username_partial(self):
        resp = self.client.get("/users/global-feed/", {"search": "ali"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_search_by_profession_partial(self):
        resp = self.client.get("/users/global-feed/", {"search": "danc"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_search_by_city_partial(self):
        resp = self.client.get("/users/global-feed/", {"search": "del"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "bob")
        self.assertNotContains(resp, "alice")

    def test_search_is_case_insensitive(self):
        resp = self.client.get("/users/global-feed/", {"search": "MUMBAI"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_search_combines_with_profession_filter(self):
        # search matches alice (Mumbai dancer); filter must exclude her
        resp = self.client.get(
            "/users/global-feed/",
            {"search": "mum", "professions": "Singer"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_search_combines_with_profession_filter_match(self):
        resp = self.client.get(
            "/users/global-feed/",
            {"search": "mum", "professions": "Dancer"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertNotContains(resp, "bob")

    def test_empty_search_returns_full_feed(self):
        resp = self.client.get("/users/global-feed/", {"search": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alice")
        self.assertContains(resp, "bob")

    def test_no_results_empty_state_mentions_search(self):
        resp = self.client.get("/users/global-feed/", {"search": "zzznomatch"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No artists found")
        self.assertContains(resp, 'No results for "zzznomatch"')

    def test_search_bar_renders(self):
        resp = self.client.get("/users/global-feed/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Search by name, profession, or city...")

    def test_clear_button_renders_when_search_active(self):
        resp = self.client.get("/users/global-feed/", {"search": "ali"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-label="Clear search"')

    def test_search_preserved_in_pagination_links(self):
        # 21 profiles/page-1 + matches → forces a second page with pagination
        for i in range(21):
            User.objects.create_user(f"artist{i}", password="testpass")
        resp = self.client.get("/users/global-feed/", {"search": "artist"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Next &rarr;")
        self.assertContains(resp, "&search=artist")

    def test_profession_pills_preserve_search(self):
        resp = self.client.get("/users/global-feed/", {"search": "ali"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "?professions=Dancer&search=ali")
        self.assertContains(resp, "?search=ali")

    def test_search_pills_with_pill_active_preserve_both(self):
        resp = self.client.get(
            "/users/global-feed/",
            {"search": "mum", "professions": "Dancer"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "&search=mum")
