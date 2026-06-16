from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from bookings.models import Engagement


class TestDeclineAPIIntegration(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_user(self, username, role="performer", profession="Saxophonist",
                     location="Mumbai", performer_fee=5000.00):
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
        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Jazz gig",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        return resp.data["id"]

    def _action(self, engagement_id, action, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return self.client.post(
            f"/api/bookings/engagements/{engagement_id}/action/",
            {"action": action},
            format="json",
        )

    def test_performer_declines_pending(self):
        performer, performer_token = self._create_user("performer.decline")
        client_user, client_token = self._create_user("client.hopeful", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "decline", performer_token)
        self.assertEqual(resp.status_code, 200)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "declined")

    def test_client_cannot_decline(self):
        performer, performer_token = self._create_user("performer.two")
        client_user, client_token = self._create_user("client.pushy", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        resp = self._action(eng_id, "decline", client_token)
        self.assertEqual(resp.status_code, 403)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "pending")

    def test_decline_accepted_returns_400(self):
        performer, performer_token = self._create_user("performer.three")
        client_user, client_token = self._create_user("client.keen", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        self._action(eng_id, "accept", performer_token)
        resp = self._action(eng_id, "decline", performer_token)
        self.assertEqual(resp.status_code, 400)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "accepted")

    def test_decline_already_declined_returns_400(self):
        performer, performer_token = self._create_user("performer.four")
        client_user, client_token = self._create_user("client.sad", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        self._action(eng_id, "decline", performer_token)
        resp = self._action(eng_id, "decline", performer_token)
        self.assertEqual(resp.status_code, 400)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "declined")

    def test_decline_auto_expired_returns_400(self):
        performer, performer_token = self._create_user("performer.slow")
        client_user, client_token = self._create_user("client.waiting", role="client")
        eng_id = self._hire(performer, performer_token, client_token)

        Engagement.objects.filter(id=eng_id).update(
            created_at="2023-01-01 00:00:00+00:00"
        )

        resp = self._action(eng_id, "decline", performer_token)
        self.assertEqual(resp.status_code, 400)

        eng = Engagement.objects.get(id=eng_id)
        self.assertEqual(eng.status, "auto_expired")
