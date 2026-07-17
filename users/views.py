
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError

from django.contrib.auth.models import User

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, authenticate
from django.contrib import messages
from .forms import UserRegisterForm, UploadForm, ProfileUpdateForm, PaymentDetailsForm
from .models import Profile, Upload

# Razorpay client is loaded lazily inside the payment-details view so the
# rest of users/views.py keeps working even when razorpay isn't configured
# (e.g. during local dev without payment env vars).


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
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
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


@login_required
def profile(request):
    user_profile = request.user.profile
    unread_count = Message.objects.filter(recipient=request.user, is_read=False).count()

    if request.method == 'POST':
        if 'upload_submit' in request.POST:
            # Handle only the upload form
            profile_form = ProfileUpdateForm(instance=user_profile)   # unbound
            upload_form = UploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                upload = upload_form.save(commit=False)
                upload.profile = user_profile
                try:
                    upload.save()
                except ValidationError as e:
                    messages.error(request, e.message)
                    return redirect('profile')
                # Kick off background ffmpeg re-encode for videos. If the
                # worker is offline, the message queues in Redis and the
                # upload still returns success — the user is never blocked.
                if upload.video:
                    from users.tasks import compress_upload_video
                    compress_upload_video.delay(upload.id)
                messages.success(request, "Image/video uploaded successfully.")
                return redirect('profile')
            else:
                messages.error(request, "Image/video upload failed. Please fix the errors below.")

        elif 'profile_submit' in request.POST:
            # Handle only the profile update form
            profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
            upload_form = UploadForm()  # blank

            if profile_form.is_valid():
                profile_obj = profile_form.save(commit=False)

                # <<< bullet-proof the avatar save, even if the form omits the field
                if 'profile_picture' in request.FILES:
                    profile_obj.profile_picture = request.FILES['profile_picture']
                if 'cover_photo' in request.FILES:
                    profile_obj.cover_photo = request.FILES['cover_photo']
                profile_obj.save()
                # >>>

                messages.success(request, "Profile updated successfully.")
                return redirect('profile')
            else:
                messages.error(request, "Profile update failed. Please correct the errors below.")

        else:
            # Fallback
            profile_form = ProfileUpdateForm(instance=user_profile)
            upload_form = UploadForm()
    else:
        profile_form = ProfileUpdateForm(instance=user_profile)
        upload_form = UploadForm()

    # Newest uploads first; hide the avatar file if it lives in Uploads too
    uploads_qs = Upload.objects.filter(profile=user_profile).order_by('-upload_date')
    if user_profile.profile_picture:
        uploads_qs = uploads_qs.exclude(image=user_profile.profile_picture.name)

    return render(request, 'users/profile.html', {
        'profile_form': profile_form,
        'upload_form': upload_form,
        'uploads': uploads_qs,
        'profile': user_profile,
        'unread_count': unread_count,
    })




from django.db.models import Q
from .forms import ProfessionFilterForm
from django.core.paginator import Paginator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.core.cache import cache




@login_required
def global_feed(request):
    profession_filter_form = ProfessionFilterForm(request.GET or None)
    page_number = request.GET.get("page", "1")
    selected_profession = request.GET.get("professions", "")
    professions_key = selected_profession or "all"
    cache_key = f"web:feed:{page_number}:{professions_key}"

    profiles_page = cache.get(cache_key)
    if profiles_page is None:
        profiles_qs = (
            Profile.objects.select_related("user")
            .only("user__id", "user__username", "profession", "profile_picture")
        )
        if profession_filter_form.is_valid():
            professions = profession_filter_form.cleaned_data.get("professions")
            if professions:
                profiles_qs = profiles_qs.filter(profession__in=professions)
        paginator = Paginator(profiles_qs, 20)
        profiles_page = paginator.get_page(page_number)
        cache.set(cache_key, profiles_page, 60)

    return render(request, "users/global_feed.html", {
        "profiles": profiles_page,
        "profession_filter_form": profession_filter_form,
        "selected_profession": selected_profession,
        "current_user_id": request.user.id,
    })

from django.shortcuts import get_object_or_404

@login_required
def profile_detail(request, user_id):
    from datetime import date
    from bookings.models import Engagement

    cache_key = f"web:profile:{user_id}"
    cached = cache.get(cache_key)

    if cached is None:
        user_profile = get_object_or_404(
            Profile.objects.select_related("user"),
            user__id=user_id,
        )
        uploads = list(
            Upload.objects.filter(profile=user_profile)
            .order_by("-upload_date")[:20]
        )
        today = date.today()
        gig_qs = Engagement.objects.filter(
            performer=user_profile.user,
            status=Engagement.STATUS_ACCEPTED,
            date__lt=today,
        )
        cached = {
            "profile": user_profile,
            "uploads": uploads,
            "gigs_count": gig_qs.count(),
            "last_engagement": gig_qs.order_by("-date").first(),
        }
        cache.set(cache_key, cached, 60)

    viewer = request.user
    profile = cached["profile"]
    hire_state = "none"
    if viewer.is_authenticated and viewer != profile.user and profile.is_performer:
        if viewer.profile.client_blacklisted:
            hire_state = "blacklisted"
        elif not viewer.profile.is_potential_client:
            hire_state = "toggle_off"
        elif not viewer.profile.client_approved:
            hire_state = "pending"
        else:
            hire_state = "ready"

    return render(request, "users/profile_detail.html", {
        **cached,
        "hire_state": hire_state,
    })

