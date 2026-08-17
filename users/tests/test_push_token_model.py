"""
Tests for the PushToken model — one row per device per user, storing the
Expo push delivery address (ExponentPushToken[...]).
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError

from users.models import PushToken


@pytest.fixture
def user(db):
    return User.objects.create_user("device.owner", password="x")


class TestPushTokenModel:
    def test_creates_token_for_user(self, user):
        token = PushToken.objects.create(user=user, token="ExponentPushToken[abc123]")
        assert token.pk is not None
        assert token.user == user
        assert token.created_at is not None

    def test_user_can_have_multiple_tokens(self, user):
        PushToken.objects.create(user=user, token="ExponentPushToken[device1]")
        PushToken.objects.create(user=user, token="ExponentPushToken[device2]")

        assert PushToken.objects.filter(user=user).count() == 2

    def test_token_value_must_be_unique(self, user):
        PushToken.objects.create(user=user, token="ExponentPushToken[dup]")

        with pytest.raises(IntegrityError):
            PushToken.objects.create(user=user, token="ExponentPushToken[dup]")

    def test_str_includes_username_and_token_prefix(self, user):
        token = PushToken.objects.create(
            user=user, token="ExponentPushToken[abcdefghijklmnopqrstuvwxyz]"
        )
        assert "device.owner" in str(token)
        assert "ExponentPushToken[abcdefghijkl" in str(token)

    def test_deleting_user_deletes_their_tokens(self, user):
        PushToken.objects.create(user=user, token="ExponentPushToken[cascade]")
        user.delete()

        assert PushToken.objects.count() == 0
