from django.urls import path
from rest_framework.routers import DefaultRouter

from bookings.api.views import CreateHireRequestAPIView, EngagementViewSet
from .views import (
    TokenLoginAPIView,
    TokenLogoutAPIView,
    TokenMeAPIView,
    MeProfileAPIView,
    MyUploadsAPIView,
    MyUploadDeleteAPIView,
    GlobalFeedAPIView,
    ProfileDetailAPIView,
    ProfessionsAPIView,
    LiveEventsAPIView,
)

router = DefaultRouter()
# Router gives us dense, DRY bookings endpoints:
# /api/bookings/engagements/...
router.register(r"bookings/engagements", EngagementViewSet, basename="engagements")

urlpatterns = [
    # -------------------------
    # AUTH (Token)
    # -------------------------
    path("auth/token/", TokenLoginAPIView.as_view(), name="api-auth-token"),
    path("auth/logout/", TokenLogoutAPIView.as_view(), name="api-auth-logout"),
    path("auth/me/", TokenMeAPIView.as_view(), name="api-auth-me"),

    # -------------------------
    # USERS
    # -------------------------
    path("users/me/", MeProfileAPIView.as_view(), name="api-users-me"),
    path("users/me/uploads/", MyUploadsAPIView.as_view(), name="api-users-me-uploads"),
    path("users/me/uploads/<int:upload_id>/", MyUploadDeleteAPIView.as_view(), name="api-users-me-upload-delete"),

    # Global feed (other users) — mirrors users.views.global_feed
    path("users/feed/", GlobalFeedAPIView.as_view(), name="api-users-feed"),
    path("users/profiles/<int:user_id>/", ProfileDetailAPIView.as_view(), name="api-users-profile-detail"),
    path("users/professions/", ProfessionsAPIView.as_view(), name="api-users-professions"),

    # Live events — mirrors users.views.live_events
    path("users/live-events/", LiveEventsAPIView.as_view(), name="api-users-live-events"),

    # -------------------------
    # BOOKINGS (hire creation)
    # -------------------------
    # We keep hire creation as a simple single endpoint (not a router hack):
    path("bookings/hire/<int:performer_id>/", CreateHireRequestAPIView.as_view(), name="api-bookings-hire"),
]

urlpatterns += router.urls
