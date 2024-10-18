from django.shortcuts import render

from .models import Profile

from django.contrib.auth.decorators import login_required

from django.contrib.auth.models import User

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
    # Get the profile of the user being viewed
    user_profile = get_object_or_404(Profile, user__id=user_id)
    
    # Get uploads for the profile
    uploads = Upload.objects.filter(profile=user_profile).order_by('-upload_date')

    unread_messages = Message.objects.filter(recipient=request.user, is_read=False)

    # Pass data to the template
    return render(request, 'users/profile_detail.html', {
        'profile': user_profile,
        'uploads': uploads,
        'unread_messages': unread_messages
    })

from .models import Message
from .forms import MessageForm


# Messaging view
@login_required
def send_message(request, recipient_id):
    recipient = get_object_or_404(User, id=recipient_id)

    # Prevent duplicate messages before a reply
    existing_message = Message.objects.filter(sender=request.user, recipient=recipient, is_read=False).first()
    if existing_message:
        messages.error(request, "You have already sent a message to this user. Please wait for a reply.")
        return redirect('message-thread', user_id=recipient_id)

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.sender = request.user
            message.recipient = recipient
            message.save()
            messages.success(request, "Your message has been sent.")
            return redirect('message-thread', user_id=recipient.id)
    else:
        form = MessageForm()

    return render(request, 'users/send_message.html', {'form': form, 'recipient': recipient})

# Inbox view
def inbox(request):
    user = request.user
    received_messages = Message.objects.filter(recipient=user).order_by('-timestamp')

    # Mark messages as read if they're accessed from the inbox
    for message in received_messages:
        if not message.is_read:
            message.is_read = True
            message.save()

    return render(request, 'users/inbox.html', {'messages': received_messages})

from django.db.models import Q

def message_thread(request, user_id):
    other_user = get_object_or_404(User, id=user_id)

    # Fetch the messages between the current user and the other user
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=other_user)) | 
        (Q(sender=other_user) & Q(recipient=request.user))
    ).order_by('timestamp')

    # Form for replying in the message thread
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.sender = request.user
            reply.recipient = other_user
            reply.save()
            return redirect('message-thread', user_id=other_user.id)  # Redirect to the thread after sending reply
    else:
        form = MessageForm()

    return render(request, 'users/message_thread.html', {
        'other_user': other_user,
        'messages': messages,
        'form': form  # Passing the form to the template
    })


