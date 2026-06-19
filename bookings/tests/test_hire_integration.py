from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from bookings.models import Engagement


class TestHireAPIIntegration(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _create_client(self, username="client_jazz", profession="Event Planner",
                       location="Mumbai"):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.profession = profession
        profile.location = location
        profile.is_potential_client = True
        profile.client_approved = True
        profile.save()
        token = Token.objects.create(user=user)
        return user, token

    def _create_performer(self, username="performer.sax", profession="Saxophonist",
                          location="Mumbai", performer_fee=5000.00):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.profession = profession
        profile.location = location
        profile.is_performer = True
        profile.performer_fee = performer_fee
        profile.save()
        token = Token.objects.create(user=user)
        return user, token

    def _booked_dates(self, start, count=1):
        return [start + timedelta(days=i) for i in range(count)]

    def test_hire_creates_pending_engagement_with_fee(self):
        performer, performer_token = self._create_performer()
        _, client_token = self._create_client()

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Saxophonist for wedding",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")

        eng = Engagement.objects.get(id=resp.data["id"])
        self.assertEqual(eng.fee, 5000.00)
        self.assertEqual(eng.client, User.objects.get(username="client_jazz"))
        self.assertEqual(eng.performer, User.objects.get(username="performer.sax"))

        self.assertIsNotNone(eng.date)

    def test_hire_snapshots_performer_fee_at_hire_time(self):
        performer, _ = self._create_performer(performer_fee=5000.00)

        performer.profile.performer_fee = 7000
        performer.profile.save(update_fields=["performer_fee"])

        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Saxophonist for event",
            "date": str(date.today() + timedelta(days=14)),
            "time": "18:00",
            "venue": "Pune",
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        eng = Engagement.objects.get(id=resp.data["id"])
        self.assertEqual(eng.fee, 7000.00)

    def test_hire_rejected_when_client_is_performer(self):
        performer, performer_token = self._create_performer()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {performer_token.key}")

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Hire myself",
            "date": str(date.today() + timedelta(days=10)),
            "time": "18:00",
            "venue": "Delhi",
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_dual_role_user_cannot_self_hire(self):
        user = User.objects.create_user(
            username="both.roles", email="both@example.com", password="pass123"
        )
        profile = user.profile
        profile.profession = "Saxophonist"
        profile.location = "Mumbai"
        profile.is_performer = True
        profile.performer_fee = 5000.00
        profile.is_potential_client = True
        profile.client_approved = True
        profile.save()
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resp = self.client.post(f"/api/bookings/hire/{user.id}/", {
            "occasion": "Hire myself as dual-role",
            "date": str(date.today() + timedelta(days=10)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_hire_rejected_for_nonexistent_performer(self):
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        resp = self.client.post("/api/bookings/hire/99999/", {
            "role_name": "Ghost performer",
            "date": str(date.today() + timedelta(days=10)),
            "location": "Nowhere",
            "message": "Does not exist",
            "budget": 1000,
        }, format="json")

        self.assertEqual(resp.status_code, 404)

    def test_hire_past_date_is_rejected(self):
        performer, _ = self._create_performer()
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Past gig",
            "date": str(date.today() - timedelta(days=1)),
            "time": "18:00",
            "venue": "History",
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_duplicate_hire_same_client_same_performer_same_date_rejected(self):
        performer, _ = self._create_performer()
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        payload = {
            "occasion": "First request",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", payload, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_allowed_for_different_date(self):
        performer, _ = self._create_performer()
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "First date",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Different date",
            "date": str(date.today() + timedelta(days=31)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_duplicate_allowed_for_different_performer(self):
        performer_a, _ = self._create_performer(username="performer.a")
        performer_b, _ = self._create_performer(username="performer.b")
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        payload = {
            "occasion": "Same date, different performer",
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Mumbai",
        }

        resp = self.client.post(f"/api/bookings/hire/{performer_a.id}/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post(f"/api/bookings/hire/{performer_b.id}/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_hire_capped_at_three_pending_engagements(self):
        performer, _ = self._create_performer()
        _, client_token = self._create_client()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        dates = self._booked_dates(date.today() + timedelta(days=60), count=3)
        for i, d in enumerate(dates):
            resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
                "occasion": f"Gig {i+1}",
                "date": str(d),
                "time": "18:00",
                "venue": "Mumbai",
            }, format="json")
            self.assertEqual(resp.status_code, 201)

        resp = self.client.post(f"/api/bookings/hire/{performer.id}/", {
            "occasion": "Gig 4 — over limit",
            "date": str(date.today() + timedelta(days=90)),
            "time": "18:00",
            "venue": "Mumbai",
        }, format="json")
        self.assertEqual(resp.status_code, 400)