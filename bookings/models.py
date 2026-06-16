from django.db import models

# Create your models here.

# appointment/models.py
from django.conf import settings
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

    # 10, 11) Emergency text fields for last-minute cancels (kept temporarily;
    # Phase 3 replaces them with mandatory cancellation_reason below).
    client_emergency_reason = models.TextField(blank=True)
    performer_emergency_reason = models.TextField(blank=True)

    # --- Payment lifecycle (Razorpay integration) -----------------------------
    # Snapshot of performer's profile fee at hire time (immutable for this
    # engagement). Profile fee can change anytime without affecting open bookings.
    fee = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Locked-in fee in rupees, snapshot from performer profile at hire time.",
    )

    PAYMENT_UNPAID   = "unpaid"
    PAYMENT_PAID     = "paid"       # captured + held in Razorpay Route escrow
    PAYMENT_RELEASED = "released"   # transferred to performer's bank
    PAYMENT_REFUNDED = "refunded"   # reversed back to client

    PAYMENT_CHOICES = [
        (PAYMENT_UNPAID,   "Unpaid"),
        (PAYMENT_PAID,     "Paid (in escrow)"),
        (PAYMENT_RELEASED, "Released to performer"),
        (PAYMENT_REFUNDED, "Refunded to client"),
    ]
    payment_status = models.CharField(
        max_length=16, choices=PAYMENT_CHOICES,
        default=PAYMENT_UNPAID, db_index=True,
    )

    # Timestamps for payment-driven state machine
    accepted_at = models.DateTimeField(null=True, blank=True)
    paid_at     = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    # Cancellation (mandatory reason after Phase 3 rewrite)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.CharField(
        max_length=16, blank=True,
        choices=[("client", "Client"), ("performer", "Performer")],
    )

    # Dispute fields — client raises issue within 24h of event end.
    # Disputed engagements skip auto-release; admin resolves manually.
    disputed_at         = models.DateTimeField(null=True, blank=True)
    dispute_reason      = models.TextField(blank=True)
    dispute_resolved_at = models.DateTimeField(null=True, blank=True)

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

    def _check_within_24h_cancellation_block(self):
        """
        REPLACES old emergency-reason logic. Within 24h of the event,
        cancellation is BLOCKED entirely for both parties (no override).
        Same-day / short-notice bookings are therefore non-cancellable from
        the moment they exist, which matches the rule the client + performer
        are warned about on the hire form and engagement detail page.
        """
        if self.event_datetime() - timezone.now() <= timedelta(hours=24):
            raise ValidationError(
                "Bookings cannot be cancelled within 24 hours of the event."
            )

    # --- Payment-window helpers (used by Celery + templates) ---------
    def payment_deadline(self):
        """
        When the client's payment window closes. Returns None if the
        engagement hasn't been accepted yet (no clock has started).

        Dynamic window: usually 24h after performer acceptance, but for
        short-notice bookings we clamp to event_time - 2h so payment must
        close before the gig actually happens.
        """
        if not self.accepted_at:
            return None
        standard = self.accepted_at + timedelta(
            hours=settings.RAZORPAY_PAYMENT_WINDOW_HOURS
        )
        event_minus_buffer = self.event_datetime() - timedelta(hours=2)
        return min(standard, event_minus_buffer)

    @property
    def is_within_24h_of_event(self) -> bool:
        """
        True iff the event is happening in the NEXT 24 hours (still in the
        future). Used by templates for the 'cancellation not allowed' banner
        — we don't want that banner showing on past events where it would
        be misleading.

        Note: the model-level _check_within_24h_cancellation_block uses a
        looser check (≤24h regardless of direction) — that's intentional,
        because past events also shouldn't be cancellable.
        """
        delta = self.event_datetime() - timezone.now()
        return timedelta(0) <= delta <= timedelta(hours=24)

    @property
    def is_past_event(self) -> bool:
        """True iff the event time has already passed."""
        return self.event_datetime() < timezone.now()

    @property
    def can_dispute(self) -> bool:
        """
        True only when the client may still raise an issue:
          - Payment is currently held in escrow (paid, not yet released).
          - No prior dispute on this engagement.
          - Now is between event end and event end + 24h.
        """
        if self.payment_status != self.PAYMENT_PAID or self.disputed_at:
            return False
        now = timezone.now()
        event_end = self.event_datetime()
        return event_end <= now <= event_end + timedelta(
            hours=settings.RAZORPAY_DISPUTE_WINDOW_HOURS
        )

    def accept(self):
        """
        Performer accepts the request.

        Rules:
        - Must be pending.
        - Must be within 24h of creation (otherwise auto-expired).
        - 7) Only *one* accepted booking per performer per date.
              When accepting one, all other pending requests for that
              performer+date are cancelled.

        Also stamps accepted_at — that timestamp starts the client's
        payment window (see payment_deadline()).
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
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at"])

    def decline(self):
        """Performer declines."""
        self._ensure_pending()
        self.status = self.STATUS_DECLINED
        self.save(update_fields=["status"])

    def cancel_by_client(self, reason: str):
        """
        Client cancels a pending/accepted gig.
        Reason is now MANDATORY (we surface it to the performer). Cancelling
        within 24h of the event is BLOCKED entirely — no override. The
        Razorpay refund itself is triggered by the view layer if money is
        already in escrow.
        """
        if self.status not in [self.STATUS_PENDING, self.STATUS_ACCEPTED]:
            raise ValidationError("Only pending or accepted bookings can be cancelled.")
        if not reason or not reason.strip():
            raise ValidationError("A cancellation reason is required.")
        if len(reason) < 10:
            raise ValidationError("Cancellation reason must be at least 10 characters.")
        if len(reason) > 500:
            raise ValidationError("Cancellation reason must be under 500 characters.")
        self._check_within_24h_cancellation_block()
        self.cancellation_reason = reason
        self.cancelled_by = "client"
        self.status = self.STATUS_CANCELLED_CLIENT
        self.save(update_fields=["cancellation_reason", "cancelled_by", "status"])

    def cancel_by_performer(self, reason: str):
        """Symmetric to cancel_by_client — same rules, opposite party."""
        if self.status not in [self.STATUS_PENDING, self.STATUS_ACCEPTED]:
            raise ValidationError("Only pending or accepted bookings can be cancelled.")
        if not reason or not reason.strip():
            raise ValidationError("A cancellation reason is required.")
        if len(reason) < 10:
            raise ValidationError("Cancellation reason must be at least 10 characters.")
        if len(reason) > 500:
            raise ValidationError("Cancellation reason must be under 500 characters.")
        self._check_within_24h_cancellation_block()
        self.cancellation_reason = reason
        self.cancelled_by = "performer"
        self.status = self.STATUS_CANCELLED_PERFORMER
        self.save(update_fields=["cancellation_reason", "cancelled_by", "status"])


class Payment(models.Model):
    """
    Razorpay audit + reference store. One Engagement can spawn multiple
    Payment rows (failed attempts, retries) — the latest 'captured' row is
    the source of truth for the engagement's money.
    """
    engagement      = models.ForeignKey(
        Engagement, on_delete=models.CASCADE, related_name="payments",
    )
    amount          = models.PositiveIntegerField(help_text="Total in rupees")
    platform_fee    = models.PositiveIntegerField(default=0)
    performer_share = models.PositiveIntegerField(default=0)

    # Razorpay references — opaque IDs returned by Razorpay's API.
    razorpay_order_id    = models.CharField(max_length=64, unique=True)
    razorpay_payment_id  = models.CharField(max_length=64, blank=True, db_index=True)
    razorpay_transfer_id = models.CharField(max_length=64, blank=True)
    razorpay_refund_id   = models.CharField(max_length=64, blank=True)

    STATUS_CHOICES = [
        ("created",  "Order created"),
        ("captured", "Payment captured (in escrow)"),
        ("released", "Transferred to performer"),
        ("refunded", "Refunded to client"),
        ("failed",   "Failed"),
    ]
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="created", db_index=True,
    )

    # Append-only audit trail of webhook payloads we received for this payment.
    raw_webhook_log = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["engagement", "status"])]

    def __str__(self) -> str:
        return f"Payment #{self.pk} for Eng #{self.engagement_id} — ₹{self.amount} ({self.status})"
