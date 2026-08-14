"""
Payouts-mode tests (RAZORPAY_ROUTE_ENABLED=False — the new default): the
automated RazorpayX Payouts path. Verifies orders carry no transfers, the
performer is payable on bank details alone, release fires a payout (not a
transfer unhold), and the webhook drives the terminal state. RazorpayX HTTP is
fully mocked via mock_razorpayx so these tests never touch the network.
"""

from unittest.mock import MagicMock

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


# ─────────────────────────────────────────────────────────────────────────
# create_order order reuse (C1 + H1) — Payouts variant
# ─────────────────────────────────────────────────────────────────────────
class TestOrderReuse:
    def test_second_call_reuses_same_order(self, engagement, mock_razorpay):
        mock_razorpay.order.create.return_value = {"id": "order_1"}
        mock_razorpay.order.fetch.return_value = {"status": "created"}

        r1 = PaymentService.create_order(engagement)  # tab 1
        r2 = PaymentService.create_order(engagement)  # tab 2

        assert r1["order_id"] == r2["order_id"] == "order_1"
        mock_razorpay.order.create.assert_called_once()  # NOT twice
        assert engagement.payments.filter(status="created").count() == 1

    def test_terminal_order_retired_then_fresh(self, engagement, mock_razorpay):
        # Existing "created" row, but Razorpay says the order is gone/terminal.
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_old",
            status="created",
        )
        mock_razorpay.order.fetch.return_value = {"status": "expired"}
        mock_razorpay.order.create.return_value = {"id": "order_new"}

        PaymentService.create_order(engagement)

        assert Payment.objects.get(razorpay_order_id="order_old").status == "failed"
        assert Payment.objects.filter(razorpay_order_id="order_new").exists()

    def test_paid_order_short_circuits_to_webhook(self, engagement, mock_razorpay):
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_paid",
            status="created",
        )
        mock_razorpay.order.fetch.return_value = {"status": "paid"}

        r = PaymentService.create_order(engagement)

        assert r["order_id"] == "order_paid"
        mock_razorpay.order.create.assert_not_called()

    def test_failed_row_does_not_block_fresh_order(self, engagement, mock_razorpay):
        # H1: a "failed" ghost row must never lock the client out.
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_dead",
            status="failed",
        )
        mock_razorpay.order.create.return_value = {"id": "order_fresh"}

        r = PaymentService.create_order(engagement)

        assert r["order_id"] == "order_fresh"
        mock_razorpay.order.create.assert_called_once()
        mock_razorpay.order.fetch.assert_not_called()  # failed rows aren't resumed


# ─────────────────────────────────────────────────────────────────────────
# initiate_payout crash-safe idempotency (C2)
# ─────────────────────────────────────────────────────────────────────────
class TestPayoutIdempotencyRecovery:
    @pytest.fixture
    def processing(self, engagement, mock_razorpay, mock_razorpayx):
        """A payout that has been fired and is awaiting its webhook."""
        mock_razorpay.order.create.return_value = {"id": "order_i1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_i1", "pay_i1")
        engagement.refresh_from_db()
        PaymentService.release_to_performer(engagement)
        engagement.refresh_from_db()
        return engagement

    def test_retry_after_crash_reuses_saved_key(self, payout_crash_row, mock_razorpayx):
        # Key saved, payout_id blank → reuse the key so Razorpay dedups.
        PaymentService.initiate_payout(payout_crash_row.engagement)

        assert (
            mock_razorpayx.create_payout.call_args.kwargs["idempotency_key"]
            == "idem_saved"
        )
        payout_crash_row.refresh_from_db()
        assert payout_crash_row.razorpayx_payout_id == "pout_test"
        assert payout_crash_row.status == "payout_processing"

    def test_key_persisted_before_api_call(
        self, engagement, mock_razorpay, mock_razorpayx
    ):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            platform_fee=100,
            performer_share=1900,
            razorpay_order_id="o",
            razorpay_payment_id="p",
            status="captured",
        )
        # API fails AFTER the key was committed in step 1.
        mock_razorpayx.create_payout.side_effect = RuntimeError("API down")

        with pytest.raises(RuntimeError):
            PaymentService.initiate_payout(engagement)

        p = engagement.payments.latest("created_at")
        assert p.payout_idempotency_key != ""  # committed in step 1, survived
        assert p.razorpayx_payout_id == ""  # step 3 never ran
        assert p.status == "captured"  # state machine not advanced

    def test_genuine_failure_retry_rotates_key(
        self, processing, mock_razorpayx, monkeypatch
    ):
        import bookings.services.razorpayx as rx

        PaymentService.handle_payout_webhook_event(
            {"event": "payout.failed", "payload": {"payout": {"entity": {"id": "pout_test"}}}}
        )
        processing.refresh_from_db()
        first = processing.payments.latest("created_at").payout_idempotency_key

        monkeypatch.setattr(rx, "new_idempotency_key", lambda: "idem_rotated")
        PaymentService.initiate_payout(processing)

        key2 = processing.payments.latest("created_at").payout_idempotency_key
        assert key2 == "idem_rotated"
        assert key2 != first


