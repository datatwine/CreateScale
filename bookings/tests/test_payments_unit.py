"""
Unit tests for PaymentService.

Razorpay API is fully mocked via the mock_razorpay fixture so these tests
never touch the network. They verify:
  - The service speaks Razorpay's protocol correctly (right fields, right shape).
  - HMAC verification rejects forged signatures.
  - Every state transition is idempotent.
  - Disputed engagements are skipped during auto-release.
"""

import hashlib
import hmac

import pytest
from django.utils import timezone

from bookings.models import Engagement, Payment
from bookings.services.payments import PaymentService


@pytest.fixture(autouse=True)
def route_mode(settings):
    """This module validates Route-mode behavior (held transfers, reverse_all).
    Pin the flag ON — the new default is OFF (payouts). Payouts-mode mirrors
    live in test_payments_payouts.py."""
    settings.RAZORPAY_ROUTE_ENABLED = True


# ─────────────────────────────────────────────────────────────────────────
# create_order
# ─────────────────────────────────────────────────────────────────────────
class TestCreateOrder:
    def test_creates_order_with_held_transfer(
        self, engagement, mock_razorpay, settings
    ):
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
        mock_razorpay.order.create.return_value = {"id": "order_test_abc"}

        result = PaymentService.create_order(engagement)

        # Returned shape matches what checkout.js needs
        assert result == {
            "order_id": "order_test_abc",
            "amount": 200000,  # ₹2000 in paise
            "currency": "INR",
            "key_id": "rzp_test_key",
        }

        # Razorpay was called with the right held-transfer shape
        called_with = mock_razorpay.order.create.call_args[0][0]
        assert called_with["amount"] == 200000
        assert called_with["currency"] == "INR"
        assert called_with["transfers"][0]["on_hold"] == 1
        assert called_with["transfers"][0]["amount"] == 190000  # 95%
        assert called_with["transfers"][0]["account"] == "acc_test123"

        # Local Payment row was persisted
        payment = Payment.objects.get(razorpay_order_id="order_test_abc")
        assert payment.status == "created"
        assert payment.amount == 2000
        assert payment.platform_fee == 100  # 5% of ₹2000
        assert payment.performer_share == 1900

    def test_raises_if_performer_not_kyc_approved(self, engagement, mock_razorpay):
        engagement.performer.profile.razorpay_kyc_status = "pending"
        engagement.performer.profile.save()
        with pytest.raises(ValueError, match="payment setup is incomplete"):
            PaymentService.create_order(engagement)
        mock_razorpay.order.create.assert_not_called()

    def test_raises_if_performer_has_no_linked_account(self, engagement, mock_razorpay):
        engagement.performer.profile.razorpay_account_id = ""
        engagement.performer.profile.save()
        with pytest.raises(ValueError, match="payment setup is incomplete"):
            PaymentService.create_order(engagement)
        mock_razorpay.order.create.assert_not_called()

    def test_raises_if_already_paid(self, engagement, mock_razorpay):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        with pytest.raises(ValueError, match="not in unpaid state"):
            PaymentService.create_order(engagement)

    def test_raises_if_no_fee_snapshot(self, engagement, mock_razorpay):
        engagement.fee = None
        engagement.save()
        with pytest.raises(ValueError, match="no fee snapshot"):
            PaymentService.create_order(engagement)


