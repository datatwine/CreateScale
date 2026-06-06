from django.contrib import admin

# Register your models here.
from .models import Profile, Upload

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


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("id", "profile", "caption", "upload_date")
    list_select_related = ("profile__user",)
