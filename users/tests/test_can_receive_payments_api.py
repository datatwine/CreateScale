"""
TDD — written BEFORE implementation (issue #69, Part 1b).

can_receive_payments must be exposed on:
  GET /api/users/me/                        (MeProfileSerializer)
  GET /api/users/profiles/<user_id>/         (PublicProfileDetailSerializer)

so Expo can show/hide the "Pay" button without replicating the
mode-dependent (Route vs Payouts) gate logic client-side. The property
itself is already fully tested in test_can_receive_payments.py — these
tests only confirm it's exposed on the serializers, read-only.
"""

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient


def _make_user(username):
    u = User.objects.create_user(username, password="x")
    return u, u.profile


@pytest.mark.django_db
class TestCanReceivePaymentsOnMeProfile:
    def setup_method(self):
        self.api = APIClient()

    def test_true_when_payable(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_user("performer_payable")
        profile.is_performer = True
        profile.bank_account_holder_name = "Performer One"
        profile.bank_account_number = "1234567890"
        profile.bank_ifsc = "HDFC0001234"
        profile.save()

        self.api.force_authenticate(user=user)
        r = self.api.get("/api/users/me/")

        assert r.status_code == 200
        assert r.data["can_receive_payments"] is True

    def test_false_when_not_payable(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_user("performer_not_payable")
        profile.is_performer = True
        profile.save()

        self.api.force_authenticate(user=user)
        r = self.api.get("/api/users/me/")

        assert r.status_code == 200
        assert r.data["can_receive_payments"] is False

    def test_field_is_read_only(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        user, profile = _make_user("performer_readonly")
        profile.is_performer = True
        profile.save()

        self.api.force_authenticate(user=user)
        r = self.api.patch(
            "/api/users/me/", {"can_receive_payments": True}, format="json"
        )

        assert r.status_code == 200
        profile.refresh_from_db()
        # Attempting to write it directly must not flip an unpayable profile.
        assert r.data["can_receive_payments"] is False


@pytest.mark.django_db
class TestCanReceivePaymentsOnPublicProfileDetail:
    def setup_method(self):
        self.api = APIClient()
        # ProfileDetailAPIView caches by user_id, and Redis persists across
        # test runs (unlike the DB transaction rollback) — a stale entry
        # from a prior run can collide if IDs repeat.
        cache.clear()

    def test_true_when_target_performer_is_payable(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        viewer, _ = _make_user("client_viewer")
        target, target_profile = _make_user("performer_target")
        target_profile.is_performer = True
        target_profile.bank_account_holder_name = "Performer Target"
        target_profile.bank_account_number = "1234567890"
        target_profile.bank_ifsc = "HDFC0001234"
        target_profile.save()

        self.api.force_authenticate(user=viewer)
        r = self.api.get(f"/api/users/profiles/{target.id}/")

        assert r.status_code == 200
        assert r.data["can_receive_payments"] is True

    def test_false_when_target_performer_is_not_payable(self, settings):
        settings.RAZORPAY_ROUTE_ENABLED = False
        viewer, _ = _make_user("client_viewer2")
        target, target_profile = _make_user("performer_target2")
        target_profile.is_performer = True
        target_profile.save()

        self.api.force_authenticate(user=viewer)
        r = self.api.get(f"/api/users/profiles/{target.id}/")

        assert r.status_code == 200
        assert r.data["can_receive_payments"] is False
