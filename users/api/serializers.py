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
        # bio included so mobile feed cards can show the blurb
        fields = ["user_id", "username", "profession", "profile_picture_url", "is_performer", "bio"]

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


# ---------------------------------------------------------------------------
# Signup serializer — mirrors users.forms.UserRegisterForm validation
# ---------------------------------------------------------------------------

import re
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError


class SignupSerializer(serializers.Serializer):
    """
    POST /api/auth/signup/
    Fields mirror UserRegisterForm: username, email, password1, password2.
    Optional: profession, location (written to the auto-created Profile).
    """
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)
    # Optional profile fields — set on the Profile after user creation
    profession = serializers.CharField(max_length=100, required=False, default="")
    location = serializers.CharField(max_length=100, required=False, default="")

    # -- Field-level validators --

    def validate_username(self, value):
        """Reject duplicate usernames (case-insensitive)."""
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def validate_email(self, value):
        """
        Same checks as UserRegisterForm.clean_email:
        1. Regex format check
        2. No 'spam' in the address
        3. Reject duplicate emails
        """
        regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(regex, value):
            raise serializers.ValidationError("Enter a valid email address.")
        if "spam" in value.lower():
            raise serializers.ValidationError("Spam emails are not allowed.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    # -- Object-level validators --

    def validate(self, attrs):
        """Password match + Django password strength validators."""
        if attrs["password1"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Passwords do not match."})

        # Run Django's AUTH_PASSWORD_VALIDATORS (length, common, numeric, etc.)
        try:
            validate_password(attrs["password1"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password1": list(exc.messages)})

        return attrs

    # -- Creation --

    def create(self, validated_data):
        """
        1. Create the User (password is hashed automatically).
        2. Profile is auto-created by the post_save signal in users.signals.
        3. Set optional profession / location on the Profile.
        """
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password1"],
        )

        # Profile already exists (thanks to the signal), so just update it
        profile = user.profile
        profile.profession = validated_data.get("profession", "")
        profile.location = validated_data.get("location", "")
        profile.save()

        return user
