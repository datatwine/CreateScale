"""
TDD — written BEFORE implementation (issue #22, pagination added per PR #37
review — see PerformerPayoutsAPIView / ClientPaymentsAPIView).

Tests for:
  GET /api/bookings/payouts/performer/
  GET /api/bookings/payments/client/

These mirror the web views performer_payouts and client_payments in
bookings/views.py. Both endpoints use _LenientPaginatorMixin (same
pattern as GlobalFeedAPIView / LiveEventsAPIView) so response shape is
{count, num_pages, page, has_next, has_previous, results}.
"""
from datetime import date, time, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Engagement
from users.models import Profile


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_user(username, *, is_performer=False, is_client=False):
    u = User.objects.create_user(username, password="x")
    Profile.objects.update_or_create(
        user=u,
        defaults={
            "is_performer": is_performer,
            "is_potential_client": is_client,
            "client_approved": is_client,
        },
    )
    return u


def _make_engagement(client_u, performer_u, payment_status):
    return Engagement.objects.create(
        client=client_u,
        performer=performer_u,
        date=date.today() + timedelta(days=10),
        time=time(19, 0),
        venue="Venue",
        occasion="Occasion",
        fee=2000,
        payment_status=payment_status,
        paid_at=timezone.now() if payment_status != Engagement.PAYMENT_UNPAID else None,
    )


# ---------------------------------------------------------------------------
# Performer payouts — GET /api/bookings/payouts/performer/
# ---------------------------------------------------------------------------

PERFORMER_PAYOUTS_URL = "/api/bookings/payouts/performer/"


