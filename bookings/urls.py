# appointment/urls.py
from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    # 5) Hire flow entry from profile_detail
    path("hire/<int:performer_id>/", views.create_hire_request, name="create-hire"),

    # 16, 17) Minimal dashboards
    path("client/", views.client_engagement_list, name="client-engagements"),
    path("performer/", views.performer_engagement_list, name="performer-engagements"),

    # 9, 10, 11) Accept / decline / cancel
    path("engagement/<int:pk>/", views.engagement_detail, name="engagement-detail"),
]
