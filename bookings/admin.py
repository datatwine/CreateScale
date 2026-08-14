# Register your models here.
from django.contrib import admin, messages

from .models import Engagement, Payment
from .services.payments import PaymentService


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "performer",
        "date",
        "status",
        "payment_status",
        "fee",
        "disputed_at",
    )
    list_select_related = ("client", "performer")
    list_filter = ("status", "payment_status", "disputed_at")
    search_fields = (
        "client__username",
        "performer__username",
        "occasion",
        "venue",
    )
    readonly_fields = (
        "accepted_at",
        "paid_at",
        "released_at",
        "refunded_at",
        "payout_initiated_at",
        "created_at",
        "updated_at",
    )
    # Make dispute resolution discoverable — admin can set
    # dispute_resolved_at, then choose to refund or release manually.
    fieldsets = (
        (
            "Parties",
            {
                "fields": ("client", "performer"),
            },
        ),
        (
            "Event",
            {
                "fields": ("date", "time", "venue", "occasion", "fee"),
            },
        ),
        (
            "Status",
            {
                "fields": ("status", "payment_status"),
            },
        ),
        (
            "Cancellation",
            {
                "fields": ("cancellation_reason", "cancelled_by"),
                "classes": ("collapse",),
            },
        ),
        (
            "Dispute",
            {
                "fields": ("disputed_at", "dispute_reason", "dispute_resolved_at"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "accepted_at",
                    "paid_at",
                    "released_at",
                    "refunded_at",
                    "payout_initiated_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "engagement",
        "amount",
        "performer_share",
        "status",
        "razorpay_payment_id",
        "razorpayx_payout_id",
        "payout_reference",
        "created_at",
    )
    list_select_related = ("engagement",)
    list_filter = ("status",)
    search_fields = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "razorpay_refund_id",
        "razorpayx_payout_id",
        "payout_reference",
    )
    readonly_fields = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "razorpay_transfer_id",
        "razorpay_refund_id",
        "razorpayx_payout_id",
        "payout_idempotency_key",
        "created_at",
        "updated_at",
    )
    actions = ["retry_failed_payout"]

    @admin.action(description="Retry failed payout (refresh bank details)")
    def retry_failed_payout(self, request, queryset):
        """
        Safety net for payout_failed / payout_reversed rows (wrong bank detail
        fixed, a transient bank/NPCI outage, or a post-settlement reversal).

        Clears the cached RazorpayX fund account first so any corrected bank
        details are picked up (H3) — ensure_payout_destination rebuilds and
        re-validates it — then re-fires via the normal guarded, idempotent
        path. Per-row messaging so a bad row doesn't hide the others.
        """
        for payment in queryset.select_related(
            "engagement", "engagement__performer"
        ):
            if payment.status not in ("payout_failed", "payout_reversed"):
                self.message_user(
                    request,
                    f"Skipped {payment} (status {payment.status}).",
                    messages.WARNING,
                )
                continue
            try:
                profile = payment.engagement.performer.profile
                profile.razorpayx_fund_account_id = ""
                profile.save(update_fields=["razorpayx_fund_account_id"])
                PaymentService.initiate_payout(payment.engagement)
                self.message_user(request, f"Retried {payment}.", messages.SUCCESS)
            except Exception as e:  # noqa: BLE001 — surface any failure to admin
                self.message_user(
                    request, f"Retry failed for {payment}: {e}", messages.ERROR
                )
