# Register your models here.
from django.contrib import admin

from .models import Engagement, Payment


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = (
        "id", "client", "performer", "date", "status",
        "payment_status", "fee", "disputed_at",
    )
    list_select_related = ("client", "performer")
    list_filter = ("status", "payment_status", "disputed_at")
    search_fields = (
        "client__username", "performer__username",
        "occasion", "venue",
    )
    readonly_fields = (
        "accepted_at", "paid_at", "released_at", "refunded_at",
        "created_at", "updated_at",
    )
    # Make dispute resolution discoverable — admin can set
    # dispute_resolved_at, then choose to refund or release manually.
    fieldsets = (
        ("Parties", {
            "fields": ("client", "performer"),
        }),
        ("Event", {
            "fields": ("date", "time", "venue", "occasion", "fee"),
        }),
        ("Status", {
            "fields": ("status", "payment_status"),
        }),
        ("Cancellation", {
            "fields": ("cancellation_reason", "cancelled_by"),
            "classes": ("collapse",),
        }),
        ("Dispute", {
            "fields": ("disputed_at", "dispute_reason", "dispute_resolved_at"),
        }),
        ("Timestamps", {
            "fields": (
                "accepted_at", "paid_at", "released_at", "refunded_at",
                "created_at", "updated_at",
            ),
            "classes": ("collapse",),
        }),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "engagement", "amount", "status",
        "razorpay_payment_id", "created_at",
    )
    list_select_related = ("engagement",)
    list_filter = ("status",)
    search_fields = (
        "razorpay_order_id", "razorpay_payment_id", "razorpay_refund_id",
    )
    readonly_fields = (
        "razorpay_order_id", "razorpay_payment_id",
        "razorpay_transfer_id", "razorpay_refund_id",
        "created_at", "updated_at",
    )
