"""
Tests for POST /api/users/push-token/ (RegisterPushTokenView).

Called by the Expo app on every launch to register the device's push token.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from users.models import PushToken

PUSH_TOKEN_URL = "/api/users/push-token/"


@pytest.fixture
def user(db):
    return User.objects.create_user("device.owner", password="x")


@pytest.fixture
def auth_client(user):
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class TestRegisterPushTokenView:
    def test_requires_authentication(self, db):
        client = APIClient()
        resp = client.post(
            PUSH_TOKEN_URL,
            {"token": "ExponentPushToken[abc123]"},
            format="json",
        )
        assert resp.status_code == 401

    def test_registers_new_token(self, auth_client, user):
        resp = auth_client.post(
            PUSH_TOKEN_URL,
            {"token": "ExponentPushToken[abc123]"},
            format="json",
        )
        assert resp.status_code == 201
        assert PushToken.objects.filter(
            user=user, token="ExponentPushToken[abc123]"
        ).exists()

    def test_rejects_malformed_token(self, auth_client):
        resp = auth_client.post(
            PUSH_TOKEN_URL, {"token": "not-a-real-token"}, format="json"
        )
        assert resp.status_code == 400
        assert PushToken.objects.count() == 0

    def test_reregistering_same_token_moves_it_to_new_user(self, auth_client, user):
        other_user = User.objects.create_user("previous.owner", password="x")
        PushToken.objects.create(
            user=other_user, token="ExponentPushToken[shared_device]"
        )

        resp = auth_client.post(
            PUSH_TOKEN_URL,
            {"token": "ExponentPushToken[shared_device]"},
            format="json",
        )

        assert resp.status_code == 201
        assert PushToken.objects.count() == 1
        token_row = PushToken.objects.get(token="ExponentPushToken[shared_device]")
        assert token_row.user == user
