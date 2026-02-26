from django.db import models

# Create your models here.

# appointment/models.py
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta


class Engagement(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED_CLIENT = "cancelled_client"
    STATUS_CANCELLED_PERFORMER = "cancelled_performer"
    STATUS_AUTO_EXPIRED = "auto_expired"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_CANCELLED_CLIENT, "Cancelled by client"),
        (STATUS_CANCELLED_PERFORMER, "Cancelled by performer"),
        (STATUS_AUTO_EXPIRED, "Auto expired"),
    ]

    # Client (hirer) & performer
    client = models.ForeignKey(
        User,
        related_name="hire_requests_made",
        on_delete=models.CASCADE,
    )
    performer = models.ForeignKey(
        User,
        related_name="hire_requests_received",
        on_delete=models.CASCADE,
    )

    # 5) Time / venue / occasion
    date = models.DateField()
    time = models.TimeField()
    venue = models.CharField(max_length=255)
    occasion = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    # 10, 11) Emergency text fields for last-minute cancels
    client_emergency_reason = models.TextField(blank=True)
    performer_emergency_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "time", "performer"]
        # Uniqueness/limits enforced in clean() to keep it model-heavy

            # High-value indexes for query patterns used across the app
        indexes = [
        # Client dashboards + "max 3 future bookings" checks
        models.Index(fields=["client", "status", "date"]),

        # Performer dashboards + "only one accepted per day" rules
        models.Index(fields=["performer", "status", "date"]),

        # Live events view: accepted future events ordered by date/time
        models.Index(fields=["status", "date", "time"]),
        ]

    def __str__(self) -> str:
        return f"{self.client} → {self.performer} on {self.date} @ {self.time} ({self.status})"

    # ----- Helpers -----
    def event_datetime(self):
        """
        Combine date & time into an aware datetime in the current time zone.
        """
        tz = timezone.get_current_timezone()
        return timezone.make_aware(datetime.combine(self.date, self.time), tz)

    # ----- Validation -----
    def clean(self):
        """
        Model-level rules:
        - Can't hire yourself.
        - 13) A client can't send multiple ACTIVE (pending/accepted) requests
              to the *same performer* on the same day.
        - 8) Client limited to 3 ongoing future engagements (pending/accepted).
        """
        super().clean()

        if not self.client_id or not self.performer_id:
            return

        if self.client == self.performer:
            raise ValidationError("You cannot hire yourself.")

        if not self.date or not self.time:
            raise ValidationError("Date and time are required.")

        # 13) No multiple requests same day to the same performer
        qs = Engagement.objects.filter(
            client=self.client,
            performer=self.performer,
            date=self.date,
            status__in=[self.STATUS_PENDING, self.STATUS_ACCEPTED],
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                "You already have a request for this performer on that date."
            )

        # 8) Max 3 ongoing future engagements for a client
        if self.client_id:
            active_qs = Engagement.objects.filter(
                client=self.client,
                status__in=[self.STATUS_PENDING, self.STATUS_ACCEPTED],
                date__gte=timezone.now().date(),
            )
            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)
            if active_qs.count() >= 3:
                raise ValidationError(
                    "You already have 3 ongoing bookings. Ask the admin if you need a higher limit."
                )

    # ----- Business logic methods -----
    def _ensure_pending(self):
        if self.status != self.STATUS_PENDING:
            raise ValidationError("Only pending requests can be updated.")

    def _ensure_accept_within_24h(self):
        """
        9) Performer must accept within 24h of being requested.
        """
        if self.created_at and timezone.now() > self.created_at + timedelta(hours=24):
            # Mark as expired once somebody tries to interact with it
            if self.status == self.STATUS_PENDING:
                self.status = self.STATUS_AUTO_EXPIRED
                self.save(update_fields=["status"])
            raise ValidationError("This request has expired (no response within 24 hours).")

    def _check_last_minute_cancellation(self, emergency_reason: str):
        """
        10 & 11) Cancelling inside 24 hours requires an emergency reason.
        """
        now = timezone.now()
        if self.event_datetime() - now <= timedelta(hours=24) and not emergency_reason.strip():
            raise ValidationError(
                "Cancelling within 24 hours requires an emergency reason."
            )

    def accept(self):
        """
        Performer accepts the request.

        Rules:
        - Must be pending.
        - Must be within 24h of creation.
        - 7) Only *one* accepted booking per performer per date.
              When accepting one, all other pending requests for that
              performer+date are cancelled.
        """
        self._ensure_pending()
        self._ensure_accept_within_24h()

        # Block if there is already an accepted gig this day
        conflict_exists = Engagement.objects.filter(
            performer=self.performer,
            date=self.date,
            status=self.STATUS_ACCEPTED,
        ).exclude(pk=self.pk).exists()

        if conflict_exists:
            raise ValidationError(
                "You already accepted a different event on this date."
            )

        # Cancel other pending requests for same performer + date
        Engagement.objects.filter(
            performer=self.performer,
            date=self.date,
            status=self.STATUS_PENDING,
        ).exclude(pk=self.pk).update(status=self.STATUS_CANCELLED_PERFORMER)

        self.status = self.STATUS_ACCEPTED
        self.save(update_fields=["status"])

    def decline(self):
        """Performer declines."""
        self._ensure_pending()
        self.status = self.STATUS_DECLINED
        self.save(update_fields=["status"])

    def cancel_by_client(self, emergency_reason: str = ""):
        """
        Client cancels a pending/accepted gig.
        10) Last-minute requires emergency_reason.
        """
        if self.status not in [self.STATUS_PENDING, self.STATUS_ACCEPTED]:
            raise ValidationError("Only pending or accepted bookings can be cancelled.")

        self._check_last_minute_cancellation(emergency_reason)
        self.client_emergency_reason = emergency_reason
        self.status = self.STATUS_CANCELLED_CLIENT
        self.save(update_fields=["client_emergency_reason", "status"])

    def cancel_by_performer(self, emergency_reason: str = ""):
        """
        Performer cancels.
        11) Last-minute requires emergency_reason.
        """
        if self.status not in [self.STATUS_PENDING, self.STATUS_ACCEPTED]:
            raise ValidationError("Only pending or accepted bookings can be cancelled.")

        self._check_last_minute_cancellation(emergency_reason)
        self.performer_emergency_reason = emergency_reason
        self.status = self.STATUS_CANCELLED_PERFORMER
        self.save(update_fields=["performer_emergency_reason", "status"])
