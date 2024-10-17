from django.shortcuts import render

from .models import Profile

from django.contrib.auth.decorators import login_required

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

@login_required
def profile(request):
    # Ensure the user's profile exists (create one if not)
    user_profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Get all uploads related to this profile, ordered by upload_date (most recent first)
    uploads = Upload.objects.filter(profile=user_profile).order_by('-upload_date')

    if request.method == 'POST':
        # Handle media upload (images/videos with caption)
        upload_form = UploadForm(request.POST, request.FILES)
        
        # Handle profile update (bio, profile picture)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        
        # Check if both forms are valid
        if upload_form.is_valid() and profile_form.is_valid():
            # Save the media upload (image/video)
            upload = upload_form.save(commit=False)
            upload.profile = user_profile  # Associate the upload with the user's profile
            upload.save()  # Save the upload
            
            # Save the updated profile (bio, profile picture)
            profile_form.save()
            
            # Refresh the page to show the updates
            return HttpResponseRedirect(request.path_info)
    else:
        # Initialize forms if not a POST request
        upload_form = UploadForm()
        profile_form = ProfileUpdateForm(instance=user_profile)

    # Render the profile template with the user's data, uploads, and the forms
    return render(request, 'users/profile.html', {
        'user': request.user,
        'uploads': uploads,
        'upload_form': upload_form,
        'profile_form': profile_form
    })


from django.db.models import Q
from .models import Profile
from .forms import ProfessionFilterForm


@login_required
def global_feed(request):
    # Fetch all profiles except the signed-in user's profile
    profiles = Profile.objects.exclude(user=request.user)

    # Handle filtering by profession
    profession_filter_form = ProfessionFilterForm(request.GET or None)  # Form for profession filtering
    if profession_filter_form.is_valid():
        professions = profession_filter_form.cleaned_data.get('professions')
        if professions:
            profiles = profiles.filter(profession__in=professions)  # Filter profiles by selected professions

    return render(request, 'users/global_feed.html', {
        'profiles': profiles,
        'profession_filter_form': profession_filter_form
    })


from django.shortcuts import get_object_or_404

@login_required
def profile_detail(request, user_id):
    # Get the profile for the clicked user
    profile = get_object_or_404(Profile, user__id=user_id)
    
    # Access the user's uploads (use 'uploads' if you specified a related_name in the Upload model)
    uploads = profile.uploads.all().order_by('-upload_date')  # Use profile.uploads if related_name is 'uploads'
    
    return render(request, 'users/profile_detail.html', {'profile': profile, 'uploads': uploads})

