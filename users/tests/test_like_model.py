"""
Tests for the Like model — a user liking another user's profile.
Toggleable in the API layer via create/delete; unique_together here is
what makes double-liking from the same user impossible at the DB level.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from users.models import Like


@pytest.fixture
def liker(db):
    return User.objects.create_user("liker", password="x")


@pytest.fixture
def liked(db):
    return User.objects.create_user("liked", password="x")


class TestLikeModel:
    def test_creates_like(self, liker, liked):
        like = Like.objects.create(user=liker, profile=liked.profile)
        assert like.pk is not None
        assert like.user == liker
        assert like.profile == liked.profile
        assert like.created_at is not None

    def test_same_user_cannot_like_same_profile_twice(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)

        with pytest.raises(IntegrityError):
            Like.objects.create(user=liker, profile=liked.profile)

    def test_different_users_can_like_same_profile(self, liked):
        other = User.objects.create_user("other.liker", password="x")
        another = User.objects.create_user("another.liker", password="x")
        Like.objects.create(user=other, profile=liked.profile)
        Like.objects.create(user=another, profile=liked.profile)

        assert Like.objects.filter(profile=liked.profile).count() == 2

    def test_one_user_can_like_multiple_profiles(self, liker):
        first = User.objects.create_user("first.performer", password="x")
        second = User.objects.create_user("second.performer", password="x")
        Like.objects.create(user=liker, profile=first.profile)
        Like.objects.create(user=liker, profile=second.profile)

        assert Like.objects.filter(user=liker).count() == 2

    def test_deleting_liker_deletes_their_likes(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)
        liker.delete()

        assert Like.objects.count() == 0

    def test_deleting_liked_users_profile_deletes_the_like(self, liker, liked):
        Like.objects.create(user=liker, profile=liked.profile)
        liked.delete()  # cascades to Profile, which cascades to Like

        assert Like.objects.count() == 0

    def test_clean_blocks_liking_own_profile(self, liker):
        like = Like(user=liker, profile=liker.profile)
        with pytest.raises(ValidationError):
            like.clean()

    def test_str_includes_both_usernames(self, liker, liked):
        like = Like.objects.create(user=liker, profile=liked.profile)
        assert "liker" in str(like)
        assert "liked" in str(like)
