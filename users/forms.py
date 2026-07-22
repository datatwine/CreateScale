from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Upload, Profile, Message
import re
from django.core.exceptions import ValidationError


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()
    profession = forms.CharField(max_length=100)
    location = forms.CharField(max_length=100)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password1",
            "password2",
            "profession",
            "location",
        ]

    def clean_email(self):
        email = self.cleaned_data.get("email")
        # Define a regex for valid email (example: no spam keywords)
        regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(regex, email):
            raise ValidationError("Enter a valid email address.")
        if "spam" in email:
            raise ValidationError("Spam emails are not allowed.")
        return email


class UploadForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ["image", "video", "caption"]

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("image") and not cleaned_data.get("video"):
            raise ValidationError("Upload requires at least one file (image or video).")
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            if image.content_type not in ["image/jpeg", "image/png", "image/gif"]:
                raise ValidationError("Only JPEG, PNG, and GIF images are supported.")
            if image.size > 5 * 1024 * 1024:  # 5 MB limit
                raise ValidationError("Image size must be under 5 MB.")
        return image

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if video:
            if video.content_type != "video/mp4":
                raise ValidationError("Only MP4 videos are supported.")
            # Aligned with Nginx client_max_body_size (120 MB). Bigger files
            # are rejected by Nginx before reaching Django; this limit gives
            # a nicer Django-side error message for anything that gets through.
            if video.size > 120 * 1024 * 1024:  # 120 MB limit
                raise ValidationError(
                    "Video size must be under 120 MB. Keep clips to 60 seconds."
                )
        return video


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "profession",
            "location",
            "profile_picture",
            "cover_photo",
            "bio",
            "is_performer",
            "is_potential_client",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 3}),
        }


class ProfessionFilterForm(forms.Form):
    professions = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Filter by Profession",
    )

    def __init__(self, *args, **kwargs):
        super(ProfessionFilterForm, self).__init__(*args, **kwargs)
        # Dynamically generate profession choices from all profiles
        all_professions = (
            Profile.objects.values_list("profession", flat=True)
            .distinct()
            .order_by("profession")
        )
        self.fields["professions"].choices = [
            (prof, prof) for prof in all_professions if prof
        ]


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Write your message here..."}
            )
        }


# ---------------------------------------------------------------------------
# Razorpay KYC + payment details for performers
# ---------------------------------------------------------------------------
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile: starts 6/7/8/9, 10 digits


class PaymentDetailsForm(forms.ModelForm):
    """
    Performer's KYC + bank details used to spin up a Razorpay linked
    account. Razorpay does the deep validation (PAN match against Income
    Tax records, IFSC against NPCI, account number via penny-test) — our
    form just checks formats so we don't ping their API with junk.
    """

    class Meta:
        model = Profile
        fields = [
            "performer_fee",
            "phone_number",
            "pan_number",
            "bank_account_number",
            "bank_ifsc",
            "bank_account_holder_name",
        ]
        widgets = {
            "performer_fee": forms.NumberInput(
                attrs={"min": 500, "max": 500000, "placeholder": "e.g. 3000"}
            ),
            "phone_number": forms.TextInput(
                attrs={
                    "placeholder": "10-digit mobile (e.g. 9876543210)",
                    "maxlength": 10,
                }
            ),
            "pan_number": forms.TextInput(
                attrs={"placeholder": "ABCDE1234F", "maxlength": 10}
            ),
            "bank_account_number": forms.TextInput(attrs={"placeholder": "1234567890"}),
            "bank_ifsc": forms.TextInput(attrs={"placeholder": "HDFC0001234"}),
            "bank_account_holder_name": forms.TextInput(
                attrs={"placeholder": "As per bank records"}
            ),
        }

    def clean_performer_fee(self):
        fee = self.cleaned_data.get("performer_fee")
        if fee is not None and (fee < 500 or fee > 500000):
            raise ValidationError("Fee must be between ₹500 and ₹5,00,000.")
        return fee

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        if phone and not PHONE_RE.match(phone):
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        return phone

    def clean_pan_number(self):
        pan = (self.cleaned_data.get("pan_number") or "").upper().strip()
        if pan and not PAN_RE.match(pan):
            raise ValidationError("Invalid PAN format. Expected: ABCDE1234F")
        return pan

    def clean_bank_ifsc(self):
        ifsc = (self.cleaned_data.get("bank_ifsc") or "").upper().strip()
        if ifsc and not IFSC_RE.match(ifsc):
            raise ValidationError("Invalid IFSC code format.")
        return ifsc
