"""
Seed 20 high-quality showcase users for investor demos.

Nukes leftover load-test users, creates 20 curated profiles with real
avatar photos (randomuser.me), landscape covers (picsum.photos), and
colored-square gallery uploads. Seeds 15 engagement scenarios that
demonstrate the hiring algorithm (one-per-day, auto-cancel, decline, etc.).
Configures the superuser account as an approved client with a known password.

Run on production via AWS SSM:

    cd /home/ubuntu/AK-WEB
    docker compose -f docker-compose.web.yml exec -T web \
        python manage.py seed_showcase
"""

import random
from datetime import date, time, timedelta
from io import BytesIO

import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from PIL import Image
from rest_framework.authtoken.models import Token

from bookings.models import Engagement
from users.models import Profile, Upload

User = get_user_model()

PASSWORD = "ShowcasePass123!"

# ---------------------------------------------------------------------------
# 20 curated showcase users
# ---------------------------------------------------------------------------
SHOWCASE_USERS = [
    # --- 14 Performers ---
    {
        "name": "Aarav Mehta",
        "gender": "m",
        "prof": "Guitarist",
        "loc": "Mumbai",
        "fee": 8000,
        "role": "performer",
        "bio": "Session guitarist & live performer. Rock, blues, jazz. 200+ gigs across India. Available for events.",
    },
    {
        "name": "Priya Sharma",
        "gender": "f",
        "prof": "Bharatanatyam Dancer",
        "loc": "Chennai",
        "fee": 12000,
        "role": "performer",
        "bio": "Bharatanatyam dancer with 12 years of stage experience. Trained at Kalakshetra. Weddings & cultural fests.",
    },
    {
        "name": "Rohan Kapoor",
        "gender": "m",
        "prof": "DJ",
        "loc": "Delhi",
        "fee": 10000,
        "role": "performer",
        "bio": "Club DJ & wedding specialist. Bollywood, EDM & retro mixes. Own sound system available. Book early!",
    },
    {
        "name": "Ananya Nair",
        "gender": "f",
        "prof": "Vocalist",
        "loc": "Kochi",
        "fee": 7000,
        "role": "performer",
        "bio": "Carnatic vocalist & playback singer. 10 years trained. Weddings, temples, corporate shows, private concerts.",
    },
    {
        "name": "Kabir Malhotra",
        "gender": "m",
        "prof": "Stand-up Comedian",
        "loc": "Bangalore",
        "fee": 15000,
        "role": "performer",
        "bio": "Professional stand-up comedian. 5 years on the circuit. Corporate shows, open mics & college tours.",
    },
    {
        "name": "Meera Iyer",
        "gender": "f",
        "prof": "Kathak Dancer",
        "loc": "Jaipur",
        "fee": 9000,
        "role": "performer",
        "bio": "Jaipur gharana Kathak. 15 years of performance experience. Dance workshops & live shows across Rajasthan.",
    },
    {
        "name": "Arjun Reddy",
        "gender": "m",
        "prof": "Photographer",
        "loc": "Hyderabad",
        "fee": 6000,
        "role": "performer",
        "bio": "Event & concert photographer. Low-light specialist. 1000+ events captured. Fast delivery guaranteed.",
    },
    {
        "name": "Zara Khan",
        "gender": "f",
        "prof": "Muralist",
        "loc": "Mumbai",
        "fee": 11000,
        "role": "performer",
        "bio": "Large-scale muralist. Transformed 50+ walls across Mumbai. Commercial & residential projects.",
    },
    {
        "name": "Siddharth Patel",
        "gender": "m",
        "prof": "Tabla Player",
        "loc": "Ahmedabad",
        "fee": 5000,
        "role": "performer",
        "bio": "Classical tabla artist. Accompanist for concerts & recordings. 8 years with leading Hindustani musicians.",
    },
    {
        "name": "Ishita Das",
        "gender": "f",
        "prof": "Mehendi Artist",
        "loc": "Kolkata",
        "fee": 4000,
        "role": "performer",
        "bio": "Bridal mehendi specialist. Arabic, Indian & Indo-fusion styles. 500+ brides served. Natural henna only.",
    },
    {
        "name": "Vikram Joshi",
        "gender": "m",
        "prof": "Emcee",
        "loc": "Pune",
        "fee": 8500,
        "role": "performer",
        "bio": "High-energy emcee & entertainer. Weddings, sangeets, receptions. Trilingual: Hindi, English, Marathi.",
    },
    {
        "name": "Neha Gupta",
        "gender": "f",
        "prof": "Flautist",
        "loc": "Lucknow",
        "fee": 6500,
        "role": "performer",
        "bio": "Bamboo flute artist. Carnatic & Hindustani styles. Perfect for intimate events, weddings & meditation.",
    },
    {
        "name": "Dev Saxena",
        "gender": "m",
        "prof": "Magician",
        "loc": "Chandigarh",
        "fee": 7500,
        "role": "performer",
        "bio": "Close-up & stage magician. 12 years of wonder. Birthday parties, corporate shows & TV appearances.",
    },
    {
        "name": "Kavya Menon",
        "gender": "f",
        "prof": "Painter",
        "loc": "Mysore",
        "fee": 5500,
        "role": "performer",
        "bio": "Oil & watercolor artist. Commissioned portraits, murals, live painting at events. Gallery exhibitions.",
    },
    # --- 4 Pure Clients ---
    {
        "name": "Rajiv Kapoor",
        "gender": "m",
        "prof": "",
        "loc": "Delhi",
        "fee": None,
        "role": "client",
        "bio": "Corporate event manager. Always looking for fresh talent to book for product launches & galas.",
    },
    {
        "name": "Sunita Deshmukh",
        "gender": "f",
        "prof": "",
        "loc": "Pune",
        "fee": None,
        "role": "client",
        "bio": "Wedding planner based in Pune. Curating the best performers for destination weddings across India.",
    },
    {
        "name": "Amit Choudhury",
        "gender": "m",
        "prof": "",
        "loc": "Kolkata",
        "fee": None,
        "role": "client",
        "bio": "Art gallery curator & cultural events organizer. Hosting exhibitions, concerts & literary festivals.",
    },
    {
        "name": "Deepika Nambiar",
        "gender": "f",
        "prof": "",
        "loc": "Bangalore",
        "fee": None,
        "role": "client",
        "bio": "Cultural festival organizer in Bangalore. Connecting artists with audiences at large-scale public events.",
    },
    # --- 2 Dual-role (performer + client) ---
    {
        "name": "Farhan Ali",
        "gender": "m",
        "prof": "DJ",
        "loc": "Goa",
        "fee": 9500,
        "role": "dual",
        "bio": "Techno & house DJ. Underground scene veteran. Also hire performers for my own beach festival events.",
    },
    {
        "name": "Simran Kaur",
        "gender": "f",
        "prof": "Event Host",
        "loc": "Chandigarh",
        "fee": 7000,
        "role": "dual",
        "bio": "Professional anchor & moderator. I also organize college fests and need great performers every season.",
    },
]

