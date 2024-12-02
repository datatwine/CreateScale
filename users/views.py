
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
            user = form.save()  # Save the user instance
            # Save additional fields in the Profile model
            user.profile.profession = form.cleaned_data.get('profession')
            user.profile.location = form.cleaned_data.get('location')
            user.profile.save()  # Explicitly save the profile
            login(request, user)  # Log the user in
            return redirect('profile')  # Redirect to the profile page
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
    user_profile = Profile.objects.get(user=request.user)  # Retrieve the current user's profile

    if request.method == 'POST':
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
        upload_form = UploadForm(request.POST, request.FILES)

        if profile_form.is_valid() and upload_form.is_valid():
            profile_form.save()  # Save profile updates
            upload = upload_form.save(commit=False)
            upload.profile = user_profile  # Associate the upload with the current user's profile
            upload.save()
            messages.success(request, "Profile updated and image uploaded successfully!")
        else:
            if not profile_form.is_valid():
                messages.error(request, "Profile update failed. Please correct the errors below.")
            if not upload_form.is_valid():
                messages.error(request, "Image upload failed. Please correct the errors below.")
    else:
        profile_form = ProfileUpdateForm(instance=user_profile)
        upload_form = UploadForm()

    # Order uploads by `upload_date` in descending order to show the latest uploads first
    uploads = Upload.objects.filter(profile=user_profile).order_by('-upload_date')

    return render(request, 'users/profile.html', {
        'profile_form': profile_form,
        'upload_form': upload_form,
        'uploads': uploads,  # Pass uploads to the template
        'profile': user_profile
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
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from users.models import User, Message

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import Message, User

@login_required
def send_message(request, user_id):
    receiver = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if not content:
            messages.error(request, "Message content cannot be empty.")
            return redirect("profile-detail", user_id=receiver.id)

        Message.objects.create(sender=request.user, recipient=receiver, content=content)
        messages.success(request, "Message sent successfully.")
        return redirect("message-thread", user_id=receiver.id)

    return redirect("profile-detail", user_id=receiver.id)


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




