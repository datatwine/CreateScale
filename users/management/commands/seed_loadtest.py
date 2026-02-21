"""
seed_loadtest — Prepare the database for Locust load testing.
==============================================================

PURPOSE
-------
This management command sets up 50 test users with the right flags and
pre-fetches auth tokens so Locust can bypass the slow password-hashing
login during the main load test.

WHAT IT DOES
------------
1.  Ensures test users loadtest_user_1 … loadtest_user_50 exist.
    (They were already created earlier; this is idempotent.)
2.  Users  1–25 → is_performer = True   (they can be hired)
3.  Users 26–50 → is_potential_client + client_approved = True (they can hire)
4.  Users 16–25 → BOTH flags (dual-role users for richer test behavior)
5.  Creates 2 placeholder uploads per performer (so the feed isn't empty).
6.  Fetches a DRF auth token for every user and writes them to
    /app/loadtest_tokens.json  (Locust reads this at startup).

RUN ON EC2
----------
    docker compose exec web python manage.py seed_loadtest
"""

import json
from io import BytesIO
from PIL import Image

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from users.models import Profile, Upload


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOTAL_USERS = 200
PASSWORD = "Passw0rd!AK2025"   # Same password set during earlier user creation
PERFORMER_RANGE = range(1, 81)       # users 1–80  (80 performers)
CLIENT_RANGE = range(81, 181)        # users 81–180 (100 clients)
DUAL_ROLE_RANGE = range(61, 81)      # users 61–80  (subset: both performer + client)
TOKEN_OUTPUT_PATH = "/app/loadtest_tokens.json"


def _make_tiny_image():
    """
    Generate a tiny 10×10 red PNG in memory.
    WHY: We need to give performers some uploads so the global feed and
         profile-detail endpoints return realistic payloads. A real photo
         would waste disk & memory — a 10×10 pixel image is enough to
         exercise the upload storage path without waste.
    """
    img = Image.new("RGB", (10, 10), color="red")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return InMemoryUploadedFile(
        file=buf,
        field_name="image",
        name="loadtest_sample.png",
        content_type="image/png",
        size=buf.getbuffer().nbytes,
        charset=None,
    )


class Command(BaseCommand):
    help = "Seed test users with performer/client flags and pre-fetch auth tokens for Locust."

    def handle(self, *args, **options):
        tokens = {}      # {username: token_key}
        performers = []   # user_ids of performers (for Locust to know who to hire)
        clients = []      # user_ids of approved clients

        for i in range(1, TOTAL_USERS + 1):
            username = f"loadtest_user_{i}"

            # --- Create or fetch user ---
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@loadtest.local"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
                self.stdout.write(f"  Created user {username}")

            # --- Ensure profile exists ---
            profile, _ = Profile.objects.get_or_create(user=user)

            # --- Set performer flags (users 1–25) ---
            if i in PERFORMER_RANGE:
                profile.is_performer = True
                profile.performer_blacklisted = False
                profile.profession = profile.profession or "Load Test Performer"
                profile.location = profile.location or "Test City"
                profile.bio = profile.bio or f"I am performer #{i}, ready for gigs."
                performers.append(user.id)

                # Create 2 sample uploads if this performer has none
                if Upload.objects.filter(profile=profile).count() == 0:
                    for j in range(2):
                        Upload.objects.create(
                            profile=profile,
                            image=_make_tiny_image(),
                            caption=f"Sample upload {j + 1} for {username}",
                        )
                    self.stdout.write(f"  Created 2 uploads for {username}")

            # --- Set client flags (users 26–50) ---
            if i in CLIENT_RANGE:
                profile.is_potential_client = True
                profile.client_approved = True
                profile.client_blacklisted = False
                clients.append(user.id)

            # --- Dual-role users (users 16–25) get BOTH flags ---
            if i in DUAL_ROLE_RANGE:
                profile.is_potential_client = True
                profile.client_approved = True
                profile.client_blacklisted = False
                if user.id not in clients:
                    clients.append(user.id)

            profile.save()

            # --- Get or create auth token ---
            token, _ = Token.objects.get_or_create(user=user)
            tokens[username] = token.key

        # --- Write tokens + role info to JSON ---
        output = {
            "tokens": tokens,
            "performer_user_ids": performers,
            "client_user_ids": clients,
        }
        with open(TOKEN_OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Seeded {TOTAL_USERS} users.\n"
            f"   Performers: {len(performers)} (users 1–80)\n"
            f"   Clients:    {len(clients)} (users 81–180, incl. dual-role 61–80)\n"
            f"   Tokens:     {TOKEN_OUTPUT_PATH}\n"
        ))