from .models import Message


# Messaging view
from django.contrib.auth.decorators import login_required
from users.models import User, Message

from django.contrib.auth.decorators import login_required
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

@login_required
def inbox(request):
    user = request.user

    # Get all messages involving the user
    all_messages = (Message.objects.filter(Q(sender=user) | Q(recipient=user)).select_related('sender','recipient'))

    # Identify each unique conversation as a frozen set of (sender_id, recipient_id)
    latest_by_pair = {}

    for message in all_messages:
        participants = frozenset([message.sender_id, message.recipient_id])
        if participants not in latest_by_pair or message.timestamp > latest_by_pair[participants].timestamp:
            latest_by_pair[participants] = message

    # Sort the conversations by most recent timestamp
    messages_to_display = sorted(latest_by_pair.values(), key=lambda m: m.timestamp, reverse=True)

    return render(request, 'users/inbox.html', {'messages': messages_to_display})






from django.contrib.auth.decorators import login_required



def is_participant(user, thread_user1, thread_user2):
    """
    Helper function to check if the user is part of the thread.
    """
    return user == thread_user1 or user == thread_user2


from django.contrib.auth.decorators import login_required
from users.models import User, Message
from datetime import date
today = date.today().isoformat()

@login_required
def message_thread(request, user_id):
    """
    View for handling the message thread between the logged-in user and another user.
    Includes normal messaging and hiring requests.
    """
    other_user = get_object_or_404(User, id=user_id)

    if request.method == "POST":

        if request.POST.get('hiring_action') in ['accept', 'decline']:
            # Accept or Decline a Hiring Request
            message_id = request.POST.get('message_id')
            hire_message = get_object_or_404(Message, id=message_id, recipient=request.user)

            action = request.POST['hiring_action']

            if action == 'accept':
                hire_message.hiring_status = 'accepted'
                hire_message.save()

                # Auto-decline other pending hiring requests
                Message.objects.filter(
                    recipient=hire_message.recipient,
                    date=hire_message.date,
                    hiring_status='pending'
                ).exclude(id=hire_message.id).update(hiring_status='declined')

                messages.success(request, "Hiring request accepted. Other pending requests have been declined.")

            elif action == 'decline':
                hire_message.hiring_status = 'declined'
                hire_message.save()
                messages.success(request, "Hiring request declined.")

            return redirect('message-thread', user_id=hire_message.sender.id)

        elif request.POST.get('hiring_request') == 'true':
            # New Hiring Request Creation
            date = request.POST.get('date')
            time = request.POST.get('time')
            location = request.POST.get('location')

            if not (date and time and location):
                messages.error(request, "All fields are required for hiring.")
            else:
                # 🔥 Corrected Conflict Check (Block if pending or accepted exists) 🔥
                conflict = Message.objects.filter(
                    recipient=other_user,
                    date=date,
                    hiring_status__in=['pending', 'accepted']
                ).exists()

                if conflict:
                    messages.error(request, "This user is already hired or has a pending hiring request for the selected date.")

                    # Re-render thread view if conflict
                    messages_qs = (
                        Message.objects.filter(
                            sender__in=[request.user, other_user],
                            recipient__in=[request.user, other_user]
                        )
                        .select_related('sender', 'recipient')   # ← added
                        .order_by('timestamp')
                    )

                    return render(request, 'users/message_thread.html', {
                        'messages_qs': messages_qs,
                        'other_user': other_user,
                        'today_date': today,
                    })

                # ✅ No conflict, allow creating new pending hiring
                Message.objects.create(
                    sender=request.user,
                    recipient=other_user,
                    content="Hiring Request",
                    date=date,
                    time=time,
                    location=location,
                    hiring_status='pending'
                )
                messages.success(request, "Hiring request sent successfully.")
                return redirect('message-thread', user_id=other_user.id)

        else:
            # Regular Message
            content = request.POST.get("content", "").strip()
            if not content:
                messages.error(request, "Message content cannot be empty.")
            else:
                Message.objects.create(sender=request.user, recipient=other_user, content=content)
                messages.success(request, "Message sent successfully.")
            return redirect('message-thread', user_id=other_user.id)

    # GET request - Render chat window
    messages_qs = (
        Message.objects.filter(
            sender__in=[request.user, other_user],
            recipient__in=[request.user, other_user]
        )
        .select_related('sender', 'recipient')   # ← added
        .order_by('timestamp')
    )

    return render(request, 'users/message_thread.html', {
        'messages_qs': messages_qs,
        'other_user': other_user,
        'today_date': today,
    })



from datetime import date
from .models import Message

from bookings.models import Engagement
from datetime import date