# ─────────────────────────────────────────────────────────────────────────
# Reversal after "released" (C3)
# ─────────────────────────────────────────────────────────────────────────
class TestReversalAfterRelease:
    @pytest.fixture
    def released(self, engagement, mock_razorpay, mock_razorpayx):
        mock_razorpay.order.create.return_value = {"id": "order_z"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_z", "pay_z")
        engagement.refresh_from_db()
        PaymentService.release_to_performer(engagement)
        PaymentService.handle_payout_webhook_event(
            {
                "event": "payout.processed",
                "payload": {"payout": {"entity": {"id": "pout_test", "utr": "U1"}}},
            }
        )
        engagement.refresh_from_db()
        return engagement

    def test_reversed_after_release_reopens(self, released):
        assert released.payment_status == Engagement.PAYMENT_RELEASED
        PaymentService.handle_payout_webhook_event(
            {"event": "payout.reversed", "payload": {"payout": {"entity": {"id": "pout_test"}}}}
        )
        released.refresh_from_db()
        assert released.payment_status == Engagement.PAYMENT_PAYOUT_FAILED
        assert released.released_at is None  # release stamp undone
        assert released.payments.latest("created_at").status == "payout_reversed"

    def test_failed_racing_a_settle_keeps_success(self, released):
        # A late payout.failed (NOT reversed) must not clobber a real settle.
        PaymentService.handle_payout_webhook_event(
            {"event": "payout.failed", "payload": {"payout": {"entity": {"id": "pout_test"}}}}
        )
        released.refresh_from_db()
        assert released.payment_status == Engagement.PAYMENT_RELEASED

    def test_double_reversal_is_idempotent(self, released):
        # RazorpayX retries webhooks — a second payout.reversed must stay
        # payout_reversed, not degrade to payout_failed.
        rev = {"event": "payout.reversed", "payload": {"payout": {"entity": {"id": "pout_test"}}}}
        PaymentService.handle_payout_webhook_event(rev)
        PaymentService.handle_payout_webhook_event(rev)  # retry
        released.refresh_from_db()
        assert released.payment_status == Engagement.PAYMENT_PAYOUT_FAILED
        assert released.payments.latest("created_at").status == "payout_reversed"


# ─────────────────────────────────────────────────────────────────────────
# refund_to_client crash-safe durability (C4)
# ─────────────────────────────────────────────────────────────────────────
class TestRefundDurability:
    def _captured(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.cancellation_reason = "client cancelled"
        engagement.save()
        return Payment.objects.create(
            engagement=engagement,
            amount=2000,
            platform_fee=100,
            performer_share=1900,
            razorpay_order_id="o",
            razorpay_payment_id="pay_Y",
            status="captured",
        )

    def test_marker_persisted_before_refund_api(self, engagement, mock_razorpay):
        self._captured(engagement)
        mock_razorpay.payment.refund.side_effect = RuntimeError("refund API down")

        with pytest.raises(RuntimeError):
            PaymentService.refund_to_client(engagement)

        p = engagement.payments.latest("created_at")
        assert p.status == "refund_pending"  # committed before the API call
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUND_PENDING

    def test_celery_skips_refund_pending(self, engagement, mock_razorpay):
        from datetime import date, timedelta

        p = self._captured(engagement)
        p.status = "refund_pending"
        p.save()
        engagement.status = Engagement.STATUS_ACCEPTED
        engagement.payment_status = Engagement.PAYMENT_REFUND_PENDING
        engagement.date = date.today() - timedelta(days=2)
        engagement.save()

        from bookings.tasks import release_completed_event_payouts

        assert release_completed_event_payouts() == 0  # not re-released
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUND_PENDING

    def test_webhook_completes_by_payment_id(self, engagement, mock_razorpay):
        p = self._captured(engagement)
        p.status = "refund_pending"
        p.save()
        engagement.payment_status = Engagement.PAYMENT_REFUND_PENDING
        engagement.save()

        PaymentService.handle_webhook_event(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_Y"}}
                },
            }
        )
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUNDED
        p.refresh_from_db()
        assert p.status == "refunded"
        assert p.razorpay_refund_id == "rfnd_1"


# ─────────────────────────────────────────────────────────────────────────
# Fund account cache invalidation (H3)
# ─────────────────────────────────────────────────────────────────────────
class TestFundAccountCache:
    def test_bank_change_recreates_fund_account(
        self, performer_user, mock_razorpayx, monkeypatch
    ):
        import bookings.services.razorpayx as rx

        create_fa = MagicMock(return_value={"id": "fa_test"})
        monkeypatch.setattr(rx, "create_fund_account", create_fa)
        profile = performer_user.profile

        PaymentService.ensure_payout_destination(profile)
        assert create_fa.call_count == 1  # first build

        PaymentService.ensure_payout_destination(profile)
        assert create_fa.call_count == 1  # unchanged details → cache hit

        profile.bank_account_number = "9999999999"
        profile.save()
        PaymentService.ensure_payout_destination(profile)
        assert create_fa.call_count == 2  # changed details → rebuild


