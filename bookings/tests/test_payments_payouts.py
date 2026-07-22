"""
Payouts-mode tests (RAZORPAY_ROUTE_ENABLED=False — the new default): the
automated RazorpayX Payouts path. Verifies orders carry no transfers, the
performer is payable on bank details alone, release fires a payout (not a
transfer unhold), and the webhook drives the terminal state. RazorpayX HTTP is
fully mocked via mock_razorpayx so these tests never touch the network.
"""

import pytest
from django.utils import timezone

from bookings.models import Engagement, Payment
from bookings.services.payments import PaymentService


@pytest.fixture(autouse=True)
def payouts_mode(settings):
    settings.RAZORPAY_ROUTE_ENABLED = False
    settings.RAZORPAY_KEY_ID = "rzp_test_key"
    settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
    settings.RAZORPAYX_ACCOUNT_NUMBER = "7878780080316316"
    settings.RAZORPAYX_PAYOUT_MODE = "IMPS"


# ─────────────────────────────────────────────────────────────────────────
# create_order — no split at collection
# ─────────────────────────────────────────────────────────────────────────
class TestCreateOrderPayoutsMode:
    def test_order_has_no_transfers(self, engagement, mock_razorpay):
        mock_razorpay.order.create.return_value = {"id": "order_p1"}

        PaymentService.create_order(engagement)

        called = mock_razorpay.order.create.call_args[0][0]
        assert "transfers" not in called  # no split at collection
        payment = Payment.objects.get(razorpay_order_id="order_p1")
        assert payment.performer_share == 1900  # ledger still snapshotted
        assert payment.platform_fee == 100

    def test_payable_without_linked_account(self, engagement, mock_razorpay):
        # Clear Route credentials entirely; bank details alone must suffice.
        p = engagement.performer.profile
        p.razorpay_account_id = ""
        p.razorpay_kyc_status = ""
        p.save()
        mock_razorpay.order.create.return_value = {"id": "order_p2"}

        PaymentService.create_order(engagement)  # must not raise
        mock_razorpay.order.create.assert_called_once()

    def test_unpayable_without_bank_details(self, engagement, mock_razorpay):
        p = engagement.performer.profile
        p.bank_account_holder_name = ""
        p.bank_account_number = ""
        p.bank_ifsc = ""
        p.save()
        with pytest.raises(ValueError, match="payment setup is incomplete"):
            PaymentService.create_order(engagement)
        mock_razorpay.order.create.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# release_to_performer — fires a payout, not a transfer unhold
# ─────────────────────────────────────────────────────────────────────────
class TestReleaseFiresPayout:
    @pytest.fixture
    def paid_engagement(self, engagement, mock_razorpay):
        mock_razorpay.order.create.return_value = {"id": "order_r1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_r1", "pay_r1")
        engagement.refresh_from_db()
        return engagement

    def test_release_creates_payout_and_sets_processing(
        self, paid_engagement, mock_razorpay, mock_razorpayx
    ):
        PaymentService.release_to_performer(paid_engagement)

        # No Route calls; a payout WAS created.
        mock_razorpay.transfer.edit.assert_not_called()
        mock_razorpay.payment.transfers.assert_not_called()
        paid_engagement.refresh_from_db()
        assert paid_engagement.payment_status == Engagement.PAYMENT_PAYOUT_PROCESSING
        assert paid_engagement.payout_initiated_at is not None
        payment = paid_engagement.payments.latest("created_at")
        assert payment.status == "payout_processing"
        assert payment.razorpayx_payout_id == "pout_test"
        assert payment.payout_idempotency_key == "idem_test"

    def test_destination_cached_on_profile(self, paid_engagement, mock_razorpayx):
        PaymentService.release_to_performer(paid_engagement)
        profile = paid_engagement.performer.profile
        profile.refresh_from_db()
        assert profile.razorpayx_contact_id == "cont_test"
        assert profile.razorpayx_fund_account_id == "fa_test"

    def test_release_idempotent(self, paid_engagement, mock_razorpayx):
        PaymentService.release_to_performer(paid_engagement)
        PaymentService.release_to_performer(paid_engagement)  # 2nd: not PAID → no-op
        paid_engagement.refresh_from_db()
        assert paid_engagement.payments.filter(status="payout_processing").count() == 1

    def test_disputed_stays_frozen(self, paid_engagement, mock_razorpayx):
        paid_engagement.disputed_at = timezone.now()
        paid_engagement.save()
        PaymentService.release_to_performer(paid_engagement)
        paid_engagement.refresh_from_db()
        assert paid_engagement.payment_status == Engagement.PAYMENT_PAID


