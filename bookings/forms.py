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
            "occasion": forms.TextInput(attrs={"placeholder": "Occasion (wedding, house party, etc.)"}),
        }


class EmergencyCancelForm(forms.Form):
    """
    Simple form used on the engagement-detail page when cancelling close to the event.
    """
    emergency_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Required only if you are cancelling within 24 hours of the event.",
        label="Emergency reason",
    )
