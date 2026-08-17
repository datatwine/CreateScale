from django.contrib import admin

# Register your models here.
from .models import Profile, Upload
from .notifications import send_push_notification


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "is_performer",
        "is_potential_client",
        "client_approved",
        "performer_blacklisted",
        "client_blacklisted",
    )
    list_select_related = ("user",)
    list_filter = (
        "is_performer",
        "is_potential_client",
        "client_approved",
        "performer_blacklisted",
        "client_blacklisted",
    )
    search_fields = ("user__username",)

    def save_model(self, request, obj, form, change):
        # client_approved has no dedicated view — this admin save is the
        # one place the False → True transition passes through, so it's
        # where the "you're approved" notification hooks in.
        was_approved = False
        if change:
            was_approved = (
                Profile.objects.filter(pk=obj.pk)
                .values_list("client_approved", flat=True)
                .first()
                or False
            )

        super().save_model(request, obj, form, change)

        if change and obj.client_approved and not was_approved:
            send_push_notification(
                user=obj.user,
                title="You're approved!",
                body="You can now hire performers",
                data={"screen": "GlobalFeed"},
            )


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "caption", "upload_date")
    list_select_related = ("profile__user",)