# ─────────────────────────────────────────────────────────────────────────
# verify_and_capture
# ─────────────────────────────────────────────────────────────────────────
class TestVerifyAndCapture:
    def _valid_signature(self, order_id, payment_id, secret):
        body = f"{order_id}|{payment_id}".encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_happy_path_captures_payment(self, engagement, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            status="created",
        )
        sig = self._valid_signature("order_X", "pay_Y", "test_secret")

        result = PaymentService.verify_and_capture("order_X", "pay_Y", sig)

        assert result.status == "captured"
        assert result.razorpay_payment_id == "pay_Y"
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID
        assert engagement.paid_at is not None

    def test_rejects_invalid_signature(self, engagement, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            status="created",
        )
        with pytest.raises(ValueError, match="Invalid signature"):
            PaymentService.verify_and_capture("order_X", "pay_Y", "totally_bogus_sig")

    def test_idempotent_when_already_captured(self, engagement, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.paid_at = timezone.now()
        engagement.save()

        # Even with a bogus signature we get back the existing row,
        # IF a valid signature is provided. Bogus sig still gets rejected.
        sig = self._valid_signature("order_X", "pay_Y", "test_secret")
        result = PaymentService.verify_and_capture("order_X", "pay_Y", sig)
        assert result.status == "captured"

    def test_rejects_when_terminal_state(self, engagement, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            status="refunded",
        )
        sig = self._valid_signature("order_X", "pay_Y", "test_secret")
        with pytest.raises(ValueError, match="terminal state"):
            PaymentService.verify_and_capture("order_X", "pay_Y", sig)


# ─────────────────────────────────────────────────────────────────────────
# release_to_performer
# ─────────────────────────────────────────────────────────────────────────
class TestReleaseToPerformer:
    def test_releases_held_transfer(self, engagement, mock_razorpay):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        mock_razorpay.payment.transfers.return_value = {
            "items": [{"id": "trf_ABC", "amount": 190000}]
        }

        PaymentService.release_to_performer(engagement)

        # Transfer was unheld via Razorpay API
        mock_razorpay.transfer.edit.assert_called_once_with("trf_ABC", {"on_hold": 0})
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_RELEASED
        assert engagement.released_at is not None

    def test_skips_disputed_engagement(self, engagement, mock_razorpay):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.disputed_at = timezone.now()
        engagement.dispute_reason = "Performer never showed up"
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_payment_id="p",
            status="captured",
        )

        PaymentService.release_to_performer(engagement)

        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID  # unchanged
        mock_razorpay.payment.transfers.assert_not_called()
        mock_razorpay.transfer.edit.assert_not_called()

    def test_no_op_if_not_paid(self, engagement, mock_razorpay):
        # engagement is "unpaid" by default in the fixture
        PaymentService.release_to_performer(engagement)
        mock_razorpay.payment.transfers.assert_not_called()

    def test_route_release_no_transfers_stays_paid(self, engagement, mock_razorpay):
        # H5: capture happened but the split never materialized (empty items).
        # Release must NOT mark released — leave PAID, don't unhold, alert.
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        mock_razorpay.payment.transfers.return_value = {"items": []}

        PaymentService.release_to_performer(engagement)

        mock_razorpay.transfer.edit.assert_not_called()
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID  # unchanged
        assert engagement.payments.get().status == "captured"  # not released


# ─────────────────────────────────────────────────────────────────────────
# refund_to_client
# ─────────────────────────────────────────────────────────────────────────
class TestRefundToClient:
    def test_full_refund_with_reverse_all(self, engagement, mock_razorpay):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.cancellation_reason = "Family emergency"
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        mock_razorpay.payment.refund.return_value = {"id": "rfnd_XYZ"}

        PaymentService.refund_to_client(engagement)

        # Razorpay refund called with reverse_all + reason
        call_args = mock_razorpay.payment.refund.call_args
        assert call_args[0][0] == "pay_Y"
        body = call_args[0][1]
        assert body["reverse_all"] == 1
        assert body["notes"]["reason"] == "Family emergency"

        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUNDED
        assert engagement.refunded_at is not None

    def test_no_op_if_not_paid(self, engagement, mock_razorpay):
        PaymentService.refund_to_client(engagement)  # status=unpaid
        mock_razorpay.payment.refund.assert_not_called()

    def test_marker_persisted_before_api_route_mode(self, engagement, mock_razorpay):
        # C4 in Route mode: the refund_pending marker must commit BEFORE the
        # (reverse_all) refund call, so a crash can't leave the row capturable.
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.cancellation_reason = "changed plans"
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        mock_razorpay.payment.refund.side_effect = RuntimeError("refund down")

        with pytest.raises(RuntimeError):
            PaymentService.refund_to_client(engagement)

        p = engagement.payments.latest("created_at")
        assert p.status == "refund_pending"  # durable marker survived
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUND_PENDING


# ─────────────────────────────────────────────────────────────────────────
# verify_webhook_signature
# ─────────────────────────────────────────────────────────────────────────
class TestWebhookSignature:
    def test_valid_signature_passes(self, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        body = b'{"event":"payment.captured"}'
        sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        assert PaymentService.verify_webhook_signature(body, sig) is True

    def test_invalid_signature_fails(self, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        assert (
            PaymentService.verify_webhook_signature(b"body", "completely_wrong")
            is False
        )

    def test_empty_signature_fails(self, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec"
        assert PaymentService.verify_webhook_signature(b"body", "") is False

    def test_no_webhook_secret_configured_fails(self, settings):
        settings.RAZORPAY_WEBHOOK_SECRET = ""
        assert PaymentService.verify_webhook_signature(b"body", "x") is False


# ─────────────────────────────────────────────────────────────────────────
# handle_webhook_event (router)
# ─────────────────────────────────────────────────────────────────────────
class TestWebhookRouter:
    def test_payment_captured_routes_to_capture_handler(self, engagement, monkeypatch):
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            status="created",
        )
        # Skip the actual capture work; just confirm routing
        called_with = {}

        def fake_capture(order_id, payment_id):
            called_with["order_id"] = order_id
            called_with["payment_id"] = payment_id

        monkeypatch.setattr(PaymentService, "mark_captured_from_webhook", fake_capture)

        PaymentService.handle_webhook_event(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_Y",
                            "order_id": "order_X",
                        }
                    }
                },
            }
        )

        assert called_with == {"order_id": "order_X", "payment_id": "pay_Y"}

    def test_refund_processed_updates_payment_and_engagement(self, engagement):
        # H2: match by payment_id and drive BOTH Payment and Engagement to the
        # terminal refunded state (the old handler updated only the Payment).
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {"entity": {"id": "rfnd_ABC", "payment_id": "pay_Y"}}
                },
            }
        )
        p = Payment.objects.get(razorpay_payment_id="pay_Y")
        assert p.status == "refunded"
        assert p.razorpay_refund_id == "rfnd_ABC"
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUNDED
        assert engagement.refunded_at is not None

    def test_unknown_event_is_a_no_op(self, engagement):
        # Just shouldn't crash
        PaymentService.handle_webhook_event(
            {
                "event": "some.weird.event",
                "payload": {},
            }
        )


