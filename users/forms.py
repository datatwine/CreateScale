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
        fields = ['username', 'email', 'password1', 'password2', 'profession', 'location']

    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Define a regex for valid email (example: no spam keywords)
        regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(regex, email):
            raise ValidationError("Enter a valid email address.")
        if "spam" in email:
            raise ValidationError("Spam emails are not allowed.")
        return email


from django.core.exceptions import ValidationError

class UploadForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ['image', 'video', 'caption']

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.content_type not in ['image/jpeg', 'image/png', 'image/gif']:
                raise ValidationError("Only JPEG, PNG, and GIF images are supported.")
            if image.size > 5 * 1024 * 1024:  # 5 MB limit
                raise ValidationError("Image size must be under 5 MB.")
        return image

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if video.content_type != 'video/mp4':
                raise ValidationError("Only MP4 videos are supported.")
            if video.size > 50 * 1024 * 1024:  # 50 MB limit
                raise ValidationError("Video size must be under 50 MB.")
        return video



class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "profession",
            "location",
            "profile_picture",
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
        label="Filter by Profession"
    )

    def __init__(self, *args, **kwargs):
        super(ProfessionFilterForm, self).__init__(*args, **kwargs)
        # Dynamically generate profession choices from all profiles
        all_professions = Profile.objects.values_list('profession', flat=True).distinct()
        self.fields['professions'].choices = [(prof, prof) for prof in all_professions if prof]



class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write your message here...'})
        }