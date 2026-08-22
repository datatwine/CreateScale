# Register your models here.
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .models import Engagement, Payment, Review
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
        for payment in queryset.select_related("engagement", "engagement__performer"):
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


@admin.register(Review)  # registers this screen at /admin/…/review/
class ReviewAdmin(admin.ModelAdmin):
    # list_display = the columns in the table. Plain strings are model fields;
    # the others (author_link, event_summary, …) are METHODS defined below —
    # Django calls them once per row to compute that cell.
    list_display = (
        "id",
        "rating",
        "author_link",
        "subject_link",
        "direction",
        "event_summary",
        "short_comment",
        "created_at",
    )
    list_filter = ("direction", "rating", "created_at")  # right-hand filter sidebar
    search_fields = ("author__username", "subject__username", "comment")  # search box

    # PERFORMANCE (important — don't remove): the list renders author.username,
    # subject.username and engagement fields for every row. Without this, each
    # row would fire its own follow-up query for each of those objects — the
    # classic "N+1 queries" problem (1 list query + N per row). list_select_related
    # tells Django to JOIN them into the single list query up front. So a page of
    # 100 reviews stays a couple of queries, not a few hundred.
    list_select_related = ("engagement", "author", "subject")

    # Reviews are written by USERS; the admin only reads them to make decisions.
    # Marking every field read-only means an admin can open a review but not
    # rewrite someone's rating/comment.
    readonly_fields = (
        "engagement",
        "author",
        "subject",
        "direction",
        "rating",
        "comment",
        "created_at",
    )

    def has_add_permission(self, request):
        return False  # hides the "Add review" button — reviews are user-created only

    # --- computed columns --------------------------------------------------
    # @admin.display(description=…) sets the column header. Each method receives
    # one row object `obj` and returns that cell's contents.

    @admin.display(description="Reviewer")
    def author_link(self, obj):
        # reverse() builds the URL for the public profile page by NAME, so it
        # keeps working if the URL path ever changes. args=[obj.author_id] uses
        # the raw FK integer (no extra query). obj.author.username is already in
        # memory thanks to list_select_related above.
        # format_html safely builds the <a> tag (it escapes the values, so a
        # username can't inject HTML). target="_blank" opens in a new tab so the
        # admin never loses their place in the list.
        url = reverse("profile-detail", args=[obj.author_id])
        return format_html(
            '<a href="{}" target="_blank">{}</a>', url, obj.author.username
        )

    @admin.display(description="Reviewed")
    def subject_link(self, obj):
        url = reverse("profile-detail", args=[obj.subject_id])
        return format_html(
            '<a href="{}" target="_blank">{}</a>', url, obj.subject.username
        )

    @admin.display(description="Event")
    def event_summary(self, obj):
        # obj.engagement is pre-joined (list_select_related) → no extra query.
        e = obj.engagement
        return f"{e.occasion} @ {e.venue} on {e.date}"

    @admin.display(description="Comment")
    def short_comment(self, obj):
        # Truncate long comments so the table stays readable; full text is on
        # the review's own page.
        return (obj.comment[:60] + "…") if len(obj.comment) > 60 else obj.comment