# ─────────────────────────────────────────────────────────────────────────
# _split_amount helper
# ─────────────────────────────────────────────────────────────────────────
class TestSplitAmount:
    def test_five_percent_split(self, settings):
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
        assert PaymentService._split_amount(2000) == (100, 1900)
        assert PaymentService._split_amount(10000) == (500, 9500)

    def test_zero_percent_means_full_to_performer(self, settings):
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 0
        assert PaymentService._split_amount(2000) == (0, 2000)


# ─────────────────────────────────────────────────────────────────────────
# create_order order reuse (C1 + H1) — Route variant
# ─────────────────────────────────────────────────────────────────────────
class TestOrderReuseRoute:
    def test_reused_order_keeps_held_transfer_spec(
        self, engagement, mock_razorpay, settings
    ):
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
        mock_razorpay.order.create.return_value = {"id": "order_1"}
        mock_razorpay.order.fetch.return_value = {"status": "created"}

        r1 = PaymentService.create_order(engagement)  # tab 1
        r2 = PaymentService.create_order(engagement)  # tab 2 → resumes order_1

        assert r1["order_id"] == r2["order_id"] == "order_1"
        mock_razorpay.order.create.assert_called_once()  # NOT twice
        assert engagement.payments.filter(status="created").count() == 1
        # The single order still carries the held transfer — escrow survives.
        created_with = mock_razorpay.order.create.call_args[0][0]
        assert created_with["transfers"][0]["on_hold"] == 1


