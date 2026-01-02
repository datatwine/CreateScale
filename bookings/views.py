from django.shortcuts import render

# Create your views here.
# appointment/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from users.models import Profile
from .forms import EngagementRequestForm, EmergencyCancelForm
from .models import Engagement


@login_required
def create_hire_request(request, performer_id):
    """
    Entry point from a performer's profile (Rule 5).
    Creates a pending Engagement if the client and performer are allowed.
    """
    performer_profile = get_object_or_404(Profile, user_id=performer_id)
    client_profile = request.user.profile

    if request.user == performer_profile.user:
        messages.error(request, "You can't hire yourself.")
        return redirect("profile-detail", user_id=performer_profile.user.id)

    # Client role checks (2, 3, 4, 15)
    if not client_profile.is_potential_client:
        messages.error(
            request,
            "Turn on the 'I hire performers' toggle on your profile before sending requests.",
        )
        return redirect("profile")

    if not client_profile.client_approved:
        messages.error(
            request,
            "Admin has not approved you for hiring performers yet."
        )
        return redirect("profile")

    if client_profile.client_blacklisted:
        messages.error(
            request,
            "You are currently blocked from hiring performers."
        )
        return redirect("profile")

    # Performer checks (2, 15)
    if not performer_profile.is_performer or performer_profile.performer_blacklisted:
        messages.error(
            request,
            "This user is not available for hire right now."
        )
        return redirect("profile-detail", user_id=performer_profile.user.id)

    if request.method == "POST":
        form = EngagementRequestForm(request.POST)
        if form.is_valid():
            engagement = form.save(commit=False)

            # Attach client & performer BEFORE running model validation
            engagement.client = request.user
            engagement.performer = performer_profile.user


            try:
                engagement.full_clean()  # runs model.clean()
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
                return render(
                    request,
                    "bookings/hire_form.html",
                    {"form": form, "performer_profile": performer_profile},
                )

            engagement.save()
            messages.success(request, "Hiring request sent.")
            return redirect("bookings:client-engagements")
    else:
        form = EngagementRequestForm()

    return render(
        request,
        "bookings/hire_form.html",
        {"form": form, "performer_profile": performer_profile},
    )


@login_required
def client_engagement_list(request):
    """
    Minimal 'dashboard' for the client showing their engagements.
    (Rule 16 – basic version)
    """
    engagements = Engagement.objects.filter(client=request.user).select_related(
        "performer"
    )
    return render(
        request,
        "bookings/client_engagements.html",
        {"engagements": engagements},
    )


@login_required
def performer_engagement_list(request):
    """
    Minimal 'dashboard' for the performer showing requests & gigs.
    (Rule 17 – basic version)
    """
    engagements = Engagement.objects.filter(performer=request.user).select_related(
        "client"
    )
    return render(
        request,
        "bookings/performer_engagements.html",
        {"engagements": engagements},
    )


@login_required
def engagement_detail(request, pk):
    """
    Single engagement screen where BOTH sides can accept/decline/cancel.
    Enforces 24h rules + emergency reasons (9, 10, 11).
    """
    engagement = get_object_or_404(Engagement, pk=pk)

    is_client = engagement.client == request.user
    is_performer = engagement.performer == request.user
    is_admin = request.user.is_superuser

    if not (is_client or is_performer or is_admin):
        raise PermissionDenied("You are not allowed to view this booking.")

    if request.method == "POST":
        action = request.POST.get("action")
        form = EmergencyCancelForm(request.POST)

        try:
            if action == "accept" and is_performer:
                engagement.accept()
                messages.success(request, "You accepted this booking.")
            elif action == "decline" and is_performer:
                engagement.decline()
                messages.success(request, "You declined this booking.")
            elif action == "cancel_client" and is_client:
                if form.is_valid():
                    engagement.cancel_by_client(
                        emergency_reason=form.cleaned_data["emergency_reason"]
                    )
                    messages.success(request, "You cancelled this booking.")
            elif action == "cancel_performer" and is_performer:
                if form.is_valid():
                    engagement.cancel_by_performer(
                        emergency_reason=form.cleaned_data["emergency_reason"]
                    )
                    messages.success(request, "You cancelled this booking.")
            else:
                messages.error(request, "Invalid action.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))

        if is_client:
            return redirect("bookings:client-engagements")
        if is_performer:
            return redirect("bookings:performer-engagements")
        return redirect("admin:index")

    else:
        form = EmergencyCancelForm()

    return render(
        request,
        "bookings/engagement_detail.html",
        {
            "engagement": engagement,
            "is_client": is_client,
            "is_performer": is_performer,
            "form": form,
        },
    )
