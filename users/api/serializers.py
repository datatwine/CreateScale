from rest_framework import serializers
from users.models import Profile, Upload


def _abs_url(request, file_field) -> str:
    """
    Converts storage URLs into absolute URLs when possible.
    This works for local MEDIA_URL and also for S3 (S3 URLs are already absolute).
    """
    if not file_field:
        return ""
    try:
        url = file_field.url
    except Exception:
        return ""
    return request.build_absolute_uri(url) if request else url


class UploadSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = ["id", "caption", "upload_date", "image", "video", "image_url", "video_url"]
        extra_kwargs = {
            "image": {"write_only": True, "required": False},
            "video": {"write_only": True, "required": False},
        }

    def get_image_url(self, obj):
        return _abs_url(self.context.get("request"), obj.image)

    def get_video_url(self, obj):
        return _abs_url(self.context.get("request"), obj.video)

    def validate(self, attrs):
        # Mirror your UploadForm intent: require at least one media field.
        if not attrs.get("image") and not attrs.get("video"):
            raise serializers.ValidationError("Upload requires an image or a video.")
        return attrs


class GlobalFeedProfileSerializer(serializers.ModelSerializer):
    """
    GLOBAL FEED serializer (other users). Mirrors users.views.global_feed:
    minimal fields for listing other profiles.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["user_id", "username", "profession", "profile_picture_url", "is_performer"]

    def get_profile_picture_url(self, obj):
        return _abs_url(self.context.get("request"), obj.profile_picture)


class MeProfileSerializer(serializers.ModelSerializer):
    """
    MY PROFILE serializer (logged-in user). Mirrors fields your ProfileUpdateForm edits
    + returns admin flags read-only (client_approved / blacklists).
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "user_id",
            "username",
            "profession",
            "location",
            "bio",
            "profile_picture",       # write (multipart)
            "profile_picture_url",   # read
            "is_performer",
            "is_potential_client",
            "client_approved",
            "performer_blacklisted",
            "client_blacklisted",
        ]
        extra_kwargs = {
            "profile_picture": {"write_only": True, "required": False},
            "client_approved": {"read_only": True},
            "performer_blacklisted": {"read_only": True},
            "client_blacklisted": {"read_only": True},
        }

    def get_profile_picture_url(self, obj):
        return _abs_url(self.context.get("request"), obj.profile_picture)


class PublicProfileDetailSerializer(serializers.ModelSerializer):
    """
    OTHER USER profile detail (users.views.profile_detail equivalent):
    includes their uploads newest-first.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    profile_picture_url = serializers.SerializerMethodField()
    uploads = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "user_id",
            "username",
            "profession",
            "location",
            "bio",
            "profile_picture_url",
            "is_performer",
            "uploads",
        ]

    def get_profile_picture_url(self, obj):
        return _abs_url(self.context.get("request"), obj.profile_picture)

    def get_uploads(self, obj):
        request = self.context.get("request")
        qs = Upload.objects.filter(profile=obj).order_by("-upload_date")
        return UploadSerializer(qs, many=True, context={"request": request}).data
