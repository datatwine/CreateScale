from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.utils import timezone

from users.models import Message


class TestSendMessageWebIntegration(TestCase):
    """POST /users/send_message/<user_id>/ — send a message to another user."""

    def setUp(self):
        self.sender = User.objects.create_user("sender", password="testpass")
        self.receiver = User.objects.create_user("receiver", password="testpass")
        self.client.login(username="sender", password="testpass")

    def test_send_message_success(self):
        resp = self.client.post(
            f"/users/send_message/{self.receiver.id}/",
            {"content": "Hello, this is a test."},
        )
        self.assertRedirects(resp, f"/users/message_thread/{self.receiver.id}/")
        self.assertTrue(
            Message.objects.filter(
                sender=self.sender,
                recipient=self.receiver,
                content="Hello, this is a test.",
            ).exists()
        )

    def test_send_message_empty_content(self):
        resp = self.client.post(
            f"/users/send_message/{self.receiver.id}/",
            {"content": ""},
        )
        self.assertRedirects(resp, f"/users/profile/{self.receiver.id}/")
        self.assertEqual(Message.objects.count(), 0)
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(
            any("Message content cannot be empty." in str(m) for m in messages)
        )

    def test_send_message_nonexistent_user(self):
        resp = self.client.post(
            "/users/send_message/99999/",
            {"content": "Hello"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_send_message_unauthenticated(self):
        self.client.logout()
        resp = self.client.post(
            f"/users/send_message/{self.receiver.id}/",
            {"content": "Hello"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_send_message_get_redirects(self):
        resp = self.client.get(f"/users/send_message/{self.receiver.id}/")
        self.assertRedirects(resp, f"/users/profile/{self.receiver.id}/")


class TestInboxWebIntegration(TestCase):
    """GET /users/inbox/ — view message threads grouped by conversation."""

    def setUp(self):
        self.user = User.objects.create_user("user", password="testpass")
        self.other = User.objects.create_user("other", password="testpass")
        self.client.login(username="user", password="testpass")

    def test_inbox_authenticated_access(self):
        resp = self.client.get("/users/inbox/")
        self.assertEqual(resp.status_code, 200)

    def test_inbox_unauthenticated_redirect(self):
        self.client.logout()
        resp = self.client.get("/users/inbox/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_inbox_shows_latest_message_per_conversation(self):
        older = Message.objects.create(
            sender=self.user,
            recipient=self.other,
            content="Older",
        )
        newer = Message.objects.create(
            sender=self.user,
            recipient=self.other,
            content="Newer",
        )
        now = timezone.now()
        Message.objects.filter(pk=older.pk).update(timestamp=now - timedelta(minutes=1))
        Message.objects.filter(pk=newer.pk).update(timestamp=now)
        resp = self.client.get("/users/inbox/")
        self.assertContains(resp, "Newer")
        self.assertNotContains(resp, "Older")

    def test_inbox_empty_state(self):
        resp = self.client.get("/users/inbox/")
        self.assertContains(resp, "No messages yet")


class TestMessageThreadWebIntegration(TestCase):
    """GET/POST /users/message_thread/<user_id>/ — conversation with another user."""

    def setUp(self):
        self.user = User.objects.create_user("user", password="testpass")
        self.other = User.objects.create_user("other", password="testpass")
        self.client.login(username="user", password="testpass")

    def test_thread_get_shows_messages(self):
        Message.objects.create(
            sender=self.user, recipient=self.other, content="Hey there"
        )
        Message.objects.create(
            sender=self.other, recipient=self.user, content="Hi back"
        )
        resp = self.client.get(f"/users/message_thread/{self.other.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hey there")
        self.assertContains(resp, "Hi back")

    def test_thread_unauthenticated_redirect(self):
        self.client.logout()
        resp = self.client.get(f"/users/message_thread/{self.other.id}/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_thread_empty_message_not_sent(self):
        resp = self.client.post(
            f"/users/message_thread/{self.other.id}/",
            {"content": ""},
        )
        self.assertRedirects(resp, f"/users/message_thread/{self.other.id}/")
        self.assertEqual(Message.objects.count(), 0)

    def test_thread_empty_state(self):
        resp = self.client.get(f"/users/message_thread/{self.other.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Conversation with other")

    def test_thread_send_message(self):
        resp = self.client.post(
            f"/users/message_thread/{self.other.id}/",
            {"content": "New message via thread"},
        )
        self.assertRedirects(resp, f"/users/message_thread/{self.other.id}/")
        self.assertTrue(
            Message.objects.filter(
                sender=self.user, recipient=self.other, content="New message via thread"
            ).exists()
        )

    def test_thread_nonexistent_user(self):
        resp = self.client.get("/users/message_thread/99999/")
        self.assertEqual(resp.status_code, 404)
