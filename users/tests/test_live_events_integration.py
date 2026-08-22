from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from bookings.models import Engagement


class TestLiveEventsWebIntegration(TestCase):
    """GET /users/live-events/ — upcoming (paginated) + past (capped 20) accepted gigs."""

    def setUp(self):
        cache.clear()
        self.client_user = User.objects.create_user("client", password="testpass")
        self.performer = User.objects.create_user("performer", password="testpass")
        self.client.login(username="client", password="testpass")

    def _gig(
        self,
        day_delta,
        status=Engagement.STATUS_ACCEPTED,
        at=time(12, 0),
        venue="venue-default",
    ):
        return Engagement.objects.create(
            client=self.client_user,
            performer=self.performer,
            date=date.today() + timedelta(days=day_delta),
            time=at,
            venue=venue,
            occasion="Gig",
            status=status,
        )

    def _upcoming_pks(self, resp):
        return [e.pk for e in resp.context["events"]]

    def _past_pks(self, resp):
        return [e.pk for e in resp.context["past_events"]]

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/users/live-events/")
        self.assertRedirects(resp, "/users/login/?next=/users/live-events/")

    def test_accepted_future_and_past_split_correctly(self):
        tomorrow = self._gig(1, venue="venue-tomorrow")
        yesterday = self._gig(-1, venue="venue-yesterday")
        resp = self.client.get("/users/live-events/")
        self.assertIn(tomorrow.pk, self._upcoming_pks(resp))
        self.assertNotIn(yesterday.pk, self._upcoming_pks(resp))
        self.assertIn(yesterday.pk, self._past_pks(resp))
        self.assertNotIn(tomorrow.pk, self._past_pks(resp))

    def test_today_event_counts_as_upcoming_not_past(self):
        today_gig = self._gig(0, venue="venue-today")
        resp = self.client.get("/users/live-events/")
        self.assertIn(today_gig.pk, self._upcoming_pks(resp))
        self.assertNotIn(today_gig.pk, self._past_pks(resp))

    def test_pending_appears_in_neither(self):
        pending = self._gig(1, status=Engagement.STATUS_PENDING, venue="venue-pending")
        resp = self.client.get("/users/live-events/")
        self.assertNotIn(pending.pk, self._upcoming_pks(resp))
        self.assertNotIn(pending.pk, self._past_pks(resp))

    def test_declined_cancelled_expired_never_appear(self):
        declined = self._gig(
            -2, status=Engagement.STATUS_DECLINED, venue="venue-declined"
        )
        cancelled_client = self._gig(
            -3,
            status=Engagement.STATUS_CANCELLED_CLIENT,
            venue="venue-cancelled-client",
        )
        cancelled_performer = self._gig(
            -4,
            status=Engagement.STATUS_CANCELLED_PERFORMER,
            venue="venue-cancelled-performer",
        )
        expired = self._gig(
            -5, status=Engagement.STATUS_AUTO_EXPIRED, venue="venue-expired"
        )
        accepted_then_cancelled = self._gig(1, venue="venue-then-cancelled")
        Engagement.objects.filter(pk=accepted_then_cancelled.pk).update(
            status=Engagement.STATUS_CANCELLED_CLIENT
        )
        resp = self.client.get("/users/live-events/")
        for gig in (
            declined,
            cancelled_client,
            cancelled_performer,
            expired,
            accepted_then_cancelled,
        ):
            self.assertNotIn(gig.pk, self._upcoming_pks(resp))
            self.assertNotIn(gig.pk, self._past_pks(resp))

    def test_15_upcoming_paginated_10_then_5(self):
        for i in range(15):
            self._gig(1, venue=f"gig-p{i:02d}")
        page1 = self.client.get("/users/live-events/")
        self.assertEqual(len(page1.context["events"]), 10)
        paginator = page1.context["page_obj"].paginator
        self.assertEqual(paginator.count, 15)
        self.assertEqual(paginator.num_pages, 2)
        self.assertTrue(page1.context["page_obj"].has_next())
        self.assertFalse(page1.context["page_obj"].has_previous())
        self.assertContains(page1, '<span class="pill-accent">15</span>', html=True)
        page2 = self.client.get("/users/live-events/?page=2")
        self.assertEqual(len(page2.context["events"]), 5)
        self.assertFalse(page2.context["page_obj"].has_next())
        self.assertTrue(page2.context["page_obj"].has_previous())

    def test_upcoming_sorted_by_date_then_time(self):
        late = self._gig(1, at=time(20, 0), venue="venue-late")
        early = self._gig(1, at=time(10, 0), venue="venue-early")
        mid = self._gig(1, at=time(15, 0), venue="venue-mid")
        resp = self.client.get("/users/live-events/")
        self.assertIn(late.pk, self._upcoming_pks(resp))
        self.assertIn(early.pk, self._upcoming_pks(resp))
        self.assertIn(mid.pk, self._upcoming_pks(resp))
        venues = [e.venue for e in resp.context["events"]]
        self.assertEqual(venues, ["venue-early", "venue-mid", "venue-late"])

    def test_past_most_recent_20_no_pagination(self):
        for i in range(25):
            self._gig(-(i + 1), venue=f"past-gig-{i:02d}")
        resp = self.client.get("/users/live-events/")
        past = resp.context["past_events"]
        self.assertEqual(len(past), 20)
        self.assertEqual(
            [e.venue for e in past], [f"past-gig-{i:02d}" for i in range(20)]
        )
        self.assertEqual(self._upcoming_pks(resp), [])
