# Create your models here.
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User

from users.utils.image import process_image, is_fresh_upload

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profession = models.CharField(max_length=100, blank=True, db_index=True)
    location = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", blank=True, null=True
    )
    cover_photo = models.ImageField(upload_to="cover_photos/", blank=True, null=True)
    bio = models.CharField(max_length=140, blank=True)

    # --- Hiring system toggles / flags ---

    # 2) Performer toggle – user decides if they are a performer
    is_performer = models.BooleanField(
        default=False,
        help_text="Tick if you are available to be hired as a performer.",
    )

    # 3 & 4) Client toggle + admin approval
    # User toggles this on profile; admin turns on client_approved in Django admin.
    is_potential_client = models.BooleanField(
        default=False,
        help_text="Tick if you want to hire performers.",
    )
    client_approved = models.BooleanField(
        default=False,
        help_text="Set by admin. Only approved clients may send hire requests.",
    )

    # 15) Blacklists
    performer_blacklisted = models.BooleanField(
        default=False,
        help_text="If true, this user cannot be hired as a performer.",
    )
    client_blacklisted = models.BooleanField(
        default=False,
        help_text="If true, this user cannot hire performers.",
    )

    # --- Payment setup (performers only; clients don't need KYC) ---
    # Standard fee per engagement, shown on profile + snapshotted into
    # Engagement.fee at hire time so opens bookings are immutable.
    performer_fee = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Standard fee per engagement in rupees (shown on public profile).",
    )

    # Razorpay linked account (per-performer). Empty until KYC submitted.
    razorpay_account_id = models.CharField(max_length=64, blank=True, db_index=True)
    razorpay_kyc_status = models.CharField(
        max_length=16,
        blank=True,
        choices=[
            ("", "Not started"),
            ("pending", "Pending RBI review"),
            ("approved", "Approved — ready for payouts"),
            ("rejected", "Rejected — contact support"),
        ],
        default="",
    )

    # KYC details (Phase 1 plaintext; encryption is a Phase 2 enhancement).
    pan_number = models.CharField(max_length=10, blank=True)
    bank_account_number = models.CharField(max_length=20, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    bank_account_holder_name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(
        max_length=10,
        blank=True,
        help_text="10-digit Indian mobile — required by Razorpay for linked account KYC.",
    )

    # RazorpayX Payouts destination (payouts mode). Created once from the
    # performer's bank details and cached here so each payout is a single API
    # call. Empty in Route mode (Route uses razorpay_account_id instead).
    razorpayx_contact_id = models.CharField(max_length=64, blank=True, db_index=True)
    razorpayx_fund_account_id = models.CharField(
        max_length=64, blank=True, db_index=True
    )

    @property
    def can_receive_payments(self) -> bool:
        """
        Gate checked by PaymentService.create_order() before charging a client.

        Route ON  — the performer's Razorpay linked account must exist and have
                    passed RBI KYC review (Razorpay holds the escrow, so Razorpay
                    decides who's payable).
        Route OFF — WE hold the money and pay out from the platform account, so
                    "payable" just means complete bank details are on file. No
                    linked account, no KYC-review wait. The RazorpayX contact /
                    fund-account are created lazily at (or before) payout time.
        """
        if settings.RAZORPAY_ROUTE_ENABLED:
            return (
                bool(self.razorpay_account_id)
                and self.razorpay_kyc_status == "approved"
            )
        return bool(
            self.bank_account_holder_name
            and self.bank_account_number
            and self.bank_ifsc
        )

    def __str__(self):
        return f"{self.user.username} Profile"

    def clean(self):
        if self.pan_number:
            pan = self.pan_number.upper().strip()
            if not PAN_RE.match(pan):
                raise ValidationError(
                    {"pan_number": "Invalid PAN format. Expected: ABCDE1234F"}
                )
            self.pan_number = pan
        if self.bank_ifsc:
            ifsc = self.bank_ifsc.upper().strip()
            if not IFSC_RE.match(ifsc):
                raise ValidationError({"bank_ifsc": "Invalid IFSC code format."})
            self.bank_ifsc = ifsc
        if self.phone_number:
            phone = self.phone_number.strip()
            if not PHONE_RE.match(phone):
                raise ValidationError(
                    {"phone_number": "Enter a valid 10-digit Indian mobile number."}
                )
            self.phone_number = phone
        if self.performer_fee is not None and (
            self.performer_fee < 500 or self.performer_fee > 500000
        ):
            raise ValidationError(
                {"performer_fee": "Fee must be between ₹500 and ₹5,00,000."}
            )

    def save(self, *args, **kwargs):
        # Compress only brand-new uploads. Re-saves (admin edits, etc.) skip this.
        if is_fresh_upload(self.profile_picture):
            self.profile_picture = process_image(self.profile_picture, "avatar")
        if is_fresh_upload(self.cover_photo):
            self.cover_photo = process_image(self.cover_photo, "cover")
        super().save(*args, **kwargs)


class Upload(models.Model):
    MAX_UPLOADS_PER_USER = 9

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="uploads"
    )
    image = models.ImageField(upload_to="profile_pics", blank=True, null=True)
    video = models.FileField(upload_to="profile_videos", blank=True, null=True)
    caption = models.TextField(blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Covers filter(profile=X).order_by("-upload_date") in one B-tree scan
            models.Index(fields=["profile", "-upload_date"]),
        ]

    def __str__(self):
        return f"{self.profile.user.username} Upload on {self.upload_date}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            count = Upload.objects.filter(profile=self.profile).count()
            if count >= self.MAX_UPLOADS_PER_USER:
                raise ValidationError(
                    f"Maximum {self.MAX_UPLOADS_PER_USER} uploads allowed."
                )
        if is_fresh_upload(self.image):
            self.image = process_image(self.image, "gallery")
        super().save(*args, **kwargs)


class Message(models.Model):
    sender = models.ForeignKey(
        User, related_name="sent_messages", on_delete=models.CASCADE
    )
    recipient = models.ForeignKey(
        User, related_name="received_messages", on_delete=models.CASCADE
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    # New Hiring-specific fields
    date = models.DateField(null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    hiring_status = models.CharField(
        max_length=10,
        choices=[
            ("none", "None"),
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
        ],
        default="none",
    )

    def __str__(self):
        return f"Message from {self.sender} to {self.recipient}"
