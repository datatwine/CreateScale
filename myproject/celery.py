"""
Celery app bootstrap.

Loaded by myproject/__init__.py so Django's autodiscover_tasks() picks up
tasks.py modules in installed apps (e.g. users/tasks.py).

Broker + result backend share the existing Redis instance (also used as the
Django cache + session store + sorl-thumbnail KVStore). All Celery settings
live in settings.py under the CELERY_ namespace.
"""

import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Beat schedule — periodic tasks (run by the dedicated `beat` container).
# Keep these in code (not a separate scheduler config) so they're committed
# with the rest of the source.
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    # Hourly: cancel accepted-but-unpaid engagements past their payment
    # deadline. Frees up the performer's slot for that date.
    "expire-unpaid-engagements": {
        "task": "bookings.tasks.expire_unpaid_engagements",
        "schedule": crontab(minute=0),
    },
    # Hourly: auto-expire pending requests older than 24h that nobody
    # responded to. Keeps the performer's queue clean.
    "expire-stale-pending": {
        "task": "bookings.tasks.expire_stale_pending_engagements",
        "schedule": crontab(minute=0),
    },
    # Daily at 02:00 local: release held transfers for events that finished
    # >24h ago and weren't disputed. 02:00 keeps the cron well clear of
    # peak traffic.
    "release-completed-payouts": {
        "task": "bookings.tasks.release_completed_event_payouts",
        "schedule": crontab(hour=2, minute=0),
    },
}
