# bookings/urls.py
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

    # Payment flow (Phase 4)
    # /pay/    → JS asks backend to create a Razorpay Order
    # /verify/ → JS forwards Razorpay's signed callback for HMAC validation
    # /dispute/→ Client raises an issue within 24h post-event
    path("engagement/<int:pk>/pay/",     views.create_payment_order, name="create-payment-order"),
    path("engagement/<int:pk>/verify/",  views.verify_payment,       name="verify-payment"),
    path("engagement/<int:pk>/dispute/", views.raise_dispute,        name="raise-dispute"),

    # Payment history dashboards
    path("performer/payouts/",  views.performer_payouts, name="performer-payouts"),
    path("client/payments/",    views.client_payments,   name="client-payments"),

    # Razorpay webhook — backup channel; verifies its own HMAC; CSRF exempt
    path("webhook/razorpay/",   views.razorpay_webhook,  name="razorpay-webhook"),
]
