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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
