from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from bookings.models import Engagement


class TestAcceptAPIIntegration(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_user(
        self,
        username,
        role="performer",
        profession="Saxophonist",
        location="Mumbai",
        performer_fee=5000.00,
    ):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.profession = profession
        profile.location = location
        if role == "performer":
            profile.is_performer = True
            profile.performer_fee = performer_fee
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

    def _action(self, engagement_id, action, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return self.client.post(
            f"/api/bookings/engagements/{engagement_id}/action/",
            {"action": action},
            format="json",
        )

    def test_performer_accepts_engagement(self):
        performer, performer_token = self._create_user("performer.ace")
        client_user, client_token = self._create_user("client.fan", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "accept", performer_token)
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "accepted")

    def test_performer_accept_auto_cancels_same_date_pending(self):
        performer, performer_token = self._create_user("busy.pro")
        client_a, token_a = self._create_user("client.a", role="client")
        client_b, token_b = self._create_user("client.b", role="client")

        eng_a = self._hire(performer, performer_token, token_a)
        eng_b = self._hire(performer, performer_token, token_b)

        resp = self._action(eng_a, "accept", performer_token)
        self.assertEqual(resp.status_code, 200)

        eng_a = Engagement.objects.get(id=eng_a)
        self.assertEqual(eng_a.status, "accepted")

        eng_b = Engagement.objects.get(id=eng_b)
        self.assertEqual(eng_b.status, "cancelled_performer")

    def test_performer_accept_fails_after_24h(self):
        performer, performer_token = self._create_user("slow.poke")
        client_user, client_token = self._create_user("client.keen", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        Engagement.objects.filter(id=eng_id).update(
            created_at="2023-01-01 00:00:00+00:00"
        )

        resp = self._action(eng_id, "accept", performer_token)
        self.assertEqual(resp.status_code, 400)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "auto_expired")

    def test_accept_fails_when_performer_conflict_exists(self):
        performer, performer_token = self._create_user("booked.solid")
        client_a, token_a = self._create_user("client.a", role="client")
        client_b, token_b = self._create_user("client.b", role="client")

        eng_a = self._hire(performer, performer_token, token_a)
        eng_b = self._hire(performer, performer_token, token_b)

        Engagement.objects.filter(id=eng_a).update(status="accepted")

        resp = self._action(eng_b, "accept", performer_token)
        self.assertIn(resp.status_code, (400, 409))

    def test_client_cannot_accept_their_own_engagement(self):
        performer, performer_token = self._create_user("performer.jazz")
        client_user, client_token = self._create_user("client.rush", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "accept", client_token)
        self.assertEqual(resp.status_code, 403)

    def test_double_accept_returns_400(self):
        performer, performer_token = self._create_user("performer.one")
        client_user, client_token = self._create_user("client.one", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "accept", performer_token)
        self.assertEqual(resp.status_code, 200)

        resp = self._action(eng_id, "accept", performer_token)
        self.assertEqual(resp.status_code, 400)
