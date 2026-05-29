
# Create your models here.
from django.db import models
from django.contrib.auth.models import User

from users.utils.image import process_image, is_fresh_upload

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profession = models.CharField(max_length=100, blank=True, db_index=True)
    location = models.CharField(max_length=100, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
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
        null=True, blank=True,
        help_text="Standard fee per engagement in rupees (shown on public profile).",
    )

    # Razorpay linked account (per-performer). Empty until KYC submitted.
    razorpay_account_id = models.CharField(max_length=64, blank=True, db_index=True)
    razorpay_kyc_status = models.CharField(
        max_length=16, blank=True,
        choices=[
            ("",         "Not started"),
            ("pending",  "Pending RBI review"),
            ("approved", "Approved — ready for payouts"),
            ("rejected", "Rejected — contact support"),
        ],
        default="",
    )

    # KYC details (Phase 1 plaintext; encryption is a Phase 2 enhancement).
    pan_number               = models.CharField(max_length=10, blank=True)
    bank_account_number      = models.CharField(max_length=20, blank=True)
    bank_ifsc                = models.CharField(max_length=11, blank=True)
    bank_account_holder_name = models.CharField(max_length=120, blank=True)
    phone_number             = models.CharField(
        max_length=10, blank=True,
        help_text="10-digit Indian mobile — required by Razorpay for linked account KYC.",
    )

    @property
    def can_receive_payments(self) -> bool:
        """True only when the performer's Razorpay linked account is approved."""
        return bool(self.razorpay_account_id) and self.razorpay_kyc_status == "approved"

    def __str__(self):
        return f'{self.user.username} Profile'

    def save(self, *args, **kwargs):
        # Compress only brand-new uploads. Re-saves (admin edits, etc.) skip this.
        if is_fresh_upload(self.profile_picture):
            self.profile_picture = process_image(self.profile_picture, "avatar")
        if is_fresh_upload(self.cover_photo):
            self.cover_photo = process_image(self.cover_photo, "cover")
        super().save(*args, **kwargs)

class Upload(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='uploads')
    image = models.ImageField(upload_to='profile_pics', blank=True, null=True)
    video = models.FileField(upload_to='profile_videos', blank=True, null=True)
    caption = models.TextField(blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.profile.user.username} Upload on {self.upload_date}'

    def save(self, *args, **kwargs):
        # Compress only brand-new uploads. The Celery video task re-saves .video
        # but never re-uploads .image, so this won't re-process compressed images.
        if is_fresh_upload(self.image):
            self.image = process_image(self.image, "gallery")
        super().save(*args, **kwargs)
    

class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

        # New Hiring-specific fields
    date = models.DateField(null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    hiring_status = models.CharField(max_length=10, choices=[
        ('none', 'None'),
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ], default='none')

    def __str__(self):
        return f'Message from {self.sender} to {self.recipient}'

