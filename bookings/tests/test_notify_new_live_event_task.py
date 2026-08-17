"""
Tests for the notify_new_live_event Celery task (users/tasks.py).

We call the task function directly (no Celery worker needed).
broadcast_push_notification is monkey-patched so these tests never touch
Expo's API — they only verify the task builds the right call.
"""

from unittest.mock import MagicMock

import pytest

from users.tasks import notify_new_live_event


@pytest.mark.django_db
class TestNotifyNewLiveEvent:
    def test_broadcasts_with_performer_excluded(
        self, engagement, performer_user, monkeypatch
    ):
        mock_broadcast = MagicMock()
        monkeypatch.setattr("users.tasks.broadcast_push_notification", mock_broadcast)

        notify_new_live_event(engagement.pk)

        mock_broadcast.assert_called_once()
        _, kwargs = mock_broadcast.call_args
        assert kwargs["exclude_user"] == performer_user
        assert kwargs["title"] == "New live event!"
        assert engagement.performer.username in kwargs["body"]
        assert engagement.occasion in kwargs["body"]
        assert kwargs["data"] == {"screen": "LiveEvents"}

    def test_missing_engagement_is_a_noop(self, db, monkeypatch):
        mock_broadcast = MagicMock()
        monkeypatch.setattr("users.tasks.broadcast_push_notification", mock_broadcast)

        notify_new_live_event(999999)

        mock_broadcast.assert_not_called()
