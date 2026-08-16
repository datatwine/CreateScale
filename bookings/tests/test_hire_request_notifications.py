"""
Tests for the "new hire request" push notification trigger (issue #81,
remaining trigger #3) — must fire from BOTH the web view and the API view,
since they're two independent entry points to the same action.

send_push_notification is monkey-patched in each module it's imported into
so these tests never touch Expo's API.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from django.test import Client as DjangoTestClient
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from bookings.models import Engagement


@pytest.mark.django_db
class TestCreateHireRequestWebNotifies:
    def test_notifies_performer(self, client_user, performer_user, monkeypatch):
        mock_send = MagicMock()
        monkeypatch.setattr("bookings.views.send_push_notification", mock_send)

        web_client = DjangoTestClient()
        web_client.force_login(client_user)
        resp = web_client.post(
            f"/bookings/hire/{performer_user.id}/",
            {
                "occasion": "Wedding sangeet",
                "date": str(date.today() + timedelta(days=20)),
                "time": "19:00",
                "venue": "Mumbai",
            },
        )
        assert resp.status_code in (302, 200)
        assert Engagement.objects.filter(performer=performer_user).exists()

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == performer_user
        assert client_user.username in kwargs["body"]
        assert "Wedding sangeet" in kwargs["body"]


@pytest.mark.django_db
class TestCreateHireRequestAPINotifies:
    def test_notifies_performer(self, client_user, performer_user, monkeypatch):
        mock_send = MagicMock()
        monkeypatch.setattr("bookings.api.views.send_push_notification", mock_send)

        token = Token.objects.create(user=client_user)
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resp = api_client.post(
            f"/api/bookings/hire/{performer_user.id}/",
            {
                "occasion": "Birthday party",
                "date": str(date.today() + timedelta(days=20)),
                "time": "18:00",
                "venue": "Pune",
            },
            format="json",
        )
        assert resp.status_code == 201

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == performer_user
        assert client_user.username in kwargs["body"]
        assert "Birthday party" in kwargs["body"]
