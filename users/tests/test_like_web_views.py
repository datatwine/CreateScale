"""
TDD — written BEFORE implementation.

likes_count must appear in the web profile view's own template context too
(users/views.py:profile for the owner, profile_detail for other viewers),
and liked_by_me on profile_detail must be computed PER-VIEWER, outside the
60s shared cache (cache key is profile-only, not viewer-scoped — caching
liked_by_me inside it would leak one viewer's like state to everyone else
who hits the same cached page).
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from users.models import Like


@pytest.fixture
def liker(db):
    return User.objects.create_user("liker", password="x")


@pytest.fixture
def liked(db):
    return User.objects.create_user("liked", password="x")


@pytest.mark.django_db
class TestProfileDetailLikesContext:
    def test_likes_count_and_liked_by_me_in_context(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)

        client = Client()
        client.force_login(liker)
        resp = client.get(f"/users/profile/{liked.id}/")

        assert resp.context["likes_count"] == 1
        assert resp.context["liked_by_me"] is True

    def test_liked_by_me_is_viewer_specific_not_cached_across_viewers(
        self, liker, liked
    ):
        Like.objects.create(user=liker, profile=liked.profile)
        other_viewer = User.objects.create_user("other.viewer", password="x")

        liker_client = Client()
        liker_client.force_login(liker)
        liker_client.get(f"/users/profile/{liked.id}/")  # warms the shared cache

        other_client = Client()
        other_client.force_login(other_viewer)
        resp = other_client.get(f"/users/profile/{liked.id}/")

        # The shared 60s cache must not leak liker's liked_by_me=True onto
        # a different viewer who never liked this profile.
        assert resp.context["liked_by_me"] is False
        assert resp.context["likes_count"] == 1


@pytest.mark.django_db
class TestOwnProfileLikesContext:
    def test_likes_count_visible_to_owner(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)

        client = Client()
        client.force_login(liked)
        resp = client.get("/users/profile/")

        assert resp.context["likes_count"] == 1