# ─────────────────────────────────────────────────────────────────────────
# Gateway webhook handlers (H2 / H4 / M1 / M2 / M3)
# ─────────────────────────────────────────────────────────────────────────
class TestGatewayWebhookHandlers:
    def test_refund_failed_reopens(self, engagement):
        # H4: Razorpay accepted the refund, then it failed at the bank. The DB
        # must not keep claiming "refunded".
        engagement.payment_status = Engagement.PAYMENT_REFUNDED
        engagement.refunded_at = timezone.now()
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_payment_id="pay_Y",
            razorpay_refund_id="rfnd_1",
            status="refunded",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "refund.failed",
                "payload": {"refund": {"entity": {"id": "rfnd_1"}}},
            }
        )
        assert (
            Payment.objects.get(razorpay_refund_id="rfnd_1").status == "refund_failed"
        )
        engagement.refresh_from_db()
        assert engagement.payment_status != Engagement.PAYMENT_REFUNDED

    def test_transfer_processed_updates_engagement(self, engagement):
        # H2 (Route): the settled transfer must flip the Engagement too.
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_transfer_id="trf_1",
            status="captured",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "transfer.processed",
                "payload": {"transfer": {"entity": {"id": "trf_1"}}},
            }
        )
        assert Payment.objects.get(razorpay_transfer_id="trf_1").status == "released"
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_RELEASED
        assert engagement.released_at is not None

    def test_transfer_failed_is_handled(self, caplog):
        # M1: previously unhandled — must not crash and must alert.
        import logging

        caplog.set_level(logging.CRITICAL)
        PaymentService.handle_webhook_event(
            {
                "event": "transfer.failed",
                "payload": {"transfer": {"entity": {"id": "trf_x", "source": "pay_x"}}},
            }
        )
        assert "FAILED" in caplog.text

    def test_payment_failed_marks_created_row_failed(self, engagement):
        # M2: ghost "created" row → failed; a captured row for the same order
        # would be excluded by the status filter.
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_ghost",
            status="created",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "payment.failed",
                "payload": {"payment": {"entity": {"order_id": "order_ghost"}}},
            }
        )
        assert Payment.objects.get(razorpay_order_id="order_ghost").status == "failed"

    def test_account_activated_sets_kyc_approved(self, performer_user):
        # M3: linked-account webhook syncs KYC status (no manual admin edit).
        profile = performer_user.profile
        profile.razorpay_account_id = "acc_test123"
        profile.razorpay_kyc_status = "pending"
        profile.save()
        PaymentService.handle_webhook_event(
            {
                "event": "account.activated",
                "payload": {"account": {"entity": {"id": "acc_test123"}}},
            }
        )
        profile.refresh_from_db()
        assert profile.razorpay_kyc_status == "approved"

    def test_account_events_map_all_kyc_states(self, performer_user):
        # M3: every handled account.* event maps to the right KYC status.
        profile = performer_user.profile
        profile.razorpay_account_id = "acc_x"
        profile.save()
        for event, expected in [
            ("account.under_review", "pending"),
            ("account.suspended", "rejected"),
            ("account.activated", "approved"),
            ("account.rejected", "rejected"),
        ]:
            PaymentService.handle_webhook_event(
                {"event": event, "payload": {"account": {"entity": {"id": "acc_x"}}}}
            )
            profile.refresh_from_db()
            assert profile.razorpay_kyc_status == expected, event

    def test_payment_failed_leaves_captured_row_untouched(self, engagement):
        # M2 / Scenario 2 Case C: a failed attempt must NEVER clobber a captured
        # success on the same order (the status="created" filter protects it).
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_ok",
            razorpay_payment_id="pay_ok",
            status="captured",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "payment.failed",
                "payload": {"payment": {"entity": {"order_id": "order_ok"}}},
            }
        )
        assert Payment.objects.get(razorpay_order_id="order_ok").status == "captured"

    def test_refund_processed_is_idempotent(self, engagement):
        # Production webhooks retry — a second refund.processed must be a no-op.
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_payment_id="pay_Y",
            status="captured",
        )
        evt = {
            "event": "refund.processed",
            "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_Y"}}},
        }
        PaymentService.handle_webhook_event(evt)
        PaymentService.handle_webhook_event(evt)  # retry
        assert (
            Payment.objects.filter(
                razorpay_payment_id="pay_Y", status="refunded"
            ).count()
            == 1
        )
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_REFUNDED

    def test_transfer_processed_is_idempotent(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_transfer_id="trf_1",
            status="captured",
        )
        evt = {
            "event": "transfer.processed",
            "payload": {"transfer": {"entity": {"id": "trf_1"}}},
        }
        PaymentService.handle_webhook_event(evt)
        first_released_at = Engagement.objects.get(pk=engagement.pk).released_at
        PaymentService.handle_webhook_event(evt)  # retry
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_RELEASED
        # The engagement's release stamp is not bumped on the idempotent retry.
        assert engagement.released_at == first_released_at


# ─────────────────────────────────────────────────────────────────────────
# Duplicate-capture guard (C1 defense-in-depth) — both capture entry points
# ─────────────────────────────────────────────────────────────────────────
class TestDuplicateCaptureGuard:
    """If order reuse is bypassed and two live orders exist, the SECOND capture
    for an already-paid engagement must be flagged 'failed', never booked as a
    second charge. Covers verify_and_capture AND mark_captured_from_webhook."""

    def _sig(self, order_id, payment_id, secret):
        body = f"{order_id}|{payment_id}".encode()
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def _paid_with_second_open_order(self, engagement):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.paid_at = timezone.now()
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_1",
            razorpay_payment_id="pay_1",
            status="captured",
        )
        return Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_2",
            status="created",
        )

    def test_verify_and_capture_flags_duplicate(self, engagement, settings):
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        dup = self._paid_with_second_open_order(engagement)
        sig = self._sig("order_2", "pay_2", "test_secret")

        result = PaymentService.verify_and_capture("order_2", "pay_2", sig)

        assert result.status == "failed"
        dup.refresh_from_db()
        assert dup.status == "failed"
        assert dup.razorpay_payment_id == "pay_2"  # recorded for reconciliation
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID  # unchanged
        assert engagement.payments.filter(status="captured").count() == 1

    def test_webhook_capture_flags_duplicate(self, engagement):
        dup = self._paid_with_second_open_order(engagement)

        PaymentService.mark_captured_from_webhook("order_2", "pay_2")

        dup.refresh_from_db()
        assert dup.status == "failed"
        engagement.refresh_from_db()
        assert engagement.payments.filter(status="captured").count() == 1

    def test_webhook_captures_when_browser_callback_missed(self, engagement):
        # Scenario 2 Case B: payment authorized but the browser callback dropped
        # → the payment.captured webhook self-heals the engagement to PAID.
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_b",
            status="created",
        )
        PaymentService.mark_captured_from_webhook("order_b", "pay_b")
        engagement.refresh_from_db()
        assert engagement.payment_status == Engagement.PAYMENT_PAID
        p = Payment.objects.get(razorpay_order_id="order_b")
        assert p.status == "captured"
        assert p.razorpay_payment_id == "pay_b"
