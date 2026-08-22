from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase

from bookings.models import Engagement


class TestEngagementDashboardsIntegration(TestCase):
    """GET /bookings/client/ + /bookings/performer/ — ownership, badges, empty state."""

    def setUp(self):
        self.amit = User.objects.create_user("amit", password="testpass")
        self.priya = User.objects.create_user("priya", password="testpass")
        self.suresh = User.objects.create_user("suresh", password="testpass")
        self.other_performer = User.objects.create_user(
            "otherperf", password="testpass"
        )

    def _gig(self, client, performer, status, venue, occasion="Gig"):
        return Engagement.objects.create(
            client=client,
            performer=performer,
            date=date.today() + timedelta(days=1),
            time=time(19, 0),
            venue=venue,
            occasion=occasion,
            status=status,
        )

    def test_login_required(self):
        for url in ("/bookings/client/", "/bookings/performer/"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/users/login/", resp.url)

    def test_client_sees_only_own_requests(self):
        own = self._gig(
            self.amit,
            self.priya,
            Engagement.STATUS_ACCEPTED,
            "venue-amit-hires-priya",
        )
        other = self._gig(
            self.suresh,
            self.priya,
            Engagement.STATUS_ACCEPTED,
            "venue-suresh-hires-priya",
        )
        amit_as_performer = self._gig(
            self.priya,
            self.amit,
            Engagement.STATUS_ACCEPTED,
            "venue-priya-hires-amit",
        )
        self.client.force_login(self.amit)
        resp = self.client.get("/bookings/client/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([e.pk for e in resp.context["engagements"]], [own.pk])
        self.assertContains(resp, own.venue)
        self.assertNotContains(resp, other.venue)
        self.assertNotContains(resp, amit_as_performer.venue)

    def test_performer_sees_only_own_gigs(self):
        g1 = self._gig(self.amit, self.priya, Engagement.STATUS_PENDING, "venue-gig1")
        g2 = self._gig(
            self.suresh, self.priya, Engagement.STATUS_ACCEPTED, "venue-gig2"
        )
        not_theirs = self._gig(
            self.amit,
            self.other_performer,
            Engagement.STATUS_ACCEPTED,
            "venue-others",
        )
        self.client.force_login(self.priya)
        resp = self.client.get("/bookings/performer/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual({e.pk for e in resp.context["engagements"]}, {g1.pk, g2.pk})
        self.assertContains(resp, g1.venue)
        self.assertContains(resp, g2.venue)
        self.assertNotContains(resp, not_theirs.venue)

    def test_pending_badge_matches_status(self):
        self._gig(self.amit, self.priya, Engagement.STATUS_PENDING, "venue-pending")
        self.client.force_login(self.amit)
        resp = self.client.get("/bookings/client/")
        e = resp.context["engagements"][0]
        self.assertEqual(e.filter_bucket, "pending")
        self.assertEqual(e.badge_label, "Pending")
        self.assertEqual(e.badge_class, "status-pending")
        self.assertContains(resp, 'data-status="pending"')
        self.assertContains(resp, "Pending")

    def test_accepted_badge_matches_status(self):
        self._gig(self.amit, self.priya, Engagement.STATUS_ACCEPTED, "venue-accepted")
        self.client.force_login(self.amit)
        resp = self.client.get("/bookings/client/")
        e = resp.context["engagements"][0]
        self.assertEqual(e.filter_bucket, "accepted")
        self.assertEqual(e.badge_label, "Accepted")
        self.assertEqual(e.badge_class, "status-accepted")
        self.assertContains(resp, 'data-status="accepted"')

    def test_terminal_statuses_bucket_other(self):
        table = {
            Engagement.STATUS_DECLINED: ("Declined", "status-declined"),
            Engagement.STATUS_CANCELLED_CLIENT: ("Cancelled", "status-cancelled"),
            Engagement.STATUS_CANCELLED_PERFORMER: ("Cancelled", "status-cancelled"),
            Engagement.STATUS_AUTO_EXPIRED: ("Expired", "status-expired"),
        }
        self.client.force_login(self.amit)
        for status, (label, cls) in table.items():
            venue = f"venue-{status}"
            gig = self._gig(self.amit, self.priya, status, venue)
            resp = self.client.get("/bookings/client/")
            by_pk = {e.pk: e for e in resp.context["engagements"]}
            e = by_pk[gig.pk]
            self.assertEqual(e.filter_bucket, "other", status)
            self.assertEqual(e.badge_label, label, status)
            self.assertEqual(e.badge_class, cls, status)
            self.assertContains(resp, 'data-status="other"')

    def test_performer_is_pending_flags(self):
        pending_gig = self._gig(
            self.amit,
            self.priya,
            Engagement.STATUS_PENDING,
            "venue-pending-pf",
        )
        self._gig(
            self.suresh,
            self.priya,
            Engagement.STATUS_ACCEPTED,
            "venue-accepted-pf",
        )
        self.client.force_login(self.priya)
        resp = self.client.get("/bookings/performer/")
        by_pk = {e.pk: e for e in resp.context["engagements"]}
        self.assertTrue(by_pk[pending_gig.pk].is_pending)
        self.assertFalse(by_pk[pending_gig.pk].is_inactive)
        self.assertContains(resp, "Respond within 24h")

    def test_client_empty_state(self):
        self.client.force_login(self.amit)
        resp = self.client.get("/bookings/client/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["engagements"], [])
        self.assertContains(resp, "No hire requests yet")

    def test_performer_empty_state(self):
        self.client.force_login(self.priya)
        resp = self.client.get("/bookings/performer/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["engagements"], [])
        self.assertContains(resp, "Your spotlight is ready")
