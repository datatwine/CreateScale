from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from .forms import UserRegisterForm, UploadForm, ProfileUpdateForm
from .models import Profile, Upload

from django.http import HttpResponseRedirect  # Import the form for handling uploads

# Sign-up view
def signup(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()  # Save the new user
            login(request, user)  # Log the user in
            return redirect('profile')  # Redirect to profile page
    else:
        form = UserRegisterForm()
    return render(request, 'users/signup.html', {'form': form})

# Login view
def signin(request):
    next_url = request.GET.get('next')  # Get the 'next' URL parameter, if available
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                if next_url:  # Redirect to the 'next' URL if available
                    return redirect(next_url)
                else:
                    return redirect('profile')  # Otherwise, redirect to profile
            else:
                messages.error(request, 'Invalid username or password')
        else:
            messages.error(request, 'Invalid username or password')
    form = AuthenticationForm()
    return render(request, 'users/login.html', {'form': form})

# Profile view (after login)
from django.http import HttpResponseRedirect
from django.shortcuts import render
from .models import Profile, Upload
from .forms import UploadForm

def profile(request):
    # Ensure the user's profile exists (create one if not)
    user_profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Get all uploads related to this profile, ordered by upload_date (most recent first)
    uploads = Upload.objects.filter(profile=user_profile).order_by('-upload_date')
    
    # Handle the form for uploading media (image/video) with caption
    if request.method == 'POST':
        upload_form = UploadForm(request.POST, request.FILES)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        
        if upload_form.is_valid() and profile_form.is_valid():
            # Handle media upload
            upload = upload_form.save(commit=False)
            upload.profile = user_profile  # Associate the upload with the user's profile
            upload.save()  # Save the upload (image/video, caption, and upload date)
            
            # Handle profile picture update
            profile_form.save()  # Save the profile picture
            
            return HttpResponseRedirect(request.path_info)  # Refresh the page to display the new upload/profile picture
    else:
        upload_form = UploadForm()
        profile_form = ProfileUpdateForm(instance=user_profile)

    # Render the profile template with the user's data, uploads, the upload form, and profile update form
    return render(request, 'users/profile.html', {
        'user': request.user,
        'uploads': uploads,
        'upload_form': upload_form,
        'profile_form': profile_form
    })


