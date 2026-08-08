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

from users.notifications import send_push_notification

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
                "Performer's payment setup is incomplete. Booking cannot be paid yet."
            )

        client = get_client()

        # ── Resume an open order instead of minting a duplicate (C1 + H1) ──
        # Two tabs, or a retry after an abandoned/failed attempt, must NOT
        # spawn a second live Razorpay order — that is the double-charge race
        # (C1) and the source of orphaned "created" rows (H1). Razorpay binds
        # exactly one successful payment to an order and allows fresh attempts
        # on a created/attempted order, so reusing the open order makes
        # Razorpay itself the dedup layer. A resumed Route order still carries
        # its original held-transfer spec, so escrow survives resumption.
        existing = (
            engagement.payments.filter(status="created").order_by("-created_at").first()
        )
        if existing:
            rz_order = client.order.fetch(existing.razorpay_order_id)
            if rz_order.get("status") in ("created", "attempted", "paid"):
                # created/attempted → still payable on the same order.
                # paid → a capture we haven't recorded yet; let the webhook /
                # verify_and_capture reconcile it on the same order_id.
                return {
                    "order_id": existing.razorpay_order_id,
                    "amount": existing.amount * 100,
                    "currency": "INR",
                    "key_id": settings.RAZORPAY_KEY_ID,
                }
            # Terminal/unknown state on Razorpay's side → retire our stale row
            # and fall through to mint a fresh order.
            existing.status = "failed"
            existing.save(update_fields=["status", "updated_at"])

        platform_fee, performer_share = PaymentService._split_amount(engagement.fee)
        amount_paise = engagement.fee * 100

        # Identical base payload in both modes.
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"eng_{engagement.pk}",
            "notes": {"engagement_id": str(engagement.pk)},
        }
        if settings.RAZORPAY_ROUTE_ENABLED:
            # Route: split at collection time; the held transfer IS the escrow.
            order_data["transfers"] = [
                {
                    "account": performer_profile.razorpay_account_id,
                    "amount": performer_share * 100,
                    "currency": "INR",
                    "notes": {"engagement_id": str(engagement.pk)},
                    "on_hold": 1,  # HOLD in escrow until event passes
                }
            ]

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
            "amount": amount_paise,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
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
                f"Payment {payment.pk} is already in terminal state {payment.status}."
            )

        engagement = payment.engagement
        # Duplicate-capture guard (C1). Order reuse in create_order normally
        # prevents two live orders per engagement, but if two DID slip through
        # (a create_order race, or pre-existing duplicates), the second capture
        # must NOT be booked as a second charge. Flag it for refund instead of
        # silently marking it captured while the engagement is already paid.
        if engagement.payment_status != Engagement.PAYMENT_UNPAID:
            payment.razorpay_payment_id = razorpay_payment_id
            payment.status = "failed"
            payment.save(update_fields=["razorpay_payment_id", "status", "updated_at"])
            logger.warning(
                "Duplicate capture blocked: payment %s (order %s) for "
                "already-%s engagement %s — needs refund/reconciliation.",
                payment.pk,
                razorpay_order_id,
                engagement.payment_status,
                engagement.pk,
            )
            return payment

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "captured"
        payment.save(
            update_fields=[
                "razorpay_payment_id",
                "status",
                "updated_at",
            ]
        )

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

        engagement = payment.engagement
        # Duplicate-capture guard (C1), mirroring verify_and_capture. The
        # payment.captured webhook fires for EVERY captured payment, so this is
        # the likeliest path to see a duplicate order's capture — flag it for
        # refund rather than booking a second charge.
        if engagement.payment_status != Engagement.PAYMENT_UNPAID:
            payment.razorpay_payment_id = razorpay_payment_id
            payment.status = "failed"
            payment.save(update_fields=["razorpay_payment_id", "status", "updated_at"])
            logger.warning(
                "Duplicate capture (webhook) blocked: payment %s (order %s) "
                "for already-%s engagement %s — needs refund/reconciliation.",
                payment.pk,
                razorpay_order_id,
                engagement.payment_status,
                engagement.pk,
            )
            return payment

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "captured"
        payment.save(
            update_fields=[
                "razorpay_payment_id",
                "status",
                "updated_at",
            ]
        )
        engagement.payment_status = Engagement.PAYMENT_PAID
        engagement.paid_at = timezone.now()
        engagement.save(update_fields=["payment_status", "paid_at"])
        return payment

    # ── Signal 2: Release money to performer ────────────────────────
    @staticmethod
    def release_to_performer(engagement: Engagement) -> None:
        """
        Called by Celery once the dispute window closes. Idempotent. Skipped if
        the engagement was disputed by the client — those wait for admin action.

        Route ON  — unholds the escrowed transfer → released (terminal here).
        Route OFF — fires a RazorpayX payout → payout_processing. The terminal
                    'released' arrives when the payout.processed webhook lands.

        NOT wrapped in a single @transaction.atomic: payouts mode delegates to
        initiate_payout, whose crash-safe idempotency (C2) requires its own
        steps to commit independently of any outer transaction. The Route
        branch keeps its own atomic block.
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
        with transaction.atomic():
            payment = engagement.payments.filter(status="captured").latest("created_at")

            client = get_client()
            # Razorpay returns a list of transfers because Route supports
            # multi-account splits. We create only one transfer per order, but
            # the loop handles both cases identically.
            transfers = client.payment.transfers(payment.razorpay_payment_id)
            items = transfers.get("items", [])
            if not items:
                # Capture succeeded but the split never materialized (H5) —
                # e.g. transfer creation failed at capture. Do NOT mark
                # released: leave the engagement PAID so it stays visible and
                # alert an admin to reconcile manually.
                logger.critical(
                    "Route release: payment %s captured but has NO transfers — "
                    "the split never happened. Manual action required.",
                    payment.pk,
                )
                return

            for t in items:
                client.transfer.edit(t["id"], {"on_hold": 0})
                payment.razorpay_transfer_id = t["id"]

            payment.status = "released"
            payment.save(
                update_fields=[
                    "status",
                    "razorpay_transfer_id",
                    "updated_at",
                ]
            )
            engagement.payment_status = Engagement.PAYMENT_RELEASED
            engagement.released_at = timezone.now()
            engagement.save(update_fields=["payment_status", "released_at"])

        send_push_notification(
            user=engagement.performer,
            title="Payment sent!",
            body=f"₹{payment.performer_share} has been sent to your bank account",
            data={"screen": "Bookings", "id": engagement.pk},
        )

    # ── Payouts mode: ensure a RazorpayX fund account exists ────────
    @staticmethod
    def ensure_payout_destination(profile) -> str:
        """
        Returns the performer's RazorpayX fund_account_id, creating the Contact
        + Fund Account on first use and caching both ids on Profile so every
        later payout is a single API call. Safe to call repeatedly.

        Cache invalidation (H3): the fund account is keyed to a hash of the
        bank details it was built from. If the performer edits those details
        the hash stops matching, so we discard the stale fund account and
        build a fresh one instead of paying the old bank forever.

        On every (re)creation we fire a proactive penny-drop validation
        (Rec 11) so bad details surface before a payout is attempted.
        """
        from . import razorpayx

        current_bank_hash = hashlib.md5(
            f"{profile.bank_ifsc}:{profile.bank_account_number}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:16]

        if profile.razorpayx_fund_account_id:
            if profile._bank_details_hash == current_bank_hash:
                return profile.razorpayx_fund_account_id
            # Bank details changed since we built the cached fund account.
            # The old fund account stays on RazorpayX (harmless, never used
            # again); we rebuild below against the new details.
            logger.info(
                "Bank details changed for user %s — rebuilding fund account.",
                profile.user_id,
            )
            profile.razorpayx_fund_account_id = ""
            profile.save(update_fields=["razorpayx_fund_account_id"])

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
        profile._bank_details_hash = current_bank_hash
        profile.save(update_fields=["razorpayx_fund_account_id", "_bank_details_hash"])

        # Proactive penny-drop validation of the fresh fund account (Rec 11).
        # The hash gate above guarantees changed details always reach here.
        # Most validations complete inline; slow ones (T+2) finish via the
        # fund_account.validation.completed webhook.
        validation = razorpayx.validate_fund_account(fa["id"])
        profile.razorpayx_validation_id = validation.get("id", "")
        profile.bank_validation_status = "pending"
        profile.save(
            update_fields=["razorpayx_validation_id", "bank_validation_status"]
        )
        if validation.get("status") == "completed":
            PaymentService._apply_validation_result(profile, validation)

        return fa["id"]

    @staticmethod
    def _apply_validation_result(profile, validation: dict) -> None:
        """
        Interpret a Fund Account Validation result — inline or via the
        fund_account.validation.completed webhook — and set
        bank_validation_status.

        Razorpay's status "completed" only means the RESULTS are in, not that
        the account is valid: the real answer is results.account_status plus a
        registered-name match against what the performer entered.
        """
        results = validation.get("results") or {}
        account_active = results.get("account_status") == "active"
        registered = (results.get("registered_name") or "").strip().lower()
        entered = (profile.bank_account_holder_name or "").strip().lower()
        # Exact match is strict for Indian bank records (initials, honorifics).
        # Start strict; relax to normalized/fuzzy or an admin review queue if
        # false rejections show up in practice.
        name_ok = bool(registered) and registered == entered

        if account_active and name_ok:
            profile.bank_validation_status = "valid"
            profile.save(update_fields=["bank_validation_status"])
        else:
            # Never pay out to an account that failed validation. Clearing the
            # cached fund account also forces a rebuild + revalidate if the
            # performer later fixes their details.
            profile.bank_validation_status = "invalid"
            profile.razorpayx_fund_account_id = ""
            profile.save(
                update_fields=[
                    "bank_validation_status",
                    "razorpayx_fund_account_id",
                ]
            )
            logger.warning(
                "Bank validation failed for user %s: account_status=%s name_ok=%s",
                profile.user_id,
                results.get("account_status"),
                name_ok,
            )

    # ── Payouts mode: create the payout (money OUT) ─────────────────
    @staticmethod
    def initiate_payout(engagement: Engagement) -> None:
        """
        Fire a RazorpayX payout for the performer's share. Sets
        payout_processing; the terminal 'released' arrives via webhook.

        Crash-safe idempotency (C2). The RazorpayX call is deliberately made
        OUTSIDE any DB transaction, bracketed by two committed steps:

          Step 1 (atomic) — lock the payable row and persist the idempotency
              key. If a prior attempt already saved a key but never recorded a
              payout_id (a crash between the API call and step 3), REUSE that
              key so Razorpay dedups to the existing payout instead of creating
              a duplicate. A retry after a genuine failure (payout_failed) mints
              a fresh key so it isn't deduped back to the failure.
          Step 2 (no transaction) — fire the payout with that key.
          Step 3 (atomic) — record payout_id + advance the state machine.

        Because the key is committed in step 1 before any money moves, a crash
        anywhere after it is recoverable: the next run reuses the key. This is
        the fix for the fresh-key-per-attempt double-payout hole.
        """
        from . import razorpayx

        # Step 1 — durably persist the idempotency key BEFORE any API call.
        with transaction.atomic():
            payment = (
                engagement.payments.select_for_update()
                # payout_reversed included so a post-settlement reversal (C3)
                # can be re-paid — the performer's money bounced back and they
                # were never actually paid.
                .filter(status__in=["captured", "payout_failed", "payout_reversed"])
                .order_by("-created_at")
                .first()
            )
            if payment is None:
                return  # nothing payable (already processing/released)

            if payment.payout_idempotency_key and not payment.razorpayx_payout_id:
                # Prior attempt saved a key but never recorded the payout_id
                # (DB committed step 1 but step 3 never landed). Reuse the key —
                # Razorpay returns the same payout, no duplicate.
                key = payment.payout_idempotency_key
            else:
                key = razorpayx.new_idempotency_key()
                payment.payout_idempotency_key = key
                payment.save(update_fields=["payout_idempotency_key", "updated_at"])
            payment_pk = payment.pk
            performer_share = payment.performer_share

        # Step 2 — API calls OUTSIDE the atomic block. If these raise, the key
        # is already saved and the next retry reuses it.
        fund_account_id = PaymentService.ensure_payout_destination(
            engagement.performer.profile
        )
        payout = razorpayx.create_payout(
            fund_account_id=fund_account_id,
            amount_paise=performer_share * 100,
            reference_id=f"eng_{engagement.pk}",
            narration=f"ArtKhoj payout {engagement.pk}",  # alnum+space, ≤30
            idempotency_key=key,
        )

        # Step 3 — record the result and advance the state machine.
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_pk)
            payment.razorpayx_payout_id = payout["id"]
            payment.status = "payout_processing"
            payment.save(update_fields=["razorpayx_payout_id", "status", "updated_at"])
            eng = payment.engagement
            eng.payment_status = Engagement.PAYMENT_PAYOUT_PROCESSING
            eng.payout_initiated_at = timezone.now()
            eng.save(update_fields=["payment_status", "payout_initiated_at"])

    # ── Signal 3: Refund to client ──────────────────────────────────
    @staticmethod
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

        Crash-safe (C4), mirroring initiate_payout. The Razorpay refund is made
        OUTSIDE any transaction, bracketed by:
          Step 1 (atomic) — flip the row to refund_pending. A crash after the
              API call then can't leave the row looking capturable, so Celery
              won't try to release money Razorpay already refunded.
          Step 2 (no transaction) — issue the irreversible refund.
          Step 3 (atomic) — record refund_id + REFUNDED. If this never lands,
              the row stays refund_pending and the refund.processed webhook
              reconciles it by razorpay_payment_id; an admin can see and act.
        """
        if engagement.payment_status != Engagement.PAYMENT_PAID:
            return

        # Step 1 — durable "refund in progress" marker before touching Razorpay.
        with transaction.atomic():
            payment = (
                engagement.payments.select_for_update()
                .filter(status="captured")
                .latest("created_at")
            )
            payment.status = "refund_pending"
            payment.save(update_fields=["status", "updated_at"])
            engagement.payment_status = Engagement.PAYMENT_REFUND_PENDING
            engagement.save(update_fields=["payment_status"])
            payment_pk = payment.pk
            payment_id = payment.razorpay_payment_id

        # Step 2 — issue the refund OUTSIDE the transaction (irreversible).
        client = get_client()
        refund_data = {
            "notes": {
                "engagement_id": str(engagement.pk),
                "reason": (
                    engagement.cancellation_reason or engagement.dispute_reason or ""
                )[:200],
            },
        }
        if settings.RAZORPAY_ROUTE_ENABLED:
            refund_data["reverse_all"] = 1
        refund = client.payment.refund(payment_id, refund_data)

        # Step 3 — record the terminal refunded state.
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment_pk)
            payment.razorpay_refund_id = refund["id"]
            payment.status = "refunded"
            payment.save(update_fields=["razorpay_refund_id", "status", "updated_at"])
            eng = payment.engagement
            eng.payment_status = Engagement.PAYMENT_REFUNDED
            eng.refunded_at = timezone.now()
            eng.save(update_fields=["payment_status", "refunded_at"])

        send_push_notification(
            user=engagement.client,
            title="Refund initiated",
            body=f"₹{engagement.fee} refund initiated — will be credited within 5-7 days",
            data={"screen": "Bookings", "id": engagement.pk},
        )

    # ── Webhook signature verification ──────────────────────────────
    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
        """
        HMAC-SHA256 of the entire raw request body using the webhook secret.
        Returns True only on exact match. Uses compare_digest to dodge
        timing attacks.
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.error("Webhook received but RAZORPAY_WEBHOOK_SECRET not configured.")
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

        elif event_type == "payment.failed":
            # M2: a gateway attempt failed. Mark the still-open "created" row
            # failed so it's visible and create_order mints a fresh order next
            # time rather than resuming a dead one. The status="created" filter
            # never touches an already-captured success.
            entity = payload["payment"]["entity"]
            order_id = entity.get("order_id")
            if order_id:
                Payment.objects.filter(
                    razorpay_order_id=order_id, status="created"
                ).update(status="failed")

        elif event_type == "refund.processed":
            # H2 + C4 backstop. Match by payment_id (the refund_id may have been
            # rolled back in the C4 window) and drive BOTH Payment and
            # Engagement to the terminal refunded state — the old handler
            # updated only the Payment row, leaving the engagement desynced.
            entity = payload["refund"]["entity"]
            payment_id = entity.get("payment_id")
            with transaction.atomic():
                payment = (
                    Payment.objects.select_for_update()
                    .filter(
                        razorpay_payment_id=payment_id,
                        status__in=["captured", "refund_pending"],
                    )
                    .first()
                )
                if payment:
                    payment.razorpay_refund_id = entity.get("id", "")
                    payment.status = "refunded"
                    payment.save(
                        update_fields=[
                            "razorpay_refund_id",
                            "status",
                            "updated_at",
                        ]
                    )
                    eng = payment.engagement
                    eng.payment_status = Engagement.PAYMENT_REFUNDED
                    eng.refunded_at = timezone.now()
                    eng.save(update_fields=["payment_status", "refunded_at"])

        elif event_type == "refund.failed":
            # H4: Razorpay accepted the refund (200) but it later failed at the
            # bank. Never leave the DB claiming "refunded" — flip the Payment to
            # refund_failed and re-show the money as held so an admin can retry.
            entity = payload["refund"]["entity"]
            with transaction.atomic():
                payment = (
                    Payment.objects.select_for_update()
                    .filter(razorpay_refund_id=entity.get("id"))
                    .first()
                )
                if payment:
                    payment.status = "refund_failed"
                    payment.save(update_fields=["status", "updated_at"])
                    eng = payment.engagement
                    eng.payment_status = Engagement.PAYMENT_PAID
                    eng.refunded_at = None
                    eng.save(update_fields=["payment_status", "refunded_at"])
            logger.error(
                "Refund FAILED at bank: refund %s — client not refunded, "
                "manual action required.",
                entity.get("id"),
            )

        elif event_type == "transfer.processed":
            # H2 (Route): the held transfer settled. Drive Payment AND
            # Engagement to released, not just the Payment row.
            entity = payload["transfer"]["entity"]
            with transaction.atomic():
                payment = (
                    Payment.objects.select_for_update()
                    .filter(razorpay_transfer_id=entity.get("id"))
                    .first()
                )
                if payment:
                    payment.status = "released"
                    payment.save(update_fields=["status", "updated_at"])
                    eng = payment.engagement
                    if eng.payment_status != Engagement.PAYMENT_RELEASED:
                        eng.payment_status = Engagement.PAYMENT_RELEASED
                        eng.released_at = timezone.now()
                        eng.save(update_fields=["payment_status", "released_at"])

        elif event_type == "transfer.failed":
            # M1 (Route): transfer creation/settlement failed — the client was
            # charged but the performer's split is broken. Alert; admin acts.
            entity = payload["transfer"]["entity"]
            logger.critical(
                "Route transfer %s FAILED (source payment %s) — client charged, "
                "performer split broken. Manual action required.",
                entity.get("id"),
                entity.get("source"),
            )

        elif event_type in (
            "account.activated",
            "account.under_review",
            "account.suspended",
            "account.rejected",
        ):
            # M3 (Route): keep the performer's KYC status in sync with Razorpay
            # instead of relying on manual admin updates.
            entity = payload.get("account", {}).get("entity", {})
            account_id = entity.get("id")
            if account_id:
                kyc = {
                    "account.activated": "approved",
                    "account.under_review": "pending",
                    "account.suspended": "rejected",
                    "account.rejected": "rejected",
                }[event_type]
                from users.models import Profile

                Profile.objects.filter(razorpay_account_id=account_id).update(
                    razorpay_kyc_status=kyc
                )

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
        event_type = event.get("event")
        payload = event.get("payload", {})

        # Fund Account Validation result (Rec 11). Arrives on the SAME RazorpayX
        # webhook endpoint but with a different entity shape, so handle it
        # before reaching for a payout entity.
        if event_type == "fund_account.validation.completed":
            entity = payload.get("fund_account.validation", {}).get("entity", {})
            validation_id = entity.get("id")
            if not validation_id:
                return
            from users.models import Profile

            profile = Profile.objects.filter(
                razorpayx_validation_id=validation_id
            ).first()
            if profile:
                PaymentService._apply_validation_result(profile, entity)
            return

        entity = payload.get("payout", {}).get("entity", {})
        payout_id = entity.get("id")
        if not payout_id:
            return

        if event_type == "payout.processed":
            # Money reached the performer's bank. Terminal success.
            PaymentService._settle_payout(payout_id, utr=entity.get("utr") or "")
        elif event_type == "payout.updated" and entity.get("utr"):
            # UTR often lands here first — capture it for the audit trail
            # without changing state.
            Payment.objects.filter(razorpayx_payout_id=payout_id).update(
                payout_reference=entity["utr"]
            )
        elif event_type in ("payout.reversed", "payout.failed"):
            # Money bounced back to our balance. Flag for retry — event_type
            # lets _fail_payout distinguish a genuine post-settlement reversal
            # (C3) from a late failure racing a settle.
            PaymentService._fail_payout(payout_id, event_type=event_type)
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

        send_push_notification(
            user=eng.performer,
            title="Payment sent!",
            body=f"₹{payment.performer_share} has been sent to your bank account",
            data={"screen": "Bookings", "id": eng.pk},
        )

    @staticmethod
    @transaction.atomic
    def _fail_payout(payout_id: str, event_type: str = "") -> None:
        """
        payout.reversed/failed → flag for admin retry. Idempotent.

        Reversal after settlement (C3): a payout can move processed → reversed
        within T+3 working days. When that reversal lands on an already-released
        row we must REOPEN it — the money bounced back to our balance and the
        performer was NOT paid. A late payout.failed merely racing a settle
        keeps the success (settle already won).
        """
        try:
            payment = Payment.objects.select_for_update().get(
                razorpayx_payout_id=payout_id
            )
        except Payment.DoesNotExist:
            return

        if payment.status in ("payout_failed", "payout_reversed"):
            return  # already flagged — idempotent for webhook retries

        if payment.status == "released":
            if event_type == "payout.reversed":
                # Genuine reversal AFTER a successful settlement. Undo the
                # release so the engagement re-surfaces for a manual re-payout.
                payment.status = "payout_reversed"
                payment.save(update_fields=["status", "updated_at"])
                eng = payment.engagement
                eng.payment_status = Engagement.PAYMENT_PAYOUT_FAILED
                eng.released_at = None  # it never truly settled
                eng.save(update_fields=["payment_status", "released_at"])
                logger.critical(
                    "PAYOUT REVERSED after settlement: payment %s, engagement "
                    "%s. Performer was NOT paid. Manual re-payout needed.",
                    payment.pk,
                    eng.pk,
                )
                return
            # Late payout.failed racing a settle — keep the success.
            return

        payment.status = "payout_failed"
        payment.save(update_fields=["status", "updated_at"])
        eng = payment.engagement
        eng.payment_status = Engagement.PAYMENT_PAYOUT_FAILED
        eng.save(update_fields=["payment_status"])
