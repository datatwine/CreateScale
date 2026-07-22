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

    def test_refund_processed_updates_payment_row(self, engagement):
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_refund_id="rfnd_ABC",
            status="captured",
        )
        PaymentService.handle_webhook_event(
            {
                "event": "refund.processed",
                "payload": {"refund": {"entity": {"id": "rfnd_ABC"}}},
            }
        )
        p = Payment.objects.get(razorpay_refund_id="rfnd_ABC")
        assert p.status == "refunded"

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
