"""
Dispute integration tests (Route mode).

Client raises an issue within the 24h post-event dispute window. Covers the
window boundaries, reason validation, role gates, and the critical effect:
a disputed engagement is frozen — release_completed_event_payouts skips it so
the escrowed money stays held for admin resolution.

The view reads the clock via bookings.views.timezone.now; the release task via
bookings.tasks.timezone.now. Both are patched to make the window/boundary
tests deterministic.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Engagement, Payment
from bookings.tasks import release_completed_event_payouts
from users.models import Profile


@override_settings(
    RAZORPAY_ROUTE_ENABLED=True,
    RAZORPAY_DISPUTE_WINDOW_HOURS=24,
)
class TestDisputeIntegration(TestCase):
    def setUp(self):
        self.meera = User.objects.create_user("meera", password="testpass")
        Profile.objects.filter(user=self.meera).update(
            is_potential_client=True, client_approved=True
        )
        self.ravi = User.objects.create_user("ravi", password="testpass")
        Profile.objects.filter(user=self.ravi).update(
            is_performer=True,
            performer_fee=2000,
            razorpay_account_id="acc_test123",
            razorpay_kyc_status="approved",
        )

        # Event ended 12h ago (inside the 24h window) by default.
        self.event_end = timezone.make_aware(datetime(2026, 2, 1, 12, 0, 0))
        self.engagement = Engagement.objects.create(
            client=self.meera,
            performer=self.ravi,
            date=self.event_end.date(),
            time=self.event_end.time(),
            venue="V",
            occasion="O",
            fee=2000,
            status=Engagement.STATUS_ACCEPTED,
            payment_status=Engagement.PAYMENT_PAID,
        )
        Payment.objects.create(
            engagement=self.engagement,
            amount=2000,
            razorpay_order_id="order_dis",
            razorpay_payment_id="pay_dis",
            status="captured",
        )

        self.mock_rzp = MagicMock()
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @property
    def dispute_url(self):
        return f"/bookings/engagement/{self.engagement.pk}/dispute/"

    def _now(self, offset_hours):
        return self.event_end + timedelta(hours=offset_hours)

    def _dispute(self, reason="The performer arrived late and the set was cut short."):
        return self.client.post(self.dispute_url, {"dispute_reason": reason})

    # ── Window rules ──────────────────────────────────────────────────
    def test_dispute_within_window_marks_disputed(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, f"/bookings/engagement/{self.engagement.pk}/")

        self.engagement.refresh_from_db()
        self.assertIsNotNone(self.engagement.disputed_at)
        self.assertEqual(
            self.engagement.dispute_reason,
            "The performer arrived late and the set was cut short.",
        )

    def test_dispute_before_event_rejected(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(-1)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)
        self.assertEqual(self.engagement.dispute_reason, "")

    def test_dispute_after_24h_window_rejected(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(25)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)

    def test_dispute_at_exact_window_end_accepted(self):
        # Window is [event_end, event_end + 24h] inclusive on the far side.
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(24)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNotNone(self.engagement.disputed_at)

    # ── Reason boundaries ────────────────────────────────────────────
    def test_dispute_reason_too_short_rejected(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute(reason="Too short")

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)

    def test_dispute_reason_exactly_10_chars_accepted(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute(reason="a" * 10)

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNotNone(self.engagement.disputed_at)

    def test_dispute_reason_too_long_rejected(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute(reason="x" * 1001)

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)

    # ── Preconditions ─────────────────────────────────────────────────
    def test_dispute_requires_paid(self):
        self.engagement.payment_status = Engagement.PAYMENT_UNPAID
        self.engagement.save(update_fields=["payment_status"])

        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)

    def test_dispute_after_money_released_rejected(self):
        # Money already reached the performer — too late to freeze escrow.
        self.engagement.payment_status = Engagement.PAYMENT_RELEASED
        self.engagement.released_at = self.event_end + timedelta(hours=30)
        self.engagement.save(update_fields=["payment_status", "released_at"])

        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertIsNone(self.engagement.disputed_at)

    def test_second_dispute_is_noop(self):
        self.client.force_login(self.meera)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            self._dispute(reason="First issue: equipment was broken.")
        self.engagement.refresh_from_db()
        first = self.engagement.disputed_at

        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute(reason="Second issue raised again.")

        self.assertEqual(resp.status_code, 302)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.disputed_at, first)
        self.assertEqual(
            self.engagement.dispute_reason, "First issue: equipment was broken."
        )

    # ── Role gates ───────────────────────────────────────────────────
    def test_performer_cannot_dispute(self):
        self.client.force_login(self.ravi)
        with patch("bookings.views.timezone.now", return_value=self._now(12)):
            resp = self._dispute()

        self.assertEqual(resp.status_code, 403)

    def test_anonymous_dispute_redirects_to_login(self):
        resp = self._dispute()
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/users/login/", resp.url)

    # ── Freeze effect: disputed money never releases ─────────────────
    def test_disputed_engagement_frozen_from_payout(self):
        # Event ended 48h ago — well past the release window.
        self.engagement.date = (self.event_end - timedelta(hours=48)).date()
        self.engagement.time = (self.event_end - timedelta(hours=48)).time()
        self.engagement.disputed_at = self.event_end - timedelta(hours=36)
        self.engagement.save(update_fields=["date", "time", "disputed_at"])

        fixed_now = timezone.make_aware(datetime(2026, 2, 3, 12, 0, 0))
        with patch("bookings.tasks.timezone.now", return_value=fixed_now):
            count = release_completed_event_payouts()

        self.assertEqual(count, 0)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.payment_status, Engagement.PAYMENT_PAID)
        self.assertIsNone(self.engagement.released_at)
        self.mock_rzp.transfer.edit.assert_not_called()
