# appointment/forms.py
from django import forms
from .models import Engagement


class EngagementRequestForm(forms.ModelForm):
    """
    Client-facing form for creating a new hire request.
    """

    class Meta:
        model = Engagement
        fields = ["date", "time", "venue", "occasion"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "venue": forms.TextInput(attrs={"placeholder": "Venue / address"}),
            "occasion": forms.TextInput(
                attrs={"placeholder": "Occasion (wedding, house party, etc.)"}
            ),
        }


class CancelEngagementForm(forms.Form):
    """
    Mandatory cancellation reason. Replaces the old EmergencyCancelForm —
    cancellation is now blocked entirely within 24h, and outside that window
    a reason is always required (it's surfaced to the other party).
    """

    cancellation_reason = forms.CharField(
        required=True,
        min_length=10,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Why are you cancelling? The other party will see this.",
            }
        ),
        label="Cancellation reason",
    )


class DisputeForm(forms.Form):
    """
    Client raises an issue against a paid engagement within the 24h
    post-event dispute window. Once submitted, the Celery payout task
    skips this engagement until an admin resolves it.
    """

    dispute_reason = forms.CharField(
        required=True,
        min_length=10,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "What went wrong? Please describe in detail. An admin will review.",
            }
        ),
        label="Issue description",
    )
