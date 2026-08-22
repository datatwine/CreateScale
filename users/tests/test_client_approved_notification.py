"""
Tests for the "approved for hiring" push notification trigger (issue #81,
remaining trigger #6).

client_approved has no dedicated view — it's flipped from Django admin's
Profile change form. ProfileAdmin.save_model() is the one place that
transition passes through, so that's where the notification hooks in.

send_push_notification is monkey-patched so these tests never touch Expo's
API.
"""

from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User

from users.admin import ProfileAdmin
from users.models import Profile


@pytest.fixture
def mock_send(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("users.admin.send_push_notification", mock)
    return mock


@pytest.fixture
def profile_admin():
    return ProfileAdmin(Profile, AdminSite())


@pytest.mark.django_db
class TestClientApprovedNotification:
    def test_notifies_on_transition_to_approved(self, profile_admin, mock_send):
        user = User.objects.create_user("aspiring.client", password="x")
        profile = Profile.objects.get(user=user)
        assert profile.client_approved is False

        profile.client_approved = True
        profile_admin.save_model(request=None, obj=profile, form=None, change=True)

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["user"] == user

    def test_does_not_notify_when_already_approved(self, profile_admin, mock_send):
        user = User.objects.create_user("existing.client", password="x")
        profile = Profile.objects.get(user=user)
        profile.client_approved = True
        profile.save()
        mock_send.reset_mock()

        # Admin re-saves the same (already-approved) profile — no transition.
        profile_admin.save_model(request=None, obj=profile, form=None, change=True)

        mock_send.assert_not_called()

    def test_does_not_notify_on_unrelated_field_change(self, profile_admin, mock_send):
        user = User.objects.create_user("browsing.user", password="x")
        profile = Profile.objects.get(user=user)

        profile.bio = "Just updating my bio"
        profile_admin.save_model(request=None, obj=profile, form=None, change=True)

        mock_send.assert_not_called()

    def test_does_not_notify_on_new_profile_creation(self, profile_admin, mock_send):
        # change=False means this is a brand-new object, not an admin edit
        # of an existing one — save_model's own transition check must not
        # explode looking up a profile that doesn't exist yet in the DB.
        user = User.objects.create_user("brand.new", password="x")
        profile = Profile.objects.get(user=user)
        Profile.objects.filter(pk=profile.pk).delete()
        profile.pk = None
        profile.user = user
        profile.client_approved = True

        profile_admin.save_model(request=None, obj=profile, form=None, change=False)

        mock_send.assert_not_called()
