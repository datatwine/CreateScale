"""
TDD — written BEFORE implementation.

likes_count must be visible to everyone viewing a profile (PublicProfileDetailSerializer,
used by the other-user profile view) AND to the profile owner themselves
(MeProfileSerializer, used by the own-profile view). liked_by_me is only
meaningful on the public one — you can't like your own profile.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory

from users.api.serializers import MeProfileSerializer, PublicProfileDetailSerializer
from users.models import Like


@pytest.fixture
def liker(db):
    return User.objects.create_user("liker", password="x")


@pytest.fixture
def liked(db):
    return User.objects.create_user("liked", password="x")


def _request_as(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


class TestPublicProfileDetailSerializerLikes:
    def test_likes_count_zero_when_no_likes(self, liker, liked):
        data = PublicProfileDetailSerializer(
            liked.profile, context={"request": _request_as(liker)}
        ).data
        assert data["likes_count"] == 0
        assert data["liked_by_me"] is False

    def test_likes_count_and_liked_by_me_after_liking(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)

        data = PublicProfileDetailSerializer(
            liked.profile, context={"request": _request_as(liker)}
        ).data
        assert data["likes_count"] == 1
        assert data["liked_by_me"] is True

    def test_liked_by_me_false_for_a_different_viewer(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)
        viewer = User.objects.create_user("viewer", password="x")

        data = PublicProfileDetailSerializer(
            liked.profile, context={"request": _request_as(viewer)}
        ).data
        assert data["likes_count"] == 1
        assert data["liked_by_me"] is False


class TestMeProfileSerializerLikes:
    def test_likes_count_visible_to_owner(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)

        data = MeProfileSerializer(
            liked.profile, context={"request": _request_as(liked)}
        ).data
        assert data["likes_count"] == 1