@login_required
def live_events(request):
    """Upcoming + past accepted engagements, optimized + paginated."""
    page_number = request.GET.get("page", "1")
    cache_key = f"web:events:{page_number}"
    cached = cache.get(cache_key)

    if cached is None:
        today = date.today()
        events_qs = (
            Engagement.objects.filter(
                status=Engagement.STATUS_ACCEPTED,
                date__gte=today,
            )
            .select_related("client", "performer", "performer__profile")
            .order_by("date", "time")
        )
        paginator = Paginator(events_qs, 10)
        page_obj = paginator.get_page(page_number)
        past_events = list(
            Engagement.objects.filter(
                status=Engagement.STATUS_ACCEPTED,
                date__lt=today,
            )
            .select_related("client", "performer", "performer__profile")
            .order_by("-date", "-time")[:20]
        )
        cached = {
            "events": page_obj.object_list,
            "page_obj": page_obj,
            "past_events": past_events,
        }
        cache.set(cache_key, cached, 60)

    return render(request, "users/live_events.html", cached)


# ---------------------------------------------------------------------------
# Payment / KYC settings — Razorpay linked account onboarding
# ---------------------------------------------------------------------------
@login_required
def update_payment_details(request):
    """
    Performer-facing form to save PAN + bank + phone, then spin up a
    Razorpay linked account in the background.

    Flow:
      1. User opens settings drawer on their own profile → clicks
         "Set up payment details" → lands here.
      2. They fill PAN, IFSC, account number, phone, fee → submit.
      3. We save to Profile (plaintext for Phase 1; encrypt later).
      4. If all required fields are filled AND no Razorpay linked
         account exists yet, we call Razorpay's Account API to create
         one. Razorpay does RBI review in 5-7 business days; status
         flips to "approved" via webhook later.
      5. Redirect them back to their own profile page.

    Always operates on request.user.profile — there's no user_id in the
    URL, so a performer can never edit another performer's bank details.
    """
    profile = request.user.profile

    if request.method == "POST":
        form = PaymentDetailsForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()

            if not settings.RAZORPAY_ROUTE_ENABLED:
                # ── Payouts mode: no linked account / KYC wait. Bank details on
                # file = payable. Pre-create the RazorpayX contact + fund account
                # now so the first real payout is a single call and any bad bank
                # detail surfaces here, not weeks later at release time.
                complete = (
                    profile.is_performer
                    and profile.bank_account_holder_name
                    and profile.bank_account_number
                    and profile.bank_ifsc
                )
                if complete and not profile.razorpayx_fund_account_id:
                    try:
                        from bookings.services.payments import PaymentService
                        PaymentService.ensure_payout_destination(profile)
                    except Exception as e:
                        # Non-fatal: details are saved; release_to_performer will
                        # create the destination lazily and retry.
                        messages.warning(
                            request,
                            f"Details saved; payout setup will finish "
                            f"automatically (note: {e}).",
                        )
                messages.success(request, "Payment details updated.")
                return redirect("profile")

            # ── Route mode: existing linked-account onboarding (verbatim) ──
            # Razorpay linked-account creation only when:
            #   - User is actually a performer (clients never need KYC)
            #   - No linked account exists yet (idempotent on re-submit)
            #   - All Razorpay-required fields are now filled
            should_onboard = (
                profile.is_performer
                and not profile.razorpay_account_id
                and profile.pan_number
                and profile.bank_account_number
                and profile.bank_ifsc
                and profile.phone_number
            )
            if should_onboard:
                try:
                    # Lazy import so this view loads even without razorpay.
                    from bookings.services.razorpay_client import get_client
                    client = get_client()
                    account = client.account.create({
                        "type": "route",
                        "reference_id": f"user_{profile.user.id}",
                        "email": profile.user.email or f"user{profile.user.id}@artkhoj.local",
                        "phone": profile.phone_number,
                        "legal_business_name": profile.bank_account_holder_name,
                        "business_type": "individual",
                        "contact_name": profile.bank_account_holder_name,
                        "profile": {
                            "category": "ecommerce",
                            "subcategory": "marketplace",
                        },
                        "legal_info": {"pan": profile.pan_number},
                    })
                    profile.razorpay_account_id = account["id"]
                    profile.razorpay_kyc_status = "pending"
                    profile.save(update_fields=[
                        "razorpay_account_id", "razorpay_kyc_status",
                    ])
                    messages.success(
                        request,
                        "Payment details saved. KYC submitted for Razorpay "
                        "review (5-7 business days)."
                    )
                except Exception as e:
                    # Razorpay onboarding failed — keep the saved details so
                    # the performer can retry without re-entering everything.
                    messages.error(
                        request,
                        f"Saved your details but Razorpay onboarding failed: {e}",
                    )
            else:
                messages.success(request, "Payment details updated.")
            # After saving payment details, return user to their OWN profile dashboard
            # (profile.html), not the public-facing profile_detail.html.
            return redirect("profile")
    else:
        form = PaymentDetailsForm(instance=profile)

    return render(request, "users/payment_details_form.html", {"form": form})

























