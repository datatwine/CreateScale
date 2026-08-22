from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from bookings.models import Engagement


class TestEngagementDetailWebView(TestCase):
    """
    Web-layer tests for bookings.views.engagement_detail — the accept /
    decline / cancel screen. Covers the IDOR gate (total outsiders) and the
    wiring of each action to its model method + flash message + redirect.
    The detailed rule logic (24h block, reason length, terminal states,
    refunds) is already green at the API + model layer and not re-tested.
    """

    def setUp(self):
        self.client = Client()
        self.amit = self._create_user("amit", role="client")
        self.priya = self._create_user("priya", role="performer")
        self.sneha = self._create_user("sneha", role="stranger")
        self.admin = self._create_admin("root.admin")
        self.engagement = self._create_engagement(self.amit, self.priya)

    def _create_user(self, username, role="stranger"):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        if role == "performer":
            profile.is_performer = True
            profile.performer_fee = 5000
        else:
            profile.is_potential_client = True
            profile.client_approved = True
        profile.save()
        return user

    def _create_admin(self, username):
        return User.objects.create_superuser(
            username=username, email=f"{username}@example.com", password="pass123"
        )

    def _create_engagement(self, client, performer):
        return Engagement.objects.create(
            client=client,
            performer=performer,
            date=date.today() + timedelta(days=10),
            time=time(19, 0),
            venue="Test venue",
            occasion="Test occasion",
            fee=5000,
        )

    def _url(self, engagement):
        return reverse("bookings:engagement-detail", args=[engagement.pk])

    def _login(self, user):
        self.client.force_login(user)

    def _post(self, user, action, reason="", follow=False):
        self._login(user)
        data = {"action": action}
        if reason:
            data["cancellation_reason"] = reason
        return self.client.post(self._url(self.engagement), data, follow=follow)

    def _flash_messages(self, resp):
        return [str(m) for m in resp.context["messages"]]

    # --- Web IDOR / access control ---

    def test_stranger_get_403(self):
        # Sneha is a legit, hire-approved user with zero relationship to the
        # booking. The gate keys off client/performer FK membership only.
        self._login(self.sneha)
        resp = self.client.get(self._url(self.engagement))
        self.assertEqual(resp.status_code, 403)

    def test_stranger_post_403(self):
        resp = self._post(self.sneha, "accept")
        self.assertEqual(resp.status_code, 403)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_PENDING)

    def test_client_can_view_own(self):
        self._login(self.amit)
        resp = self.client.get(self._url(self.engagement))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["is_client"])
        self.assertFalse(resp.context["is_performer"])
        self.assertContains(resp, "Test occasion")

    def test_performer_can_view_own(self):
        self._login(self.priya)
        resp = self.client.get(self._url(self.engagement))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["is_performer"])
        self.assertFalse(resp.context["is_client"])

    def test_admin_can_view_any(self):
        self._login(self.admin)
        resp = self.client.get(self._url(self.engagement))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["is_client"])
        self.assertFalse(resp.context["is_performer"])

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self._url(self.engagement))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    def test_nonexistent_pk_404(self):
        self._login(self.amit)
        resp = self.client.get(reverse("bookings:engagement-detail", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    # --- Web action wiring ---

    def test_performer_accept_wired(self):
        resp = self._post(self.priya, "accept", follow=True)
        self.assertRedirects(resp, reverse("bookings:performer-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_ACCEPTED)
        self.assertIn("You accepted this booking.", self._flash_messages(resp))

    def test_performer_decline_wired(self):
        resp = self._post(self.priya, "decline", follow=True)
        self.assertRedirects(resp, reverse("bookings:performer-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_DECLINED)
        self.assertIn("You declined this booking.", self._flash_messages(resp))

    def test_client_cancel_wired(self):
        resp = self._post(
            self.amit,
            "cancel_client",
            reason="I found another performer for the event.",
            follow=True,
        )
        self.assertRedirects(resp, reverse("bookings:client-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_CANCELLED_CLIENT)
        self.assertEqual(self.engagement.cancelled_by, "client")
        self.assertIn("Booking cancelled.", self._flash_messages(resp))

    def test_performer_cancel_wired(self):
        resp = self._post(
            self.priya,
            "cancel_performer",
            reason="I am no longer available on that date.",
            follow=True,
        )
        self.assertRedirects(resp, reverse("bookings:performer-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_CANCELLED_PERFORMER)
        self.assertEqual(self.engagement.cancelled_by, "performer")
        self.assertIn("Booking cancelled.", self._flash_messages(resp))

    # --- Web-layer role scoping of actions ---

    def test_client_posting_accept_is_invalid(self):
        resp = self._post(self.amit, "accept", follow=True)
        self.assertRedirects(resp, reverse("bookings:client-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_PENDING)
        self.assertIn("Invalid action.", self._flash_messages(resp))

    def test_performer_posting_cancel_client_is_invalid(self):
        resp = self._post(
            self.priya,
            "cancel_client",
            reason="A reason that is clearly long enough to be valid.",
            follow=True,
        )
        self.assertRedirects(resp, reverse("bookings:performer-engagements"))
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.STATUS_PENDING)
        self.assertIn("Invalid action.", self._flash_messages(resp))

    def test_admin_post_redirects_admin_index(self):
        resp = self._post(self.admin, "accept", follow=True)
        self.assertRedirects(resp, reverse("admin:index"))
        self.assertIn("Invalid action.", self._flash_messages(resp))


class TestEngagementDetailAPIStranger(TestCase):
    """
    Closes the same stranger-leak gap on the API mirror endpoints
    (retrieve + action in bookings/api/views.py) — no existing test creates
    a total outsider on either layer.
    """

    def setUp(self):
        self.client = APIClient()

    def _create_user(self, username, role="performer"):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        if role == "performer":
            profile.is_performer = True
            profile.performer_fee = 5000
        else:
            profile.is_potential_client = True
            profile.client_approved = True
        profile.save()
        token = Token.objects.create(user=user)
        return user, token

    def _hire(self, performer, performer_token, client_token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")
        resp = self.client.post(
            f"/api/bookings/hire/{performer.id}/",
            {
                "occasion": "Jazz gig",
                "date": str(date.today() + timedelta(days=30)),
                "time": "18:00",
                "venue": "Mumbai",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        return resp.data["id"]

    def test_stranger_cannot_retrieve(self):
        performer, performer_token = self._create_user("performer.jazz")
        client_user, client_token = self._create_user("client.fan", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        stranger, stranger_token = self._create_user("stranger.sneha", role="client")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {stranger_token.key}")
        resp = self.client.get(f"/api/bookings/engagements/{eng_id}/")
        self.assertEqual(resp.status_code, 403)

    def test_stranger_cannot_post_action(self):
        performer, performer_token = self._create_user("performer.jazz2")
        client_user, client_token = self._create_user("client.fan2", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        stranger, stranger_token = self._create_user("stranger.sneha2", role="client")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {stranger_token.key}")
        resp = self.client.post(
            f"/api/bookings/engagements/{eng_id}/action/",
            {"action": "accept"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, Engagement.STATUS_PENDING)