@pytest.mark.django_db
class TestPerformerPayoutsAPI:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self):
        r = self.api.get(PERFORMER_PAYOUTS_URL)
        assert r.status_code == 401

    def test_returns_only_own_engagements(self):
        performer = _make_user("perf_a", is_performer=True)
        other_performer = _make_user("perf_b", is_performer=True)
        client_u = _make_user("cli_a", is_client=True)

        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)
        _make_engagement(client_u, other_performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL)

        assert r.status_code == 200
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["performer"]["username"] == "perf_a"

    def test_filters_paid_released_refunded_only(self):
        performer = _make_user("perf_c", is_performer=True)
        client_u = _make_user("cli_b", is_client=True)

        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)
        _make_engagement(client_u, performer, Engagement.PAYMENT_RELEASED)
        _make_engagement(client_u, performer, Engagement.PAYMENT_REFUNDED)
        _make_engagement(client_u, performer, Engagement.PAYMENT_UNPAID)  # must be excluded

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL)

        assert r.status_code == 200
        assert len(r.data["results"]) == 3
        assert r.data["count"] == 3

    def test_response_shape_includes_payment_fields(self):
        performer = _make_user("perf_d", is_performer=True)
        client_u = _make_user("cli_c", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL)

        item = r.data["results"][0]
        assert "id" in item
        assert "fee" in item
        assert "payment_status" in item
        assert "paid_at" in item
        assert "client" in item
        assert "date" in item
        assert "venue" in item
        assert "occasion" in item

    def test_excludes_client_only_engagements(self):
        """As a client, GET performer payouts must return 0 of their own client engagements."""
        performer = _make_user("perf_e", is_performer=True)
        client_u = _make_user("cli_d", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_u)
        r = self.api.get(PERFORMER_PAYOUTS_URL)
        assert r.status_code == 200
        assert len(r.data["results"]) == 0

    def test_paginates_at_page_size(self):
        performer = _make_user("perf_pag", is_performer=True)
        client_u = _make_user("cli_pag", is_client=True)
        for _ in range(25):
            _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL)

        assert r.status_code == 200
        assert r.data["count"] == 25
        assert r.data["num_pages"] == 2
        assert r.data["page"] == 1
        assert r.data["has_next"] is True
        assert r.data["has_previous"] is False
        assert len(r.data["results"]) == 20

    def test_second_page_returns_remainder(self):
        performer = _make_user("perf_pag2", is_performer=True)
        client_u = _make_user("cli_pag2", is_client=True)
        for _ in range(25):
            _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL, {"page": 2})

        assert r.status_code == 200
        assert r.data["page"] == 2
        assert r.data["has_next"] is False
        assert r.data["has_previous"] is True
        assert len(r.data["results"]) == 5

    def test_invalid_page_does_not_404(self):
        """Mirrors users.views.global_feed's Paginator.get_page() lenience."""
        performer = _make_user("perf_pag3", is_performer=True)
        client_u = _make_user("cli_pag3", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(PERFORMER_PAYOUTS_URL, {"page": "not-a-number"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Client payments — GET /api/bookings/payments/client/
# ---------------------------------------------------------------------------

CLIENT_PAYMENTS_URL = "/api/bookings/payments/client/"


@pytest.mark.django_db
class TestClientPaymentsAPI:

    def setup_method(self):
        self.api = APIClient()

    def test_requires_authentication(self):
        r = self.api.get(CLIENT_PAYMENTS_URL)
        assert r.status_code == 401

    def test_returns_only_own_engagements(self):
        performer = _make_user("perf_f", is_performer=True)
        client_a = _make_user("cli_e", is_client=True)
        client_b = _make_user("cli_f", is_client=True)

        _make_engagement(client_a, performer, Engagement.PAYMENT_PAID)
        _make_engagement(client_b, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_a)
        r = self.api.get(CLIENT_PAYMENTS_URL)

        assert r.status_code == 200
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["client"]["username"] == "cli_e"

    def test_filters_paid_released_refunded_only(self):
        performer = _make_user("perf_g", is_performer=True)
        client_u = _make_user("cli_g", is_client=True)

        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)
        _make_engagement(client_u, performer, Engagement.PAYMENT_RELEASED)
        _make_engagement(client_u, performer, Engagement.PAYMENT_REFUNDED)
        _make_engagement(client_u, performer, Engagement.PAYMENT_UNPAID)  # excluded

        self.api.force_authenticate(user=client_u)
        r = self.api.get(CLIENT_PAYMENTS_URL)

        assert r.status_code == 200
        assert len(r.data["results"]) == 3
        assert r.data["count"] == 3

    def test_response_shape_includes_payment_fields(self):
        performer = _make_user("perf_h", is_performer=True)
        client_u = _make_user("cli_h", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_u)
        r = self.api.get(CLIENT_PAYMENTS_URL)

        item = r.data["results"][0]
        assert "id" in item
        assert "fee" in item
        assert "payment_status" in item
        assert "paid_at" in item
        assert "performer" in item
        assert "date" in item
        assert "venue" in item
        assert "occasion" in item

    def test_excludes_performer_only_engagements(self):
        """A performer with no client engagements gets an empty list."""
        performer = _make_user("perf_i", is_performer=True)
        client_u = _make_user("cli_i", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=performer)
        r = self.api.get(CLIENT_PAYMENTS_URL)
        assert r.status_code == 200
        assert len(r.data["results"]) == 0

    def test_paginates_at_page_size(self):
        performer = _make_user("perf_pag4", is_performer=True)
        client_u = _make_user("cli_pag4", is_client=True)
        for _ in range(25):
            _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_u)
        r = self.api.get(CLIENT_PAYMENTS_URL)

        assert r.status_code == 200
        assert r.data["count"] == 25
        assert r.data["num_pages"] == 2
        assert r.data["page"] == 1
        assert r.data["has_next"] is True
        assert r.data["has_previous"] is False
        assert len(r.data["results"]) == 20

    def test_second_page_returns_remainder(self):
        performer = _make_user("perf_pag5", is_performer=True)
        client_u = _make_user("cli_pag5", is_client=True)
        for _ in range(25):
            _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_u)
        r = self.api.get(CLIENT_PAYMENTS_URL, {"page": 2})

        assert r.status_code == 200
        assert r.data["page"] == 2
        assert r.data["has_next"] is False
        assert r.data["has_previous"] is True
        assert len(r.data["results"]) == 5

    def test_invalid_page_does_not_404(self):
        performer = _make_user("perf_pag6", is_performer=True)
        client_u = _make_user("cli_pag6", is_client=True)
        _make_engagement(client_u, performer, Engagement.PAYMENT_PAID)

        self.api.force_authenticate(user=client_u)
        r = self.api.get(CLIENT_PAYMENTS_URL, {"page": "not-a-number"})
        assert r.status_code == 200
