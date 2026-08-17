import tempfile
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Engagement
from users.models import Profile, Upload

_TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=_TEMP_MEDIA)
class TestProfileDetailWebIntegration(TestCase):
    """GET /users/profile/<id>/ — public profile page for another user."""

    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user("rahul", password="testpass")
        self.client.login(username="rahul", password="testpass")

        self.priya = User.objects.create_user(
            "priya", email="priya@example.com", password="testpass"
        )
        Profile.objects.filter(user=self.priya).update(
            profession="Dancer",
            location="Mumbai",
            bio="Classical dancer from Mumbai",
            is_performer=True,
            performer_fee=5000,
            pan_number="ABCDE1234F",
            bank_account_number="1234567890",
            bank_ifsc="HDFC0001234",
            bank_account_holder_name="Priya Secret",
            phone_number="9876543210",
            razorpay_account_id="acc_leak123",
            razorpay_kyc_status="approved",
            performer_blacklisted=True,
            client_blacklisted=True,
        )

    def _url(self):
        return f"/users/profile/{self.priya.id}/"

    def _seed_gig_mix(self):
        def gig(status, days_from_today):
            return Engagement.objects.create(
                client=self.viewer,
                performer=self.priya,
                date=date.today() + timedelta(days=days_from_today),
                time=time(19, 0),
                venue=f"venue-{status}-{abs(days_from_today)}",
                occasion="Gig",
                status=status,
            )

        old = gig(Engagement.STATUS_ACCEPTED, -30)
        recent = gig(Engagement.STATUS_ACCEPTED, -5)
        pending_past = gig(Engagement.STATUS_PENDING, -10)
        future_accepted = gig(Engagement.STATUS_ACCEPTED, 10)
        return old, recent, pending_past, future_accepted

    def test_nonexistent_user_404(self):
        resp = self.client.get("/users/profile/999999/")
        self.assertEqual(resp.status_code, 404)

    def test_gigs_count_only_counts_accepted_past(self):
        self._seed_gig_mix()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["gigs_count"], 2)

    def test_last_engagement_is_most_recent_accepted_past(self):
        old, recent, pending_past, future_accepted = self._seed_gig_mix()
        resp = self.client.get(self._url())
        self.assertEqual(resp.context["last_engagement"].pk, recent.pk)
        self.assertContains(resp, recent.venue)
        self.assertNotContains(resp, old.venue)
        self.assertNotContains(resp, pending_past.venue)
        self.assertNotContains(resp, future_accepted.venue)

    def test_uploads_newest_first_capped_at_20(self):
        now = timezone.now()
        profile = Profile.objects.get(user=self.priya)
        created = Upload.objects.bulk_create(
            Upload(
                profile=profile,
                image=f"uploads/gig_{i:02d}.jpg",
                caption=f"Work {i:02d}",
            )
            for i in range(25)
        )
        for i, up in enumerate(created):
            Upload.objects.filter(pk=up.pk).update(upload_date=now - timedelta(days=i))
        resp = self.client.get(self._url())
        uploads = resp.context["uploads"]
        self.assertEqual(len(uploads), 20)
        dates = [u.upload_date for u in uploads]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(uploads[0].caption, "Work 00")
        self.assertEqual(uploads[19].caption, "Work 19")
        self.assertLess(resp.content.index(b"Work 00"), resp.content.index(b"Work 19"))
        self.assertEqual(resp.content.count(b'class="upload-card"'), 20)

    def test_no_uploads_empty_state(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No uploads yet")

    def test_no_private_fields_leaked(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "priya")
        self.assertContains(resp, "Dancer")
        self.assertContains(resp, "Classical dancer from Mumbai")
        for private in (
            "priya@example.com",
            "ABCDE1234F",
            "1234567890",
            "HDFC0001234",
            "Priya Secret",
            "9876543210",
            "acc_leak123",
            "approved",
            "performer_blacklisted",
            "client_blacklisted",
        ):
            self.assertNotContains(resp, private)