# ─────────────────────────────────────────────────────────────────────────
# refund_to_client — no reverse_all in payouts mode
# ─────────────────────────────────────────────────────────────────────────
class TestRefundPayoutsMode:
    def test_refund_has_no_reverse_all(self, engagement, mock_razorpay):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.cancellation_reason = "Client cancelled"
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        mock_razorpay.payment.refund.return_value = {"id": "rfnd_X"}

        PaymentService.refund_to_client(engagement)

        body = mock_razorpay.payment.refund.call_args[0][1]
        assert "reverse_all" not in body  # nothing to reverse
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUNDED


# ─────────────────────────────────────────────────────────────────────────
# handle_payout_webhook_event — terminal state driven by webhook
# ─────────────────────────────────────────────────────────────────────────
class TestPayoutWebhook:
    @pytest.fixture
    def processing(self, engagement, mock_razorpay, mock_razorpayx):
        mock_razorpay.order.create.return_value = {"id": "order_w1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_w1", "pay_w1")
        engagement.refresh_from_db()
        PaymentService.release_to_performer(engagement)
        engagement.refresh_from_db()
        return engagement

    def _event(self, etype, utr=None):
        return {
            "event": etype,
            "payload": {"payout": {"entity": {"id": "pout_test", "utr": utr}}},
        }

    def test_processed_releases(self, processing):
        PaymentService.handle_payout_webhook_event(
            self._event("payout.processed", utr="UTR12345")
        )
        processing.refresh_from_db()
        assert processing.payment_status == Engagement.PAYMENT_RELEASED
        assert processing.released_at is not None
        payment = processing.payments.latest("created_at")
        assert payment.status == "released"
        assert payment.payout_reference == "UTR12345"

    def test_processed_idempotent(self, processing):
        for _ in range(2):
            PaymentService.handle_payout_webhook_event(
                self._event("payout.processed", utr="UTR1")
            )
        assert processing.payments.filter(status="released").count() == 1

    def test_updated_stores_utr_without_state_change(self, processing):
        PaymentService.handle_payout_webhook_event(
            self._event("payout.updated", utr="UTR777")
        )
        processing.refresh_from_db()
        # State stays processing; UTR captured for the audit trail.
        assert processing.payment_status == Engagement.PAYMENT_PAYOUT_PROCESSING
        payment = processing.payments.latest("created_at")
        assert payment.payout_reference == "UTR777"

    def test_reversed_marks_failed(self, processing):
        PaymentService.handle_payout_webhook_event(self._event("payout.reversed"))
        processing.refresh_from_db()
        assert processing.payment_status == Engagement.PAYMENT_PAYOUT_FAILED
        assert processing.payments.latest("created_at").status == "payout_failed"

    def test_unknown_payout_id_is_noop(self, processing):
        PaymentService.handle_payout_webhook_event(
            {
                "event": "payout.processed",
                "payload": {"payout": {"entity": {"id": "pout_unknown"}}},
            }
        )
        processing.refresh_from_db()
        assert processing.payment_status == Engagement.PAYMENT_PAYOUT_PROCESSING

    def test_retry_after_failure_uses_new_key(self, processing, mock_razorpayx):
        # Fail it, then retry via the admin path (initiate_payout).
        PaymentService.handle_payout_webhook_event(self._event("payout.failed"))
        processing.refresh_from_db()
        assert processing.payment_status == Engagement.PAYMENT_PAYOUT_FAILED

        PaymentService.initiate_payout(processing)
        processing.refresh_from_db()
        assert processing.payment_status == Engagement.PAYMENT_PAYOUT_PROCESSING
        assert processing.payments.latest("created_at").status == "payout_processing"