# ─────────────────────────────────────────────────────────────────────────
# Proactive bank validation (Rec 11)
# ─────────────────────────────────────────────────────────────────────────
class TestBankValidation:
    def test_validation_marks_valid(self, performer_user, mock_razorpayx):
        profile = performer_user.profile
        PaymentService.ensure_payout_destination(profile)
        profile.refresh_from_db()
        assert profile.bank_validation_status == "valid"
        assert profile.razorpayx_fund_account_id == "fa_test"

    def test_name_mismatch_marks_invalid_and_blocks(
        self, performer_user, mock_razorpayx
    ):
        mock_razorpayx.validate_fund_account.return_value = {
            "id": "fav_x",
            "status": "completed",
            "results": {"account_status": "active", "registered_name": "Someone Else"},
        }
        profile = performer_user.profile
        PaymentService.ensure_payout_destination(profile)
        profile.refresh_from_db()
        assert profile.bank_validation_status == "invalid"
        assert profile.razorpayx_fund_account_id == ""  # never pay a failed account
        assert profile.can_receive_payments is False

    def test_pending_stays_payable(self, performer_user, mock_razorpayx):
        mock_razorpayx.validate_fund_account.return_value = {
            "id": "fav_p",
            "status": "created",  # results not in yet
            "results": {},
        }
        profile = performer_user.profile
        PaymentService.ensure_payout_destination(profile)
        profile.refresh_from_db()
        assert profile.bank_validation_status == "pending"
        assert profile.can_receive_payments is True  # T+2 delay must not block

    def test_completed_webhook_applies_result(self, performer_user, mock_razorpayx):
        profile = performer_user.profile
        profile.razorpayx_validation_id = "fav_async"
        profile.bank_validation_status = "pending"
        profile.save()

        PaymentService.handle_payout_webhook_event(
            {
                "event": "fund_account.validation.completed",
                "payload": {
                    "fund_account.validation": {
                        "entity": {
                            "id": "fav_async",
                            "results": {
                                "account_status": "active",
                                "registered_name": "Performer One",
                            },
                        }
                    }
                },
            }
        )
        profile.refresh_from_db()
        assert profile.bank_validation_status == "valid"


# ─────────────────────────────────────────────────────────────────────────
# Admin "Retry failed payout" action (Scenario 5)
# ─────────────────────────────────────────────────────────────────────────
class TestAdminRetryAction:
    def _request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        req = RequestFactory().post("/")
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _admin(self):
        from django.contrib.admin.sites import AdminSite

        from bookings.admin import PaymentAdmin

        return PaymentAdmin(Payment, AdminSite())

    @pytest.fixture
    def failed(self, engagement, mock_razorpay, mock_razorpayx):
        mock_razorpay.order.create.return_value = {"id": "order_a1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_a1", "pay_a1")
        engagement.refresh_from_db()
        PaymentService.release_to_performer(engagement)
        PaymentService.handle_payout_webhook_event(
            {"event": "payout.failed", "payload": {"payout": {"entity": {"id": "pout_test"}}}}
        )
        engagement.refresh_from_db()
        return engagement

    def test_retry_refires_and_clears_stale_fund_account(self, failed, mock_razorpayx):
        payment = failed.payments.latest("created_at")
        assert payment.status == "payout_failed"
        # A stale cached fund account the performer has since corrected.
        profile = failed.performer.profile
        profile.razorpayx_fund_account_id = "fa_stale"
        profile.save()

        self._admin().retry_failed_payout(
            self._request(), Payment.objects.filter(pk=payment.pk)
        )

        failed.refresh_from_db()
        assert failed.payment_status == Engagement.PAYMENT_PAYOUT_PROCESSING
        payment.refresh_from_db()
        assert payment.status == "payout_processing"
        profile.refresh_from_db()
        # Cleared and rebuilt fresh (mock → fa_test), not the stale id.
        assert profile.razorpayx_fund_account_id == "fa_test"

    def test_retry_re_pays_a_reversed_payout(self, failed, mock_razorpayx):
        # C3 recovery: a reversed payout must be re-payable via the admin action
        # (regression guard for the initiate_payout status-filter fix).
        payment = failed.payments.latest("created_at")
        payment.status = "payout_reversed"
        payment.save()

        self._admin().retry_failed_payout(
            self._request(), Payment.objects.filter(pk=payment.pk)
        )

        payment.refresh_from_db()
        assert payment.status == "payout_processing"

    def test_retry_skips_non_failed_rows(self, engagement, mock_razorpayx):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        payment = Payment.objects.create(
            engagement=engagement,
            amount=2000,
            performer_share=1900,
            razorpay_order_id="o",
            razorpay_payment_id="p",
            status="captured",
        )
        self._admin().retry_failed_payout(
            self._request(), Payment.objects.filter(pk=payment.pk)
        )
        payment.refresh_from_db()
        assert payment.status == "captured"  # untouched — not a failed row