VENUES = [
    "The Jazz Lounge",
    "Blue Note Club",
    "Grand Ballroom",
    "City Park Amphitheater",
    "Sunset Terrace",
    "Hotel Majestic",
    "Convention Center Hall A",
    "Rooftop Garden Bar",
    "Beach Resort Stage",
    "Heritage Palace Courtyard",
    "The Art Gallery",
    "Community Hall",
]

OCCASIONS = [
    "Birthday Party",
    "Corporate Event",
    "Wedding Reception",
    "Private Dinner",
    "Club Night",
    "Festival",
    "College Fest",
    "Product Launch",
    "Charity Gala",
    "House Party",
    "New Year Eve Party",
    "Anniversary Celebration",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _download_image(url, timeout=10):
    """Download an image from a URL. Returns bytes or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def _make_colored_square(width=400, height=400):
    """Generate a random colored JPEG in memory. Fallback for network errors."""
    img = Image.new(
        "RGB",
        (width, height),
        color=(
            random.randint(30, 220),
            random.randint(30, 220),
            random.randint(30, 220),
        ),
    )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _get_avatar(gender, index):
    """Download a face photo from randomuser.me, fallback to colored square."""
    folder = "men" if gender == "m" else "women"
    url = f"https://randomuser.me/api/portraits/{folder}/{index % 100}.jpg"
    data = _download_image(url)
    if data:
        return data
    return _make_colored_square(512, 512)


def _get_cover(seed):
    """Download a landscape photo from picsum.photos, fallback to colored rect."""
    url = f"https://picsum.photos/1920/600?random={seed}"
    data = _download_image(url)
    if data:
        return data
    return _make_colored_square(1920, 600)


def _random_time():
    """Random time between 10:00 and 21:00, 15-min intervals."""
    hour = random.randint(10, 20)
    minute = random.choice([0, 15, 30, 45])
    return time(hour, minute)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Seed 20 showcase users + engagement scenarios for investor demos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-username",
            type=str,
            default="",
            help="Superuser username to configure as client. "
            "If empty, auto-detects the first superuser.",
        )
        parser.add_argument(
            "--skip-cleanup",
            action="store_true",
            help="Skip nuking old load-test users (useful for re-runs).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would happen without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n========================================\n"
                "  Showcase Seeder for Investor Demo\n"
                "========================================\n"
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("  *** DRY RUN — no changes ***\n"))

        # Phase 0: Nuke old load-test users
        if not options["skip_cleanup"]:
            self._nuke_old_users(dry_run)
        else:
            self.stdout.write("  Skipping cleanup (--skip-cleanup)\n")

        # Phase 1: Create 20 showcase users
        user_map = self._create_showcase_users(dry_run)

        # Phase 2: Configure admin account
        admin_user = self._configure_admin(options["admin_username"], dry_run)

        # Phase 3: Seed engagements
        if not dry_run:
            self._seed_engagements(user_map, admin_user)

        self.stdout.write(
            self.style.SUCCESS(
                "\n========================================\n"
                "  SEED SHOWCASE COMPLETE\n"
                "========================================\n"
            )
        )

    # ------------------------------------------------------------------
    # Phase 0
    # ------------------------------------------------------------------

    def _nuke_old_users(self, dry_run):
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Phase 0: Nuke old load-test users ---")
        )

        old_users = User.objects.filter(
            Q(username__startswith="loadtest_user_")
            | Q(username__startswith="lt2_user_")
            | Q(username__startswith="demo_")
        )
        count = old_users.count()

        if count == 0:
            self.stdout.write("  No old load-test users found. Nothing to nuke.")
            return

        self.stdout.write(f"  Found {count} old users to delete.")

        if dry_run:
            self.stdout.write(
                f"  [DRY RUN] Would delete {count} users + their storage files."
            )
            return

        # Clean up storage files BEFORE cascade-deleting the DB rows
        storage_deleted = 0
        for user in old_users.iterator():
            profile = getattr(user, "profile", None)
            if not profile:
                continue

            # Gallery uploads
            for upload in Upload.objects.filter(profile=profile):
                if upload.image and upload.image.name:
                    try:
                        default_storage.delete(upload.image.name)
                        storage_deleted += 1
                    except Exception:
                        pass
                if upload.video and upload.video.name:
                    try:
                        default_storage.delete(upload.video.name)
                        storage_deleted += 1
                    except Exception:
                        pass

            # Profile images
            if profile.profile_picture and profile.profile_picture.name:
                try:
                    default_storage.delete(profile.profile_picture.name)
                    storage_deleted += 1
                except Exception:
                    pass
            if profile.cover_photo and profile.cover_photo.name:
                try:
                    default_storage.delete(profile.cover_photo.name)
                    storage_deleted += 1
                except Exception:
                    pass

        # Now cascade-delete the users (Profile, Upload, Engagement, Token rows)
        deleted_count, _ = old_users.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"  Nuked {deleted_count} DB objects, "
                f"{storage_deleted} storage files deleted."
            )
        )

    # ------------------------------------------------------------------
    # Phase 1
    # ------------------------------------------------------------------

    def _create_showcase_users(self, dry_run):
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Phase 1: Create 20 showcase users ---")
        )

        if dry_run:
            for d in SHOWCASE_USERS:
                safe = d["name"].lower().replace(" ", "_")
                self.stdout.write(
                    f"  [DRY RUN] Would create demo_{safe} — {d['prof'] or d['role']}"
                )
            return {}

        user_map = {}  # username → User object

        for idx, d in enumerate(SHOWCASE_USERS):
            safe_name = d["name"].lower().replace(" ", "_")
            username = f"demo_{safe_name}"
            parts = d["name"].split()
            first_name = parts[0]
            last_name = " ".join(parts[1:])

            self.stdout.write(
                f"  [{idx + 1}/20] {username} — {d['prof'] or d['role']}..."
            )

            # Create user
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{safe_name}@createscale.demo",
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()

            # Download images
            self.stdout.write("       Downloading avatar...")
            avatar_bytes = _get_avatar(d["gender"], idx)
            self.stdout.write("       Downloading cover...")
            cover_bytes = _get_cover(idx + 100)

            # Configure profile
            profile, _ = Profile.objects.get_or_create(user=user)

            if d["role"] in ("performer", "dual"):
                profile.is_performer = True
                profile.performer_blacklisted = False
                profile.performer_fee = d["fee"]
                profile.profession = d["prof"]

            if d["role"] in ("client", "dual"):
                profile.is_potential_client = True
                profile.client_approved = True
                profile.client_blacklisted = False

            profile.location = d["loc"]
            profile.bio = d["bio"][:140]

            # Assign images (Profile.save() auto-compresses via process_image)
            profile.profile_picture = ContentFile(
                avatar_bytes, name=f"{username}_avatar.jpg"
            )
            profile.cover_photo = ContentFile(cover_bytes, name=f"{username}_cover.jpg")
            profile.save()

            # Gallery uploads (3-5 colored squares per performer)
            if d["role"] in ("performer", "dual"):
                existing = Upload.objects.filter(profile=profile).count()
                target = random.randint(3, 5)
                for j in range(existing, target):
                    img_bytes = _make_colored_square(1080, 1080)
                    Upload.objects.create(
                        profile=profile,
                        image=ContentFile(
                            img_bytes,
                            name=f"{username}_gallery_{j + 1}.jpg",
                        ),
                        caption=f"{d['prof']} portfolio piece {j + 1}",
                    )

            # Auth token
            Token.objects.get_or_create(user=user)

            user_map[username] = user

        performers = [
            u
            for d, u in zip(SHOWCASE_USERS, user_map.values())
            if d["role"] in ("performer", "dual")
        ]
        clients = [
            u
            for d, u in zip(SHOWCASE_USERS, user_map.values())
            if d["role"] in ("client", "dual")
        ]

        self.stdout.write(
            self.style.SUCCESS(
                f"  20 showcase users created "
                f"({len(performers)} performers, {len(clients)} clients)"
            )
        )
        return user_map

    # ------------------------------------------------------------------
    # Phase 2
    # ------------------------------------------------------------------

    def _configure_admin(self, admin_username, dry_run):
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Phase 2: Configure admin account ---")
        )

        if admin_username:
            admin_user = User.objects.filter(username=admin_username).first()
        else:
            admin_user = User.objects.filter(is_superuser=True).first()

        if not admin_user:
            self.stdout.write(
                self.style.WARNING(
                    "  No superuser found! Skipping admin configuration.\n"
                    "  Create one with: python manage.py createsuperuser"
                )
            )
            return None

        self.stdout.write(f"  Found admin: {admin_user.username}")

        if dry_run:
            self.stdout.write(
                "  [DRY RUN] Would reset password and set client_approved=True"
            )
            return admin_user

        # Reset password
        admin_user.set_password(PASSWORD)
        admin_user.save()

        # Configure as approved client
        profile, _ = Profile.objects.get_or_create(user=admin_user)
        profile.is_potential_client = True
        profile.client_approved = True
        profile.client_blacklisted = False
        profile.save(
            update_fields=[
                "is_potential_client",
                "client_approved",
                "client_blacklisted",
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Admin username:  {admin_user.username}\n"
                f"  Password reset:  {PASSWORD}\n"
                f"  client_approved: True"
            )
        )
        return admin_user

    # ------------------------------------------------------------------
    # Phase 3
    # ------------------------------------------------------------------

    def _seed_engagements(self, user_map, admin_user):
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Phase 3: Seed engagement scenarios ---")
        )

        if not user_map:
            self.stdout.write(
                self.style.WARNING("  No showcase users found. Skipping engagements.")
            )
            return

        # Helper to look up a user by short key
        def u(short_name):
            """Look up user by last part of username, e.g. 'rohan_kapoor'."""
            key = f"demo_{short_name}"
            return user_map.get(key)

        base = date.today()
        created = 0

        # Each scenario is a list of (client, performer_key, day_offset, status, extras)
        scenarios = []

        # --- Scenario A: Admin's hiring dashboard ---
        if admin_user:
            scenarios.extend(
                [
                    (
                        admin_user,
                        "priya_sharma",
                        25,
                        Engagement.STATUS_ACCEPTED,
                        {"accepted_at": timezone.now()},
                    ),
                    (admin_user, "aarav_mehta", 30, Engagement.STATUS_PENDING, {}),
                    (admin_user, "kabir_malhotra", 35, Engagement.STATUS_DECLINED, {}),
                ]
            )

        # --- Scenario B: One-per-day auto-cancel (Rohan Kapoor, day +28) ---
        scenarios.extend(
            [
                (
                    u("rajiv_kapoor"),
                    "rohan_kapoor",
                    28,
                    Engagement.STATUS_ACCEPTED,
                    {"accepted_at": timezone.now()},
                ),
                (
                    u("sunita_deshmukh"),
                    "rohan_kapoor",
                    28,
                    Engagement.STATUS_CANCELLED_PERFORMER,
                    {},
                ),
                (
                    u("amit_choudhury"),
                    "rohan_kapoor",
                    28,
                    Engagement.STATUS_CANCELLED_PERFORMER,
                    {},
                ),
            ]
        )

        # --- Scenario C: Performer declines ---
        scenarios.extend(
            [
                (
                    u("deepika_nambiar"),
                    "meera_iyer",
                    32,
                    Engagement.STATUS_DECLINED,
                    {},
                ),
                (u("rajiv_kapoor"), "ananya_nair", 40, Engagement.STATUS_DECLINED, {}),
            ]
        )

        # --- Scenario D: Client's pending queue (Sunita) ---
        scenarios.extend(
            [
                (
                    u("sunita_deshmukh"),
                    "siddharth_patel",
                    35,
                    Engagement.STATUS_PENDING,
                    {},
                ),
                (u("sunita_deshmukh"), "neha_gupta", 38, Engagement.STATUS_PENDING, {}),
                (
                    u("sunita_deshmukh"),
                    "vikram_joshi",
                    42,
                    Engagement.STATUS_PENDING,
                    {},
                ),
            ]
        )

        # --- Scenario E: Client cancellation ---
        scenarios.extend(
            [
                (
                    u("amit_choudhury"),
                    "zara_khan",
                    45,
                    Engagement.STATUS_CANCELLED_CLIENT,
                    {
                        "cancellation_reason": "Event venue changed, need to reschedule",
                        "cancelled_by": "client",
                    },
                ),
            ]
        )

        # --- Scenario F: Healthy accepted bookings ---
        scenarios.extend(
            [
                (
                    u("deepika_nambiar"),
                    "farhan_ali",
                    33,
                    Engagement.STATUS_ACCEPTED,
                    {"accepted_at": timezone.now()},
                ),
                (
                    u("rajiv_kapoor"),
                    "dev_saxena",
                    50,
                    Engagement.STATUS_ACCEPTED,
                    {"accepted_at": timezone.now()},
                ),
                (
                    u("sunita_deshmukh"),
                    "kavya_menon",
                    55,
                    Engagement.STATUS_ACCEPTED,
                    {"accepted_at": timezone.now()},
                ),
            ]
        )

        for client, perf_key, day_offset, target_status, extras in scenarios:
            performer = u(perf_key)
            if not client or not performer:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipping engagement: client or performer not found "
                        f"(perf_key={perf_key})"
                    )
                )
                continue

            event_date = base + timedelta(days=day_offset)
            perf_profile = getattr(performer, "profile", None)
            fee = perf_profile.performer_fee if perf_profile else None

            try:
                eng = Engagement(
                    client=client,
                    performer=performer,
                    date=event_date,
                    time=_random_time(),
                    venue=random.choice(VENUES),
                    occasion=random.choice(OCCASIONS),
                    status=Engagement.STATUS_PENDING,
                    fee=fee,
                )
                eng.save()  # Saves as pending, passes clean()

                # Update to target status via ORM (bypasses state machine)
                if target_status != Engagement.STATUS_PENDING:
                    updates = {"status": target_status}
                    updates.update(extras)
                    Engagement.objects.filter(pk=eng.pk).update(**updates)

                status_display = target_status.replace("_", " ").title()
                self.stdout.write(
                    f"  {client.username} -> {performer.username} "
                    f"(day +{day_offset}) [{status_display}]"
                )
                created += 1
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Failed: {client.username} -> {performer.username}: {exc}"
                    )
                )

        # Summary by status
        status_counts = {}
        for _, _, _, status, _ in scenarios:
            label = status.replace("_", " ").title()
            status_counts[label] = status_counts.get(label, 0) + 1

        breakdown = ", ".join(f"{v} {k}" for k, v in status_counts.items())
        self.stdout.write(
            self.style.SUCCESS(f"  {created} engagements seeded ({breakdown})")
        )
