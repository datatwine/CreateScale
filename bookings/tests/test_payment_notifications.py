"""
Tests for the payment-related push notification triggers (issue #81,
remaining triggers #4 and #5):

- Payment disbursed -> notify performer, fired from BOTH terminal points:
    * release_to_performer() Route-mode branch (release is immediate there)
    * _settle_payout() (Payouts-mode terminal, driven by the payout.processed
      webhook — release_to_performer() only *starts* the payout there)
- Refund initiated -> notify client, fired from refund_to_client()

send_push_notification is monkey-patched so these tests never touch Expo's
API, and mock_razorpay/mock_razorpayx keep them off the real Razorpay APIs.

All three send sites are wrapped in transaction.on_commit() (money already
moved by the time they fire, so a notification failure must not roll back
the payment-state write) — tests that expect the notification to actually
fire use the django_capture_on_commit_callbacks fixture to run those
deferred callbacks, since pytest-django wraps each test in a transaction
that's rolled back, not committed.
"""

from unittest.mock import MagicMock

import pytest

from bookings.models import Engagement, Payment
from bookings.services.payments import PaymentService


@pytest.fixture
def mock_send(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("bookings.services.payments.send_push_notification", mock)
    return mock


@pytest.fixture
def route_mode(settings):
    settings.RAZORPAY_ROUTE_ENABLED = True


@pytest.mark.django_db
@pytest.mark.usefixtures("route_mode")
class TestReleaseToPerformerNotifiesRouteMode:
    def test_notifies_performer_on_release(
        self, engagement, mock_razorpay, mock_send, django_capture_on_commit_callbacks
    ):
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="order_X",
            razorpay_payment_id="pay_Y",
            status="captured",
            performer_share=1900,
        )
        mock_razorpay.payment.transfers.return_value = {
            "items": [{"id": "trf_ABC", "amount": 190000}]
        }

        with django_capture_on_commit_callbacks(execute=True):
            PaymentService.release_to_performer(engagement)

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == engagement.performer
        assert "1900" in kwargs["body"]

    def test_does_not_notify_when_disputed(self, engagement, mock_razorpay, mock_send):
        from django.utils import timezone

        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.disputed_at = timezone.now()
        engagement.dispute_reason = "no-show"
        engagement.save()
        Payment.objects.create(
            engagement=engagement,
            amount=2000,
            razorpay_order_id="o",
            razorpay_payment_id="p",
            status="captured",
        )

        PaymentService.release_to_performer(engagement)

        mock_send.assert_not_called()


@pytest.mark.django_db
class TestReleaseToPerformerPayoutsMode:
    """In Payouts mode, release_to_performer() only STARTS the payout —
    money hasn't actually reached the performer yet. The notification must
    wait for _settle_payout() (the payout.processed webhook)."""

    def test_does_not_notify_yet_when_payout_only_initiated(
        self, engagement, mock_razorpay, mock_razorpayx, mock_send, settings
    ):
        settings.RAZORPAY_ROUTE_ENABLED = False
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
        settings.RAZORPAYX_ACCOUNT_NUMBER = "7878780080316316"
        settings.RAZORPAYX_PAYOUT_MODE = "IMPS"
        mock_razorpay.order.create.return_value = {"id": "order_r1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_r1", "pay_r1")
        engagement.refresh_from_db()

        PaymentService.release_to_performer(engagement)

        mock_send.assert_not_called()


@pytest.mark.django_db
class TestSettlePayoutNotifies:
    @pytest.fixture
    def processing(self, engagement, mock_razorpay, mock_razorpayx, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        settings.RAZORPAY_KEY_ID = "rzp_test_key"
        settings.RAZORPAY_PLATFORM_FEE_PERCENT = 5
        settings.RAZORPAYX_ACCOUNT_NUMBER = "7878780080316316"
        settings.RAZORPAYX_PAYOUT_MODE = "IMPS"
        mock_razorpay.order.create.return_value = {"id": "order_w1"}
        PaymentService.create_order(engagement)
        PaymentService.mark_captured_from_webhook("order_w1", "pay_w1")
        engagement.refresh_from_db()
        PaymentService.release_to_performer(engagement)
        engagement.refresh_from_db()
        return engagement

    def test_notifies_performer_when_payout_settles(
        self, processing, mock_send, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            PaymentService._settle_payout("pout_test", utr="UTR12345")

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == processing.performer
        assert "1900" in kwargs["body"]

    def test_does_not_notify_twice_idempotent(
        self, processing, mock_send, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            PaymentService._settle_payout("pout_test", utr="UTR12345")
            PaymentService._settle_payout("pout_test", utr="UTR12345")

        mock_send.assert_called_once()


@pytest.mark.django_db
@pytest.mark.usefixtures("route_mode")
class TestRefundToClientNotifies:
    def test_notifies_client_on_refund(
        self, engagement, mock_razorpay, mock_send, django_capture_on_commit_callbacks
    ):
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

        with django_capture_on_commit_callbacks(execute=True):
            PaymentService.refund_to_client(engagement)

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == engagement.client
        assert str(engagement.fee) in kwargs["body"]

    def test_does_not_notify_if_not_paid(self, engagement, mock_razorpay, mock_send):
        PaymentService.refund_to_client(engagement)  # status=unpaid, no-op

        mock_send.assert_not_called()
