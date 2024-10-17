from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Upload, Profile

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()
    profession = forms.CharField(max_length=100)
    location = forms.CharField(max_length=100)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'profession', 'location']


class UploadForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ['image', 'video', 'caption']


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['profession', 'location', 'profile_picture','bio']