"""
Payout release integration tests (Route mode): the real Celery task
release_completed_event_payouts driving the real PaymentService.
release_to_performer — only Razorpay's HTTP is mocked (at
bookings.services.payments.get_client).

The existing test_tasks.py mocks release_to_performer at the task boundary;
this file lets the real service run end-to-end (queryset → transfer lookup →
unhold → DB state) so the Razorpay call contract and row transitions are
verified together.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Engagement, Payment
from bookings.tasks import release_completed_event_payouts
from users.models import Profile


@override_settings(RAZORPAY_ROUTE_ENABLED=True, RAZORPAY_DISPUTE_WINDOW_HOURS=24)
class TestPayoutReleaseIntegration(TestCase):
    """release_completed_event_payouts + real release_to_performer (Route)."""

    def setUp(self):
        self.meera = User.objects.create_user("meera", password="x")
        Profile.objects.filter(user=self.meera).update(
            is_potential_client=True, client_approved=True
        )

        self.mock_rzp = MagicMock()
        # One held transfer exists for the payment, id trf_test_123.
        self.mock_rzp.payment.transfers.return_value = {
            "items": [{"id": "trf_test_123"}]
        }
        self._patcher = patch(
            "bookings.services.payments.get_client", return_value=self.mock_rzp
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def _make_paid(
        self,
        username,
        event_dt,
        fee=2000,
        status=Engagement.STATUS_ACCEPTED,
        **kwargs,
    ):
        """A paid, accepted engagement with a captured Payment row."""
        performer = User.objects.create_user(username, password="x")
        Profile.objects.filter(user=performer).update(
            is_performer=True,
            razorpay_account_id="acc_test",
            razorpay_kyc_status="approved",
        )
        engagement = Engagement.objects.create(
            client=self.meera,
            performer=performer,
            date=event_dt.date(),
            time=event_dt.time(),
            venue="V",
            occasion="O",
            fee=fee,
            status=status,
            payment_status=Engagement.PAYMENT_PAID,
            paid_at=event_dt - timedelta(days=1),
            **kwargs,
        )
        Payment.objects.create(
            engagement=engagement,
            amount=fee,
            platform_fee=100,
            performer_share=fee - 100,
            razorpay_order_id=f"order_{username}",
            razorpay_payment_id=f"pay_{username}",
            status="captured",
        )
        return engagement

    # ── Happy path ──────────────────────────────────────────────────────
    def test_release_after_dispute_window(self):
        past = timezone.now() - timedelta(days=3)  # well past the 24h window
        engagement = self._make_paid("ravi", past)

        count = release_completed_event_payouts()
        self.assertEqual(count, 1)

        payment = engagement.payments.get()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "released")
        self.assertEqual(payment.razorpay_transfer_id, "trf_test_123")

        engagement.refresh_from_db()
        self.assertEqual(engagement.payment_status, Engagement.PAYMENT_RELEASED)
        self.assertIsNotNone(engagement.released_at)

        # The exact Razorpay call that moves money: unhold the transfer.
        self.mock_rzp.payment.transfers.assert_called_once_with("pay_ravi")
        self.mock_rzp.transfer.edit.assert_called_once_with(
            "trf_test_123", {"on_hold": 0}
        )

    def test_multiple_held_transfers_all_unheld(self):
        self.mock_rzp.payment.transfers.return_value = {
            "items": [{"id": "trf_a"}, {"id": "trf_b"}]
        }
        past = timezone.now() - timedelta(days=3)
        engagement = self._make_paid("ravi", past)

        count = release_completed_event_payouts()
        self.assertEqual(count, 1)
        self.mock_rzp.transfer.edit.assert_any_call("trf_a", {"on_hold": 0})
        self.mock_rzp.transfer.edit.assert_any_call("trf_b", {"on_hold": 0})
        self.assertEqual(self.mock_rzp.transfer.edit.call_count, 2)

    # ── Window filtering ────────────────────────────────────────────────
    def test_skips_within_dispute_window(self):
        soon_past = timezone.now() - timedelta(hours=12)  # window still open
        engagement = self._make_paid("ravi", soon_past)

        count = release_completed_event_payouts()
        self.assertEqual(count, 0)
        self.mock_rzp.payment.transfers.assert_not_called()
        self.mock_rzp.transfer.edit.assert_not_called()
        engagement.payments.get().refresh_from_db()
        self.assertEqual(engagement.payments.get().status, "captured")
        engagement.refresh_from_db()
        self.assertEqual(engagement.payment_status, Engagement.PAYMENT_PAID)

    def test_skips_at_exact_cutoff_boundary(self):
        # The task's filter is `event_datetime() < now - window` (strict). Pin
        # the task's clock so an event ending EXACTLY at the cutoff is
        # deterministically still held, while one just past it releases.
        fixed_now = timezone.make_aware(datetime(2026, 1, 15, 12, 0, 0))
        at_boundary = self._make_paid("ravi", fixed_now - timedelta(hours=24))

        with patch("bookings.tasks.timezone.now", return_value=fixed_now):
            first = release_completed_event_payouts()

        self.assertEqual(first, 0)  # exactly at the cutoff → not released
        at_boundary.refresh_from_db()
        self.assertEqual(at_boundary.payment_status, Engagement.PAYMENT_PAID)

        # An event just 1h past the boundary, same pinned clock → released.
        just_past = self._make_paid("sita", fixed_now - timedelta(hours=25))
        with patch("bookings.tasks.timezone.now", return_value=fixed_now):
            second = release_completed_event_payouts()
        self.assertEqual(second, 1)
        just_past.refresh_from_db()
        self.assertEqual(just_past.payment_status, Engagement.PAYMENT_RELEASED)
        at_boundary.refresh_from_db()
        self.assertEqual(at_boundary.payment_status, Engagement.PAYMENT_PAID)

    def test_skips_disputed_engagement(self):
        past = timezone.now() - timedelta(days=3)
        engagement = self._make_paid("ravi", past, disputed_at=timezone.now())

        count = release_completed_event_payouts()
        self.assertEqual(count, 0)
        self.mock_rzp.transfer.edit.assert_not_called()
        engagement.payments.get().refresh_from_db()
        self.assertEqual(engagement.payments.get().status, "captured")

    def test_skips_cancelled_engagement(self):
        past = timezone.now() - timedelta(days=3)
        engagement = self._make_paid(
            "ravi", past, status=Engagement.STATUS_CANCELLED_CLIENT
        )

        count = release_completed_event_payouts()
        self.assertEqual(count, 0)
        self.mock_rzp.transfer.edit.assert_not_called()

    # ── Idempotency ─────────────────────────────────────────────────────
    def test_double_run_releases_once(self):
        past = timezone.now() - timedelta(days=3)
        engagement = self._make_paid("ravi", past)

        first = release_completed_event_payouts()
        second = release_completed_event_payouts()

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)  # already released → not in queryset
        self.mock_rzp.transfer.edit.assert_called_once()
        engagement.payments.get().refresh_from_db()
        self.assertEqual(engagement.payments.get().status, "released")

    def test_paid_but_no_captured_payment_does_not_crash(self):
        # Paid flag but the captured Payment row is missing (data anomaly).
        past = timezone.now() - timedelta(days=3)
        engagement = self._make_paid("ravi", past)
        engagement.payments.all().delete()

        count = release_completed_event_payouts()
        # Per-row try/except swallows it; batch keeps going without crashing.
        self.assertEqual(count, 0)
        self.mock_rzp.payment.transfers.assert_not_called()

    # ── Batch resilience ────────────────────────────────────────────────
    def test_one_failure_does_not_block_the_batch(self):
        # Three paid gigs, oldest event first (Meta.ordering = date, time, performer):
        # anil → priya → ravi. Priya's unhold blows up; the other two must still
        # release.
        anil = self._make_paid("anil", timezone.now() - timedelta(days=3, hours=4))
        priya = self._make_paid("priya", timezone.now() - timedelta(days=3, hours=3))
        ravi = self._make_paid("ravi", timezone.now() - timedelta(days=3, hours=2))

        self.mock_rzp.transfer.edit.side_effect = [
            None,
            Exception("account deactivated"),
            None,
        ]

        count = release_completed_event_payouts()
        self.assertEqual(count, 2)

        ravi.refresh_from_db()
        anil.refresh_from_db()
        priya.refresh_from_db()
        self.assertEqual(ravi.payment_status, Engagement.PAYMENT_RELEASED)
        self.assertEqual(anil.payment_status, Engagement.PAYMENT_RELEASED)
        # Priya's money stays in escrow for admin.
        self.assertEqual(priya.payment_status, Engagement.PAYMENT_PAID)
        self.assertEqual(priya.payments.get().status, "captured")
