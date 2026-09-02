"""
Tests for POST /api/users/profiles/<user_id>/like/ — toggles the
requesting user's like on the target profile. One endpoint does both
like and unlike: creating the Like row is the like, deleting an existing
one is the unlike.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from users.models import Like

LIKE_URL = "/api/users/profiles/{user_id}/like/"


@pytest.fixture
def liker(db):
    return User.objects.create_user("liker", password="x")


@pytest.fixture
def liked(db):
    return User.objects.create_user("liked", password="x")


@pytest.fixture
def auth_client(liker):
    token = Token.objects.create(user=liker)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class TestLikeToggleAPIView:
    def test_requires_authentication(self, liked, db):
        client = APIClient()
        resp = client.post(LIKE_URL.format(user_id=liked.id), format="json")
        assert resp.status_code == 401

    def test_first_call_likes(self, auth_client, liker, liked):
        resp = auth_client.post(LIKE_URL.format(user_id=liked.id), format="json")

        assert resp.status_code == 200
        assert resp.data["liked_by_me"] is True
        assert resp.data["likes_count"] == 1
        assert Like.objects.filter(user=liker, profile=liked.profile).exists()

    def test_second_call_unlikes(self, auth_client, liker, liked):
        auth_client.post(LIKE_URL.format(user_id=liked.id), format="json")

        resp = auth_client.post(LIKE_URL.format(user_id=liked.id), format="json")

        assert resp.status_code == 200
        assert resp.data["liked_by_me"] is False
        assert resp.data["likes_count"] == 0
        assert not Like.objects.filter(user=liker, profile=liked.profile).exists()

    def test_cannot_like_own_profile(self, auth_client, liker):
        resp = auth_client.post(LIKE_URL.format(user_id=liker.id), format="json")

        assert resp.status_code == 400
        assert Like.objects.count() == 0

    def test_likes_count_reflects_multiple_likers(self, auth_client, liked):
        other = User.objects.create_user("other.liker", password="x")
        other_token = Token.objects.create(user=other)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f"Token {other_token.key}")

        auth_client.post(LIKE_URL.format(user_id=liked.id), format="json")
        resp = other_client.post(LIKE_URL.format(user_id=liked.id), format="json")

        assert resp.data["likes_count"] == 2

    def test_404_for_nonexistent_profile(self, auth_client):
        resp = auth_client.post(LIKE_URL.format(user_id=999999), format="json")
        assert resp.status_code == 404

    def test_invalidates_profile_caches(self, auth_client, liked):
        cache.set(f"profile:{liked.id}", {"stale": True}, 300)
        cache.set(f"web:profile:{liked.id}", {"stale": True}, 300)

        auth_client.post(LIKE_URL.format(user_id=liked.id), format="json")

        assert cache.get(f"profile:{liked.id}") is None
        assert cache.get(f"web:profile:{liked.id}") is None
