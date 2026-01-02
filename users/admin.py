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
    list_filter = (
        "is_performer",
        "is_potential_client",
        "client_approved",
        "performer_blacklisted",
        "client_blacklisted",
    )
    search_fields = ("user__username",)

admin.site.register(Upload)
