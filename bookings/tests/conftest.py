"""
Shared pytest fixtures for the bookings/tests package.

These fixtures spin up minimal but realistic engagement scenarios so each
test file can focus on its specific behavior rather than re-creating
boilerplate. All fixtures use pytest-django's `db` fixture transitively, so
test data is rolled back after each test.
"""

from datetime import date, time, timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from bookings.models import Engagement, Payment
from users.models import Profile


def _refresh_profile_cache(user):
    """
    Django caches the Profile on the User instance the first time
    `user.profile` is accessed. Our post_save signal (`save_profile` in
    users/signals.py) fires on User creation and caches the *default*
    Profile, BEFORE our test overrides via Profile.objects.update_or_create
    have applied. Drop the cache so subsequent `.profile` accesses re-fetch
    from the DB and see our test defaults.
    """
    # OneToOneField descriptor uses a `_<related_name>_cache` attr — here
    # the related accessor is `profile`, so the cache attr is `_profile_cache`.
    for attr in ("_profile_cache", "profile"):
        # Django 5+ uses a "fields_cache" dict on _state, not the legacy
        # attribute. Clear both so we're covered either way.
        user.__dict__.pop(attr, None)
    if hasattr(user, "_state"):
        user._state.fields_cache.pop("profile", None)


@pytest.fixture
def client_user(db):
    """A logged-in-capable client with approved hire permissions."""
    u = User.objects.create_user("client1", password="x")
    # Profile is auto-created by EnsureProfileMiddleware on first login, but
    # tests bypass middleware — so we create/upsert one explicitly here.
    Profile.objects.update_or_create(
        user=u,
        defaults={"is_potential_client": True, "client_approved": True},
    )
    _refresh_profile_cache(u)
    return u


@pytest.fixture
def performer_user(db):
    """A performer payable in BOTH modes: Route linked account approved AND
    complete bank details on file for payouts mode."""
    u = User.objects.create_user("performer1", password="x")
    Profile.objects.update_or_create(
        user=u,
        defaults={
            "is_performer": True,
            "performer_fee": 2000,
            # Route-mode credentials:
            "razorpay_account_id": "acc_test123",
            "razorpay_kyc_status": "approved",
            # Payouts-mode credentials (bank details on file):
            "bank_account_holder_name": "Performer One",
            "bank_account_number": "1234567890",
            "bank_ifsc": "HDFC0001234",
            "pan_number": "ABCDE1234F",
            "phone_number": "9876543210",
        },
    )
    _refresh_profile_cache(u)
    return u


@pytest.fixture
def engagement(client_user, performer_user):
    """A pending engagement 10 days out, with the fee already snapshotted."""
    return Engagement.objects.create(
        client=client_user,
        performer=performer_user,
        date=date.today() + timedelta(days=10),
        time=time(19, 0),
        venue="Test venue",
        occasion="Test occasion",
        fee=2000,
    )


@pytest.fixture
def mock_razorpay(monkeypatch):
    """
    Replaces get_client() with a MagicMock so no test ever hits Razorpay.
    Tests that need to assert on specific Razorpay API calls can read
    `mock_razorpay.order.create.call_args` etc.
    """
    mock_rzp = MagicMock()
    monkeypatch.setattr(
        "bookings.services.payments.get_client",
        lambda: mock_rzp,
    )
    return mock_rzp


@pytest.fixture
def mock_razorpayx(monkeypatch):
    """
    Patch the raw RazorpayX API module so payouts-mode tests never hit HTTP.
    Mirrors mock_razorpay: patches create_contact/create_fund_account/
    create_payout/new_idempotency_key/validate_fund_account to canned values.

    create_payout and validate_fund_account are MagicMocks (not lambdas) so
    tests can assert on call_args — e.g. that the same idempotency_key is
    reused across a crash recovery, or read the validation call — and can
    override return_value per-test (e.g. an "invalid" validation result).
    """
    import bookings.services.razorpayx as rx

    monkeypatch.setattr(rx, "create_contact", lambda **k: {"id": "cont_test"})
    monkeypatch.setattr(rx, "create_fund_account", lambda **k: {"id": "fa_test"})
    monkeypatch.setattr(
        rx,
        "create_payout",
        MagicMock(return_value={"id": "pout_test", "status": "queued"}),
    )
    # Stable key by default so tests asserting an exact value stay simple;
    # rotation tests re-patch this locally.
    monkeypatch.setattr(rx, "new_idempotency_key", lambda: "idem_test")
    # Validation defaults to a clean pass: active account, name matches the
    # performer_user fixture's holder name ("Performer One").
    monkeypatch.setattr(
        rx,
        "validate_fund_account",
        MagicMock(
            return_value={
                "id": "fav_test",
                "status": "completed",
                "results": {
                    "account_status": "active",
                    "registered_name": "Performer One",
                },
            }
        ),
    )
    return rx


@pytest.fixture
def payout_crash_row(engagement):
    """
    A Payment seeded into the exact post-crash state C2 must recover from:
    the idempotency key was committed (step 1) but the payout_id was never
    recorded (step 3 never landed). initiate_payout must REUSE this key rather
    than mint a fresh one, so Razorpay dedups instead of double-paying.
    """
    engagement.payment_status = Engagement.PAYMENT_PAID
    engagement.save()
    return Payment.objects.create(
        engagement=engagement,
        amount=2000,
        platform_fee=100,
        performer_share=1900,
        razorpay_order_id="order_c",
        razorpay_payment_id="pay_c",
        status="captured",
        payout_idempotency_key="idem_saved",  # committed in step 1
        razorpayx_payout_id="",  # the tell: step 3 never ran
    )
