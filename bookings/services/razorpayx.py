"""
RazorpayX Payouts API client (raw HTTP).

The pinned razorpay-python SDK (1.4.2) wraps only the Payment Gateway — it has
no Payout or Contact resource (confirmed against SDK 2.0.1 too; Razorpay never
added RazorpayX to the SDK) — so RazorpayX endpoints are called directly over
HTTPS here. Auth is identical to the gateway (Basic auth with key_id:key_secret);
RazorpayX simply exposes extra endpoints on the same host.

This module is the ONLY place that talks to the RazorpayX API. It is thin and
stateless: PaymentService orchestrates persistence and state transitions. Every
payout is created with an idempotency key so a retried request never double-pays.
"""
import hashlib
import hmac
import logging
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.razorpay.com/v1"
_TIMEOUT = 30  # seconds. Payouts aren't latency-sensitive; prefer a slow, safe fail.


def _auth():
    """Basic-auth tuple — SAME keys as the gateway (see razorpay_client)."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError(
            "RazorpayX is not configured. Set RAZORPAY_KEY_ID and "
            "RAZORPAY_KEY_SECRET in the environment."
        )
    return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)


def _post(path: str, payload: dict, idempotency_key: str | None = None) -> dict:
    """
    POST helper. Raises requests.HTTPError on any non-2xx so the caller can
    decide how to record the failure — never swallows errors silently.

    When idempotency_key is passed, Razorpay guarantees it will NOT create two
    payouts for the same key even if this exact request is retried at the
    network layer.
    """
    headers = {"Content-Type": "application/json"}
    if idempotency_key:
        headers["X-Payout-Idempotency"] = idempotency_key
    resp = requests.post(
        f"{_BASE}/{path}", json=payload, headers=headers,
        auth=_auth(), timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def new_idempotency_key() -> str:
    """A fresh UUID for one payout attempt. Rotated on a retry-after-failure."""
    return str(uuid.uuid4())


def create_contact(name: str, email: str, phone: str, reference_id: str) -> dict:
    """
    POST /v1/contacts — the beneficiary (performer). reference_id is our own
    stable handle (e.g. "user_42") for reconciliation. Returns {id: "cont_..."}.
    """
    return _post("contacts", {
        "name": (name or "Performer")[:50],
        "email": email or "",
        "contact": phone or "",
        "type": "vendor",            # performers are paid like vendors
        "reference_id": reference_id,
    })


def create_fund_account(contact_id: str, name: str, ifsc: str,
                        account_number: str) -> dict:
    """
    POST /v1/fund_accounts — the performer's bank account, linked to a contact.
    Returns {id: "fa_..."}. This is the destination a payout targets.
    """
    return _post("fund_accounts", {
        "contact_id": contact_id,
        "account_type": "bank_account",
        "bank_account": {
            "name": name,
            "ifsc": ifsc,
            "account_number": account_number,
        },
    })


def create_payout(fund_account_id: str, amount_paise: int, reference_id: str,
                  narration: str, idempotency_key: str) -> dict:
    """
    POST /v1/payouts — move money from OUR RazorpayX balance
    (RAZORPAYX_ACCOUNT_NUMBER) to the performer's fund account. Returns
    {id: "pout_...", status: "queued"|"processing", utr: null, ...}. The
    terminal 'processed' status arrives later via the payout.processed webhook.

    queue_if_low_balance=True means a temporary shortfall queues the payout
    (auto-processed when funds arrive) instead of hard-failing.
    """
    return _post("payouts", {
        "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,   # OUR source acct
        "fund_account_id": fund_account_id,
        "amount": amount_paise,
        "currency": "INR",
        "mode": settings.RAZORPAYX_PAYOUT_MODE,                # IMPS/NEFT/RTGS
        "purpose": "payout",                                   # built-in purpose
        "queue_if_low_balance": True,
        "reference_id": reference_id[:40],   # Razorpay caps at 40 chars
        "narration": narration[:30],         # caps at 30, [a-zA-Z0-9 ] only
    }, idempotency_key=idempotency_key)


def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    HMAC-SHA256 over the RAW request body using the RazorpayX webhook secret
    (distinct from the gateway's RAZORPAY_WEBHOOK_SECRET). compare_digest to
    dodge timing attacks. Never parse the body before hashing.
    """
    secret = settings.RAZORPAYX_WEBHOOK_SECRET
    if not secret:
        logger.error(
            "RazorpayX webhook received but RAZORPAYX_WEBHOOK_SECRET not set."
        )
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")
