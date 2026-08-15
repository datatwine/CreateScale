from django.contrib import admin
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils.html import format_html

from .models import Upload, Performer, Client


class _RoleConsole(admin.ModelAdmin):
    """
    Shared columns/logic for the Performer and Client screens. The leading
    underscore is a convention meaning "internal base class, not registered on
    its own" — only its two subclasses below get @admin.register.
    """
    search_fields = ("user__username",)
    role_filter = {}   # subclasses set this, e.g. {"is_performer": True}

    def get_queryset(self, request):
        # This defines the rows + columns of DATA the list page runs on. We
        # start from the default queryset and layer three things on:
        qs = super().get_queryset(request).select_related("user")
        # (1) select_related("user") → JOIN the related User row into the same
        #     query, so profile_link reading obj.user.username costs no extra
        #     per-row query (avoids N+1, same idea as list_select_related).

        # (2) filter to just this role's rows. **self.role_filter unpacks the
        #     dict the subclass set, e.g. filter(is_performer=True). This is why
        #     the Performers screen shows performers and Clients shows clients,
        #     from one shared table.
        qs = qs.filter(**self.role_filter)

        # (3) Compute the average score AND the number of reviews each person
        #     RECEIVED, IN THE DATABASE, as two extra columns (_avg, _cnt).
        #     `user__reviews_received` walks User → the Review.subject reverse
        #     relation. Doing this with annotate() means one GROUP BY query for
        #     the whole page — NOT a per-row "count this person's reviews" loop.
        #     (Both aggregates traverse the *same* relation, so they share one
        #     JOIN and don't inflate each other's numbers.)
        return qs.annotate(
            _avg=Avg("user__reviews_received__rating"),
            _cnt=Count("user__reviews_received"),
        )

    @admin.display(description="User (click → profile)")
    def profile_link(self, obj):
        # Clickable username → the person's public profile. obj.user_id is the
        # raw FK integer (no query); obj.user.username is already joined in.
        url = reverse("profile-detail", args=[obj.user_id])
        return format_html('<a href="{}" target="_blank">{}</a>', url, obj.user.username)

    # ordering="_avg" makes this column SORTABLE by clicking its header — Django
    # sorts on the annotated DB value, so "worst-rated first" is one click.
    @admin.display(description="Avg score", ordering="_avg")
    def avg_rating(self, obj):
        # _avg is None when the person has no reviews yet → show a dash instead
        # of crashing on the format. Otherwise one decimal, e.g. "7.3/10".
        return f"{obj._avg:.1f}/10" if obj._avg is not None else "—"

    @admin.display(description="# reviews", ordering="_cnt")
    def review_count(self, obj):
        return obj._cnt


@admin.register(Performer)
class PerformerAdmin(_RoleConsole):
    role_filter = {"is_performer": True}     # this screen = performers only
    list_display = (
        "profile_link", "avg_rating", "review_count",
        "performer_blacklisted", "performer_fee",
    )
    list_filter = ("performer_blacklisted",)
    # `actions` = the dropdown above the checkboxes. Tick rows → pick an action
    # → it runs on all of them at once. THIS is "bulk blacklist".
    actions = ["blacklist_performers", "unblacklist_performers"]

    # An @admin.action receives the admin, the request, and `queryset` = exactly
    # the rows the admin ticked. queryset.update(...) issues ONE bulk SQL UPDATE
    # for all of them (not a Python loop) and returns how many rows changed.
    # (Same pattern as the existing PaymentAdmin.retry_failed_payout.)
    @admin.action(description="Blacklist selected performers")
    def blacklist_performers(self, request, queryset):
        n = queryset.update(performer_blacklisted=True)
        # message_user shows the green confirmation banner at the top.
        self.message_user(request, f"{n} performer(s) blacklisted.")

    @admin.action(description="Remove performer blacklist")
    def unblacklist_performers(self, request, queryset):
        n = queryset.update(performer_blacklisted=False)
        self.message_user(request, f"{n} performer(s) un-blacklisted.")


@admin.register(Client)
class ClientAdmin(_RoleConsole):
    role_filter = {"is_potential_client": True}   # this screen = clients only
    list_display = (
        "profile_link", "client_approved", "client_blacklisted",
        "avg_rating", "review_count",
    )
    list_filter = ("client_approved", "client_blacklisted")
    # Clients get two more actions than performers: approve/revoke hire access.
    actions = [
        "approve_clients", "unapprove_clients",
        "blacklist_clients", "unblacklist_clients",
    ]

    # Bulk APPROVE — flips client_approved on every ticked row in one UPDATE.
    @admin.action(description="Approve selected clients to hire")
    def approve_clients(self, request, queryset):
        n = queryset.update(client_approved=True)
        self.message_user(request, f"{n} client(s) approved to hire.")

    @admin.action(description="Revoke hire approval")
    def unapprove_clients(self, request, queryset):
        n = queryset.update(client_approved=False)
        self.message_user(request, f"{n} client approval(s) revoked.")

    @admin.action(description="Blacklist selected clients")
    def blacklist_clients(self, request, queryset):
        n = queryset.update(client_blacklisted=True)
        self.message_user(request, f"{n} client(s) blacklisted.")

    @admin.action(description="Remove client blacklist")
    def unblacklist_clients(self, request, queryset):
        n = queryset.update(client_blacklisted=False)
        self.message_user(request, f"{n} client(s) un-blacklisted.")


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "caption", "upload_date")
    list_select_related = ("profile__user",)
