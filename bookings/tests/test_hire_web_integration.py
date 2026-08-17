from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages, ERROR, SUCCESS
from django.test import Client, TestCase

from bookings.models import Engagement


class TestHireWebIntegration(TestCase):
    """Web hire flow — bookings.views.create_hire_request (/bookings/hire/<id>/).

    Mirrors the API tests in test_hire_integration.py but drives the browser
    path: redirects + messages.error()/messages.success() instead of JSON
    error bodies. The three client approval gates (toggle / admin approval /
    blacklist) are only testable here — the API tests hard-code them on.
    """

    def setUp(self):
        self.client = Client()

    def _create_client(
        self,
        username="amit",
        *,
        is_potential_client=True,
        client_approved=True,
        client_blacklisted=False,
    ):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.is_potential_client = is_potential_client
        profile.client_approved = client_approved
        profile.client_blacklisted = client_blacklisted
        profile.save()
        return user

    def _create_performer(
        self,
        username="priya",
        *,
        is_performer=True,
        performer_blacklisted=False,
        performer_fee=5000.00,
    ):
        user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass123"
        )
        profile = user.profile
        profile.is_performer = is_performer
        profile.performer_blacklisted = performer_blacklisted
        profile.performer_fee = performer_fee
        profile.save()
        return user

    def _hire_url(self, performer_id):
        return f"/bookings/hire/{performer_id}/"

    def _payload(self, **overrides):
        payload = {
            "date": str(date.today() + timedelta(days=30)),
            "time": "18:00",
            "venue": "Grand Palace, Mumbai",
            "occasion": "Wedding performance",
        }
        payload.update(overrides)
        return payload

    def _messages(self, resp):
        return list(get_messages(resp.wsgi_request))

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def test_anonymous_post_redirected_to_login(self):
        performer = self._create_performer()
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)
        self.assertEqual(Engagement.objects.count(), 0)

    # ------------------------------------------------------------------
    # Client approval gates
    # ------------------------------------------------------------------
    def test_toggle_off_blocked(self):
        performer = self._create_performer()
        client = self._create_client(is_potential_client=False, client_approved=False)
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/users/profile/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]),
            "Turn on the 'I hire performers' toggle on your profile before sending requests.",
        )
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_toggle_off_blocked_even_when_approved(self):
        performer = self._create_performer()
        client = self._create_client(is_potential_client=False, client_approved=True)
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/users/profile/")
        messages = self._messages(resp)
        self.assertIn("'I hire performers' toggle", str(messages[0]))
        self.assertEqual(Engagement.objects.count(), 0)

    def test_not_approved_blocked(self):
        performer = self._create_performer()
        client = self._create_client(is_potential_client=True, client_approved=False)
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/users/profile/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]),
            "Admin has not approved you for hiring performers yet.",
        )
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_blacklisted_blocked(self):
        performer = self._create_performer()
        client = self._create_client(
            is_potential_client=True, client_approved=True, client_blacklisted=True
        )
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/users/profile/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]), "You are currently blocked from hiring performers."
        )
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_blacklisted_but_not_approved_gets_approval_message(self):
        # Approval gate runs before the blacklist gate, so a blacklisted user
        # who was never approved sees the approval message first.
        performer = self._create_performer()
        client = self._create_client(
            is_potential_client=True, client_approved=False, client_blacklisted=True
        )
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/users/profile/")
        messages = self._messages(resp)
        self.assertIn("not approved you for hiring", str(messages[0]))
        self.assertEqual(Engagement.objects.count(), 0)

    def test_gates_run_on_get_too(self):
        performer = self._create_performer()
        client = self._create_client(is_potential_client=False)
        self.client.force_login(client)
        resp = self.client.get(self._hire_url(performer.id))
        self.assertRedirects(resp, "/users/profile/")

    # ------------------------------------------------------------------
    # Performer availability gate
    # ------------------------------------------------------------------
    def test_non_performer_target_blocked(self):
        target = self._create_client(username="target")  # not a performer
        client = self._create_client(username="amit2")
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(target.id), self._payload())
        self.assertRedirects(resp, f"/users/profile/{target.id}/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            str(messages[0]), "This user is not available for hire right now."
        )
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_blacklisted_performer_blocked(self):
        performer = self._create_performer(performer_blacklisted=True)
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, f"/users/profile/{performer.id}/")
        messages = self._messages(resp)
        self.assertEqual(
            str(messages[0]), "This user is not available for hire right now."
        )
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_performer_gate_runs_on_get_too(self):
        target = self._create_client(username="target")
        client = self._create_client(username="amit3")
        self.client.force_login(client)
        resp = self.client.get(self._hire_url(target.id))
        self.assertRedirects(resp, f"/users/profile/{target.id}/")

    # ------------------------------------------------------------------
    # Self-hire
    # ------------------------------------------------------------------
    def test_self_hire_blocked(self):
        performer = self._create_performer()
        self.client.force_login(performer)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, f"/users/profile/{performer.id}/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "You can't hire yourself.")
        self.assertEqual(messages[0].level, ERROR)
        self.assertEqual(Engagement.objects.count(), 0)

    def test_dual_role_self_hire_blocked(self):
        user = self._create_performer(username="both.roles")
        profile = user.profile
        profile.is_potential_client = True
        profile.client_approved = True
        profile.save()
        self.client.force_login(user)
        resp = self.client.post(self._hire_url(user.id), self._payload())
        self.assertRedirects(resp, f"/users/profile/{user.id}/")
        messages = self._messages(resp)
        self.assertEqual(str(messages[0]), "You can't hire yourself.")
        self.assertEqual(Engagement.objects.count(), 0)

    def test_dual_role_user_can_hire_another_performer(self):
        performer = self._create_performer()
        user = self._create_performer(username="both.roles")
        profile = user.profile
        profile.is_potential_client = True
        profile.client_approved = True
        profile.save()
        self.client.force_login(user)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/bookings/client/")
        self.assertEqual(Engagement.objects.count(), 1)

    # ------------------------------------------------------------------
    # Nonexistent performer
    # ------------------------------------------------------------------
    def test_nonexistent_performer_404(self):
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(99999), self._payload())
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(Engagement.objects.count(), 0)

    # ------------------------------------------------------------------
    # GET form rendering
    # ------------------------------------------------------------------
    def test_get_renders_hire_form(self):
        performer = self._create_performer()
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.get(self._hire_url(performer.id))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bookings/hire_form.html")
        self.assertContains(resp, "priya")

    # ------------------------------------------------------------------
    # POST with invalid form data
    # ------------------------------------------------------------------
    def test_post_invalid_form_rerenders_with_field_errors(self):
        performer = self._create_performer()
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.post(
            self._hire_url(performer.id),
            {"date": "", "time": "", "venue": "", "occasion": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bookings/hire_form.html")
        self.assertTrue(resp.context["form"].errors)
        self.assertEqual(Engagement.objects.count(), 0)

    # ------------------------------------------------------------------
    # Model rules surfaced through the web view (re-render + flash)
    # ------------------------------------------------------------------
    def test_post_past_date_rerenders_with_flash(self):
        performer = self._create_performer()
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.post(
            self._hire_url(performer.id),
            self._payload(date=str(date.today() - timedelta(days=1))),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bookings/hire_form.html")
        messages = self._messages(resp)
        self.assertTrue(any("Cannot book for a past date." in str(m) for m in messages))
        self.assertEqual(Engagement.objects.count(), 0)

    def test_post_duplicate_date_rerenders_with_flash(self):
        performer = self._create_performer()
        client = self._create_client()
        payload = self._payload()
        Engagement.objects.create(
            client=client,
            performer=performer,
            date=payload["date"],
            time=payload["time"],
            venue=payload["venue"],
            occasion=payload["occasion"],
        )
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bookings/hire_form.html")
        messages = self._messages(resp)
        self.assertTrue(
            any(
                "You already have a request for this performer on that date." in str(m)
                for m in messages
            )
        )
        self.assertEqual(Engagement.objects.count(), 1)

    def test_post_cap_3_rerenders_with_flash(self):
        performer = self._create_performer()
        client = self._create_client()
        for i in range(3):
            Engagement.objects.create(
                client=client,
                performer=performer,
                date=date.today() + timedelta(days=60 + i),
                time="18:00",
                venue="Mumbai",
                occasion=f"Gig {i + 1}",
            )
        self.client.force_login(client)
        resp = self.client.post(
            self._hire_url(performer.id),
            self._payload(date=str(date.today() + timedelta(days=90))),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "bookings/hire_form.html")
        messages = self._messages(resp)
        self.assertTrue(
            any("You already have 3 ongoing bookings." in str(m) for m in messages)
        )
        self.assertEqual(Engagement.objects.count(), 3)

    def test_post_creates_engagement_when_performer_fee_is_none(self):
        performer = self._create_performer(performer_fee=None)
        client = self._create_client()
        self.client.force_login(client)
        resp = self.client.post(self._hire_url(performer.id), self._payload())
        self.assertRedirects(resp, "/bookings/client/")
        engagement = Engagement.objects.get(client=client, performer=performer)
        self.assertIsNone(engagement.fee)

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------
    def test_post_success_creates_pending_engagement(self):
        performer = self._create_performer(performer_fee=5000.00)
        client = self._create_client()
        self.client.force_login(client)
        payload = self._payload()
        resp = self.client.post(self._hire_url(performer.id), payload)
        self.assertRedirects(resp, "/bookings/client/")
        messages = self._messages(resp)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Hiring request sent.")
        self.assertEqual(messages[0].level, SUCCESS)

        engagement = Engagement.objects.get(client=client, performer=performer)
        self.assertEqual(engagement.status, Engagement.STATUS_PENDING)
        self.assertEqual(engagement.payment_status, Engagement.PAYMENT_UNPAID)
        self.assertEqual(engagement.fee, 5000.00)
        self.assertEqual(engagement.date, date.fromisoformat(payload["date"]))
        self.assertEqual(engagement.time, time.fromisoformat(payload["time"]))
        self.assertEqual(engagement.venue, payload["venue"])
        self.assertEqual(engagement.occasion, payload["occasion"])

    def test_post_success_snapshots_fee_at_hire_time(self):
        performer = self._create_performer(performer_fee=5000.00)
        client = self._create_client()
        self.client.force_login(client)
        self.client.post(self._hire_url(performer.id), self._payload())

        performer.profile.performer_fee = 7000
        performer.profile.save(update_fields=["performer_fee"])

        engagement = Engagement.objects.get(client=client, performer=performer)
        self.assertEqual(engagement.fee, 5000.00)
