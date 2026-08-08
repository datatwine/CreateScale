"""
Tests that Engagement.accept() fires both notifications:
1) a direct "booking confirmed" push to the client
2) a broadcast "new live event" push to everyone else, via Celery

send_push_notification and notify_new_live_event.delay are monkey-patched
so these tests never touch Expo's API or a real Celery broker.
"""

from unittest.mock import MagicMock

import pytest


@pytest.mark.django_db
class TestAcceptNotifications:
    def test_accept_notifies_client_directly(
        self, engagement, client_user, monkeypatch
    ):
        mock_send = MagicMock()
        monkeypatch.setattr("users.notifications.send_push_notification", mock_send)
        monkeypatch.setattr("users.tasks.notify_new_live_event.delay", MagicMock())

        engagement.accept()

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == client_user
        assert kwargs["title"] == "Booking confirmed!"
        assert engagement.performer.username in kwargs["body"]
        assert engagement.occasion in kwargs["body"]
        assert kwargs["data"] == {"screen": "BookingDetail", "id": engagement.pk}

    def test_accept_broadcasts_new_live_event_via_celery(self, engagement, monkeypatch):
        monkeypatch.setattr("users.notifications.send_push_notification", MagicMock())
        mock_delay = MagicMock()
        monkeypatch.setattr("users.tasks.notify_new_live_event.delay", mock_delay)

        engagement.accept()

        mock_delay.assert_called_once_with(engagement.pk)
