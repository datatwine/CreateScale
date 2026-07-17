"""
The Razorpay translator.

This module is the ONLY place that talks to Razorpay's API. Views call into
PaymentService; PaymentService calls Razorpay. If engagement rules change,
the views change — this file stays stable.

Every public method is idempotent: safe to call twice with the same input.
That property is critical because:
  - The browser callback and webhook may both fire for the same payment.
  - Webhooks can arrive multiple times due to Razorpay's retry policy.
"""
import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Engagement, Payment
from .razorpay_client import get_client

logger = logging.getLogger(__name__)


class PaymentService:
    """Thin layer between bookings/views.py and the razorpay SDK."""

    # ── Fee split helper ────────────────────────────────────────────
    @staticmethod
    def _split_amount(total_rupees: int) -> tuple[int, int]:
        """Returns (platform_fee_rupees, performer_share_rupees)."""
        fee_pct = settings.RAZORPAY_PLATFORM_FEE_PERCENT
        platform_fee = int(total_rupees * fee_pct / 100)
        return platform_fee, total_rupees - platform_fee

    # ── Signal 1: Charge this client ────────────────────────────────
    @staticmethod
    def create_order(engagement: Engagement) -> dict:
        """
        Creates a Razorpay Order; returns {order_id, amount, currency, key_id}
        for the frontend checkout.js to consume. Two modes via
        settings.RAZORPAY_ROUTE_ENABLED:

        Route ON  — the order carries a HELD transfer (on_hold=1) to the
                    performer's linked account. The held transfer IS the escrow
                    until release_to_performer() unholds it; our 5% lands in our
                    balance immediately.
        Route OFF — a plain order, no transfers[]. The full amount lands in our
                    Razorpay balance; the Payment row's performer_share is the
                    ledger of what we owe and pay out via RazorpayX after the
                    event.
        """
        if engagement.payment_status != Engagement.PAYMENT_UNPAID:
            raise ValueError(
                f"Engagement {engagement.pk} is not in unpaid state "
                f"(current: {engagement.payment_status})."
            )
        if not engagement.fee:
            raise ValueError("Engagement has no fee snapshot.")

        performer_profile = engagement.performer.profile
        # Mode-aware gate (see users/models.py): Route → linked acct approved;
        # Payouts → complete bank details on file.
        if not performer_profile.can_receive_payments:
            raise ValueError(
                "Performer's payment setup is incomplete. Booking cannot be "
                "paid yet."
            )

        platform_fee, performer_share = PaymentService._split_amount(
            engagement.fee
        )
        amount_paise = engagement.fee * 100

        # Identical base payload in both modes.
        order_data = {
            "amount":   amount_paise,
            "currency": "INR",
            "receipt":  f"eng_{engagement.pk}",
            "notes":    {"engagement_id": str(engagement.pk)},
        }
        if settings.RAZORPAY_ROUTE_ENABLED:
            # Route: split at collection time; the held transfer IS the escrow.
            order_data["transfers"] = [{
                "account":  performer_profile.razorpay_account_id,
                "amount":   performer_share * 100,
                "currency": "INR",
                "notes":    {"engagement_id": str(engagement.pk)},
                "on_hold":  1,   # HOLD in escrow until event passes
            }]

        client = get_client()
        order = client.order.create(order_data)

        # Persist our side of the world. Order is created on Razorpay first;
        # if THAT call fails we never reach this line and no Payment row is
        # written — keeping our DB consistent with Razorpay's view.
        Payment.objects.create(
            engagement=engagement,
            amount=engagement.fee,
            platform_fee=platform_fee,
            performer_share=performer_share,
            razorpay_order_id=order["id"],
            status="created",
        )

        return {
            "order_id": order["id"],
            "amount":   amount_paise,
            "currency": "INR",
            "key_id":   settings.RAZORPAY_KEY_ID,
        }

    # ── Verify checkout callback (browser → backend) ────────────────
    @staticmethod
    @transaction.atomic
    def verify_and_capture(
        razorpay_order_id: str,
        razorpay_payment_id: str,
        signature: str,
    ) -> Payment:
        """
        Verifies the HMAC signature from checkout.js callback and marks the
        payment captured. Idempotent — safe to call again after success.

        HMAC layout: SHA256(secret_key, "order_id|payment_id"). If our local
        recomputation matches what the browser forwarded, the callback is
        genuine (only Razorpay knows our secret).
        """
        body = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid signature")

        # Row-level lock prevents the webhook path from racing with us.
        payment = Payment.objects.select_for_update().get(
            razorpay_order_id=razorpay_order_id
        )
        if payment.status == "captured":
            return payment  # already done — no-op
        if payment.status in ("released", "refunded"):
            raise ValueError(
                f"Payment {payment.pk} is already in terminal state "
                f"{payment.status}."
            )

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "captured"
        payment.save(update_fields=[
            "razorpay_payment_id", "status", "updated_at",
        ])

        engagement = payment.engagement
        if engagement.payment_status == Engagement.PAYMENT_UNPAID:
            engagement.payment_status = Engagement.PAYMENT_PAID
            engagement.paid_at = timezone.now()
            engagement.save(update_fields=["payment_status", "paid_at"])
        return payment

    # ── Webhook capture path (no checkout signature available) ──────
    @staticmethod
    @transaction.atomic
    def mark_captured_from_webhook(
        razorpay_order_id: str,
        razorpay_payment_id: str,
    ) -> Payment:
        """
        Webhook delivered a payment.captured event. The webhook envelope's
        HMAC was already verified upstream (in razorpay_webhook view), so we
        skip the checkout signature here. Same idempotency guards as
        verify_and_capture, just a different entry point.
        """
        payment = Payment.objects.select_for_update().get(
            razorpay_order_id=razorpay_order_id
        )
        if payment.status == "captured":
            return payment
        if payment.status in ("released", "refunded"):
            return payment  # webhook arrived late; do nothing

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "captured"
        payment.save(update_fields=[
            "razorpay_payment_id", "status", "updated_at",
        ])
        engagement = payment.engagement
        if engagement.payment_status == Engagement.PAYMENT_UNPAID:
            engagement.payment_status = Engagement.PAYMENT_PAID
            engagement.paid_at = timezone.now()
            engagement.save(update_fields=["payment_status", "paid_at"])
        return payment

    # ── Signal 2: Release money to performer ────────────────────────
    @staticmethod
    @transaction.atomic
    def release_to_performer(engagement: Engagement) -> None:
        """
        Called by Celery once the dispute window closes. Idempotent. Skipped if
        the engagement was disputed by the client — those wait for admin action.

        Route ON  — unholds the escrowed transfer → released (terminal here).
        Route OFF — fires a RazorpayX payout → payout_processing. The terminal
                    'released' arrives when the payout.processed webhook lands.
        """
        if engagement.payment_status != Engagement.PAYMENT_PAID:
            return
        if engagement.disputed_at is not None:
            logger.info(
                "release_to_performer: skipping disputed engagement %s",
                engagement.pk,
            )
            return

        if not settings.RAZORPAY_ROUTE_ENABLED:
            # ── Payouts mode: fire the RazorpayX payout (async) ──────────
            PaymentService.initiate_payout(engagement)
            return

        # ── Route mode: unhold the escrowed transfer ─────────────────────
        payment = engagement.payments.filter(status="captured").latest(
            "created_at"
        )

        client = get_client()
        # Razorpay returns a list of transfers because Route supports
        # multi-account splits. We create only one transfer per order, but
        # the loop handles both cases identically.
        transfers = client.payment.transfers(payment.razorpay_payment_id)
        for t in transfers.get("items", []):
            client.transfer.edit(t["id"], {"on_hold": 0})
            payment.razorpay_transfer_id = t["id"]

        payment.status = "released"
        payment.save(update_fields=[
            "status", "razorpay_transfer_id", "updated_at",
        ])
        engagement.payment_status = Engagement.PAYMENT_RELEASED
        engagement.released_at = timezone.now()
        engagement.save(update_fields=["payment_status", "released_at"])

    # ── Payouts mode: ensure a RazorpayX fund account exists ────────
    @staticmethod
    def ensure_payout_destination(profile) -> str:
        """
        Returns the performer's RazorpayX fund_account_id, creating the Contact
        + Fund Account on first use and caching both ids on Profile so every
        later payout is a single API call. Safe to call repeatedly.
        """
        from . import razorpayx
        if profile.razorpayx_fund_account_id:
            return profile.razorpayx_fund_account_id

        if not profile.razorpayx_contact_id:
            contact = razorpayx.create_contact(
                name=profile.bank_account_holder_name,
                email=profile.user.email,
                phone=profile.phone_number,
                reference_id=f"user_{profile.user_id}",
            )
            profile.razorpayx_contact_id = contact["id"]
            profile.save(update_fields=["razorpayx_contact_id"])

        fa = razorpayx.create_fund_account(
            contact_id=profile.razorpayx_contact_id,
            name=profile.bank_account_holder_name,
            ifsc=profile.bank_ifsc,
            account_number=profile.bank_account_number,
        )
        profile.razorpayx_fund_account_id = fa["id"]
        profile.save(update_fields=["razorpayx_fund_account_id"])
        return fa["id"]

    # ── Payouts mode: create the payout (money OUT) ─────────────────
    @staticmethod
    @transaction.atomic
    def initiate_payout(engagement: Engagement) -> None:
        """
        Fire a RazorpayX payout for the performer's share. Sets
        payout_processing; the terminal 'released' arrives via webhook.

        Idempotent at three layers:
          1. Row lock (select_for_update) serializes concurrent releases.
          2. Status guard — only acts from 'captured' or 'payout_failed'.
          3. X-Payout-Idempotency header stops Razorpay double-creating.
        """
        from . import razorpayx
        payment = (
            engagement.payments.select_for_update()
            .filter(status__in=["captured", "payout_failed"])
            .order_by("-created_at")
            .first()
        )
        if payment is None:
            return  # nothing payable (already processing/released, or no capture)

        fund_account_id = PaymentService.ensure_payout_destination(
            engagement.performer.profile
        )
        # Fresh key per attempt: a retry after a real failure must NOT be
        # deduped back to the failed payout.
        key = razorpayx.new_idempotency_key()
        payout = razorpayx.create_payout(
            fund_account_id=fund_account_id,
            amount_paise=payment.performer_share * 100,
            reference_id=f"eng_{engagement.pk}",
            narration=f"ArtKhoj payout {engagement.pk}",  # alnum+space, ≤30
            idempotency_key=key,
        )

        payment.razorpayx_payout_id = payout["id"]
        payment.payout_idempotency_key = key
        payment.status = "payout_processing"
        payment.save(update_fields=[
            "razorpayx_payout_id", "payout_idempotency_key",
            "status", "updated_at",
        ])
        engagement.payment_status = Engagement.PAYMENT_PAYOUT_PROCESSING
        engagement.payout_initiated_at = timezone.now()
        engagement.save(update_fields=[
            "payment_status", "payout_initiated_at",
        ])

    # ── Signal 3: Refund to client ──────────────────────────────────
    @staticmethod
    @transaction.atomic
    def refund_to_client(engagement: Engagement) -> None:
        """
        Full refund to the client. Idempotent; a no-op unless payment_status
        is PAID (so it can't collide with a payout — payouts only start after
        the dispute window, refunds fire from PAID).

        Route ON  — reverse_all=1 also cancels the linked held transfer, so the
                    performer's escrowed share unwinds back to the client with
                    no manual reconciliation.
        Route OFF — nothing to reverse: the money never left our balance (no
                    payout has fired yet). A plain refund makes the client whole.
        """
        if engagement.payment_status != Engagement.PAYMENT_PAID:
            return

        payment = engagement.payments.filter(status="captured").latest(
            "created_at"
        )
        client = get_client()
        refund_data = {
            "notes": {
                "engagement_id": str(engagement.pk),
                "reason": (
                    engagement.cancellation_reason
                    or engagement.dispute_reason
                    or ""
                )[:200],
            },
        }
        if settings.RAZORPAY_ROUTE_ENABLED:
            refund_data["reverse_all"] = 1
        refund = client.payment.refund(payment.razorpay_payment_id, refund_data)
        payment.razorpay_refund_id = refund["id"]
        payment.status = "refunded"
        payment.save(update_fields=[
            "razorpay_refund_id", "status", "updated_at",
        ])
        engagement.payment_status = Engagement.PAYMENT_REFUNDED
        engagement.refunded_at = timezone.now()
        engagement.save(update_fields=["payment_status", "refunded_at"])

    # ── Webhook signature verification ──────────────────────────────
    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes, signature_header: str
    ) -> bool:
        """
        HMAC-SHA256 of the entire raw request body using the webhook secret.
        Returns True only on exact match. Uses compare_digest to dodge
        timing attacks.
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.error(
                "Webhook received but RAZORPAY_WEBHOOK_SECRET not configured."
            )
            return False
        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header or "")

    # ── Webhook event router ────────────────────────────────────────
    @staticmethod
    def handle_webhook_event(event: dict) -> None:
        """
        Routes a verified webhook event to the right handler. All handlers
        are idempotent — the same event can fire twice without side effects.
        """
        event_type = event.get("event")
        payload = event.get("payload", {})

        if event_type == "payment.captured":
            entity = payload["payment"]["entity"]
            try:
                PaymentService.mark_captured_from_webhook(
                    entity["order_id"], entity["id"]
                )
            except Payment.DoesNotExist:
                logger.warning(
                    "Webhook payment.captured for unknown order %s",
                    entity.get("order_id"),
                )
        elif event_type == "refund.processed":
            entity = payload["refund"]["entity"]
            Payment.objects.filter(
                razorpay_refund_id=entity["id"]
            ).update(status="refunded")
        elif event_type == "transfer.processed":
            entity = payload["transfer"]["entity"]
            Payment.objects.filter(
                razorpay_transfer_id=entity["id"]
            ).update(status="released")
        else:
            logger.info("Unhandled webhook event: %s", event_type)

    # ── RazorpayX payout webhook router (payouts mode) ──────────────
    @staticmethod
    def handle_payout_webhook_event(event: dict) -> None:
        """
        Routes a VERIFIED RazorpayX payout webhook to a state transition. All
        handlers are idempotent — RazorpayX retries, and events can arrive out
        of order (updated before processed, etc.).
        """
        entity = (
            event.get("payload", {}).get("payout", {}).get("entity", {})
        )
        payout_id = entity.get("id")
        if not payout_id:
            return

        event_type = event.get("event")
        if event_type == "payout.processed":
            # Money reached the performer's bank. Terminal success.
            PaymentService._settle_payout(payout_id, utr=entity.get("utr") or "")
        elif event_type == "payout.updated" and entity.get("utr"):
            # UTR often lands here first — capture it for the audit trail
            # without changing state.
            Payment.objects.filter(
                razorpayx_payout_id=payout_id
            ).update(payout_reference=entity["utr"])
        elif event_type in ("payout.reversed", "payout.failed"):
            # Money bounced back to our balance. Flag for retry.
            PaymentService._fail_payout(payout_id)
        else:
            logger.info("Unhandled RazorpayX payout event: %s", event_type)

    @staticmethod
    @transaction.atomic
    def _settle_payout(payout_id: str, utr: str = "") -> None:
        """payout.processed → mark the Payment + Engagement released. Idempotent."""
        try:
            payment = Payment.objects.select_for_update().get(
                razorpayx_payout_id=payout_id
            )
        except Payment.DoesNotExist:
            logger.warning("payout.processed for unknown payout %s", payout_id)
            return
        if payment.status == "released":
            return  # idempotent no-op
        payment.status = "released"
        if utr:
            payment.payout_reference = utr
        payment.save(update_fields=["status", "payout_reference", "updated_at"])
        eng = payment.engagement
        eng.payment_status = Engagement.PAYMENT_RELEASED
        eng.released_at = timezone.now()
        eng.save(update_fields=["payment_status", "released_at"])

    @staticmethod
    @transaction.atomic
    def _fail_payout(payout_id: str) -> None:
        """payout.reversed/failed → flag for admin retry. Idempotent; a late
        failure racing a settle keeps the success."""
        try:
            payment = Payment.objects.select_for_update().get(
                razorpayx_payout_id=payout_id
            )
        except Payment.DoesNotExist:
            return
        if payment.status == "released":
            return
        payment.status = "payout_failed"
        payment.save(update_fields=["status", "updated_at"])
        eng = payment.engagement
        eng.payment_status = Engagement.PAYMENT_PAYOUT_FAILED
        eng.save(update_fields=["payment_status"])
