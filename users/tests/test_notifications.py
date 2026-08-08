"""
Tests for users/notifications.py — send_push_notification (1:1) and
broadcast_push_notification (batched). Expo's API is fully mocked via
monkeypatching requests.post so these tests never touch the network.
"""

from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from users.models import PushToken
from users.notifications import (
    broadcast_push_notification,
    send_push_notification,
)


@pytest.fixture
def user(db):
    return User.objects.create_user("notify.me", password="x")


def _ok_response(results):
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = {"data": results}
    return resp


class TestSendPushNotification:
    def test_no_tokens_is_a_noop(self, user, monkeypatch):
        post = MagicMock()
        monkeypatch.setattr("users.notifications.requests.post", post)

        send_push_notification(user=user, title="Hi", body="There")

        post.assert_not_called()

    def test_sends_one_message_per_device(self, user, monkeypatch):
        PushToken.objects.create(user=user, token="ExponentPushToken[dev1]")
        PushToken.objects.create(user=user, token="ExponentPushToken[dev2]")

        post = MagicMock(
            return_value=_ok_response([{"status": "ok"}, {"status": "ok"}])
        )
        monkeypatch.setattr("users.notifications.requests.post", post)

        send_push_notification(
            user=user,
            title="Booking confirmed!",
            body="Rajath accepted your booking",
            data={"screen": "BookingDetail", "id": 42},
        )

        post.assert_called_once()
        _, kwargs = post.call_args
        sent = kwargs["json"]
        assert len(sent) == 2
        tos = {m["to"] for m in sent}
        assert tos == {"ExponentPushToken[dev1]", "ExponentPushToken[dev2]"}
        assert all(m["title"] == "Booking confirmed!" for m in sent)
        assert all(m["data"] == {"screen": "BookingDetail", "id": 42} for m in sent)

    def test_network_error_is_swallowed(self, user, monkeypatch):
        import requests

        PushToken.objects.create(user=user, token="ExponentPushToken[dev1]")
        monkeypatch.setattr(
            "users.notifications.requests.post",
            MagicMock(side_effect=requests.RequestException("boom")),
        )

        # Should not raise — push notifications are best-effort.
        send_push_notification(user=user, title="Hi", body="There")

    def test_dead_token_is_removed(self, user, monkeypatch):
        PushToken.objects.create(user=user, token="ExponentPushToken[dead]")

        post = MagicMock(
            return_value=_ok_response(
                [
                    {
                        "status": "error",
                        "details": {"error": "DeviceNotRegistered"},
                    }
                ]
            )
        )
        monkeypatch.setattr("users.notifications.requests.post", post)

        send_push_notification(user=user, title="Hi", body="There")

        assert not PushToken.objects.filter(token="ExponentPushToken[dead]").exists()

    def test_live_token_survives_unrelated_error(self, user, monkeypatch):
        PushToken.objects.create(user=user, token="ExponentPushToken[alive]")

        post = MagicMock(
            return_value=_ok_response(
                [{"status": "error", "details": {"error": "MessageTooBig"}}]
            )
        )
        monkeypatch.setattr("users.notifications.requests.post", post)

        send_push_notification(user=user, title="Hi", body="There")

        assert PushToken.objects.filter(token="ExponentPushToken[alive]").exists()


class TestBroadcastPushNotification:
    def test_no_tokens_is_a_noop(self, db, monkeypatch):
        post = MagicMock()
        monkeypatch.setattr("users.notifications.requests.post", post)

        broadcast_push_notification(title="Hi", body="There")

        post.assert_not_called()

    def test_excludes_given_user(self, db, monkeypatch):
        excluded = User.objects.create_user("excluded", password="x")
        included = User.objects.create_user("included", password="x")
        PushToken.objects.create(user=excluded, token="ExponentPushToken[excl]")
        PushToken.objects.create(user=included, token="ExponentPushToken[incl]")

        post = MagicMock(return_value=_ok_response([{"status": "ok"}]))
        monkeypatch.setattr("users.notifications.requests.post", post)

        broadcast_push_notification(
            title="New live event!", body="Someone is performing", exclude_user=excluded
        )

        post.assert_called_once()
        _, kwargs = post.call_args
        tos = {m["to"] for m in kwargs["json"]}
        assert tos == {"ExponentPushToken[incl]"}

    def test_batches_in_chunks_of_100(self, db, monkeypatch):
        users = [User.objects.create_user(f"u{i}", password="x") for i in range(150)]
        for i, u in enumerate(users):
            PushToken.objects.create(user=u, token=f"ExponentPushToken[t{i}]")

        post = MagicMock(return_value=_ok_response([{"status": "ok"}] * 100))
        monkeypatch.setattr("users.notifications.requests.post", post)

        broadcast_push_notification(title="Hi", body="There")

        assert post.call_count == 2
        first_batch = post.call_args_list[0].kwargs["json"]
        second_batch = post.call_args_list[1].kwargs["json"]
        assert len(first_batch) == 100
        assert len(second_batch) == 50

    def test_one_batch_failure_does_not_stop_others(self, db, monkeypatch):
        import requests

        users = [User.objects.create_user(f"v{i}", password="x") for i in range(150)]
        for i, u in enumerate(users):
            PushToken.objects.create(user=u, token=f"ExponentPushToken[v{i}]")

        post = MagicMock(
            side_effect=[
                requests.RequestException("boom"),
                _ok_response([{"status": "ok"}] * 50),
            ]
        )
        monkeypatch.setattr("users.notifications.requests.post", post)

        # Should not raise, and should still attempt the second batch.
        broadcast_push_notification(title="Hi", body="There")

        assert post.call_count == 2
