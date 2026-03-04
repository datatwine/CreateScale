"""
seed_loadtest_v2 — Prepare the database for Load Test V2 (2,000 users).
======================================================================

PURPOSE
-------
Seeds 2,000 load test users with realistic data and 50 demo/showcase users
that survive post-test cleanup. Designed to create enough DB working-set
diversity that Postgres can't cache everything in shared_buffers.

WHAT IT CREATES
---------------
1. 2,000 load test users (prefix: lt2_user_)
   - Users   1–800  → Performers (varied professions, 3–10 uploads each)
   - Users 601–800  → Dual-role (both performer + client)
   - Users 801–1700 → Clients (approved)
   - Users 1701–1800 → Scrollers (no flags, browse only)
   - Users 1801–2000 → Login pool (exclusive, for login testing)
2. 50 demo/showcase users (prefix: demo_)
   - Real-sounding names, rich bios, AI-generated portfolio images
   - Pre-seeded bookings between them
3. 500 pre-seeded Engagement records across load test users
4. Auth tokens for all users → /app/loadtest_tokens_v2.json

RUN ON EC2
----------
    # Upload demo images first:
    scp -r demo_images/ ubuntu@<EC2>:~/AK/demo_images
    scp -r test_images/ ubuntu@<EC2>:~/AK/test_images

    docker compose exec web python manage.py seed_loadtest_v2
"""

import json
import os
import random
from datetime import date, timedelta, time
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token

from users.models import Profile, Upload
from bookings.models import Engagement


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TOTAL_LOADTEST_USERS = 2000
TOTAL_DEMO_USERS = 50
PASSWORD = "Passw0rd!AK2025v2"

# Load test user ranges
PERFORMER_RANGE = range(1, 801)          # 800 performers
DUAL_ROLE_RANGE = range(601, 801)        # 200 dual-role (subset of performers)
CLIENT_RANGE = range(801, 1701)          # 900 clients
SCROLLER_RANGE = range(1701, 1801)       # 100 scrollers
LOGIN_RANGE = range(1801, 2001)          # 200 login-only

TOKEN_OUTPUT_PATH = "/app/loadtest_tokens_v2.json"

# Paths to pre-made images (uploaded via SCP before running this command)
TEST_IMAGES_DIR = "/app/test_images"
DEMO_IMAGES_DIR = "/app/demo_images"

# ---------------------------------------------------------------------------
# Realistic data pools
# ---------------------------------------------------------------------------
PROFESSIONS = [
    "Classical Dancer", "Contemporary Dancer", "Hip-Hop Dancer",
    "Bharatanatyam Dancer", "Kathak Dancer", "Salsa Dancer",
    "Vocalist", "Guitarist", "Pianist", "Drummer", "DJ",
    "Violinist", "Flautist", "Tabla Player", "Sitar Player",
    "Stand-up Comedian", "Emcee", "Event Host",
    "Painter", "Sketch Artist", "Muralist", "Digital Artist",
    "Photographer", "Videographer", "Photo Editor",
    "Mehendi Artist", "Rangoli Artist", "Calligrapher",
    "Magician", "Puppeteer", "Mime Artist",
    "Singer-Songwriter", "Band (Full)", "Acoustic Duo",
]

LOCATIONS = [
    "Bangalore", "Mysore", "Mumbai", "Delhi", "Hyderabad",
    "Chennai", "Pune", "Kolkata", "Jaipur", "Ahmedabad",
    "Goa", "Kochi", "Lucknow", "Chandigarh", "Bhopal",
]

BIO_TEMPLATES = [
    "Professional {prof} with {years} years of experience. Available for events across {loc}.",
    "{prof} | Performer | Booking open for weddings, corporate shows & private events.",
    "Passionate {prof} based in {loc}. Let's create magic at your next event! 🎭",
    "{years}+ years as a {prof}. Specializing in live performances & cultural events.",
    "Experienced {prof} available in {loc} & nearby cities. DM for bookings.",
    "Award-winning {prof}. Performed at 200+ events. Available pan-India.",
    "{prof} and creative artist. Bringing art to life, one stage at a time.",
    "Full-time {prof} | Part-time dreamer. Based in {loc}. Book me for your event!",
]

VENUES = [
    "The Jazz Lounge", "Blue Note Club", "Grand Ballroom",
    "City Park Amphitheater", "Sunset Terrace", "Hotel Majestic",
    "Convention Center Hall A", "Rooftop Garden Bar", "Beach Resort Stage",
    "Heritage Palace Courtyard", "The Art Gallery", "Community Hall",
]

OCCASIONS = [
    "Birthday Party", "Corporate Event", "Wedding Reception",
    "Private Dinner", "Club Night", "Festival", "College Fest",
    "Product Launch", "Charity Gala", "House Party",
    "New Year Eve Party", "Anniversary Celebration",
]

# ---------------------------------------------------------------------------
# Demo user definitions (50 curated users)
# ---------------------------------------------------------------------------
DEMO_USERS = [
    # Classical Dancers (8)
    {"name": "Meera Krishnan", "prof": "Bharatanatyam Dancer", "loc": "Chennai",
     "bio": "Bharatanatyam dancer with 12 years of stage experience. Trained at Kalakshetra. Available for weddings & cultural fests."},
    {"name": "Anjali Nair", "prof": "Kathak Dancer", "loc": "Delhi",
     "bio": "Kathak performer & choreographer. Trained under Pandit Birju Maharaj's lineage. Solo & group performances available."},
    {"name": "Priya Menon", "prof": "Classical Dancer", "loc": "Kochi",
     "bio": "Mohiniyattam & Bharatanatyam. 8 years on stage. Performed at national festivals. Book me for cultural events."},
    {"name": "Kavitha Rao", "prof": "Bharatanatyam Dancer", "loc": "Bangalore",
     "bio": "Classical dancer specializing in Bharatanatyam & contemporary fusion. Corporate shows, weddings, private events."},
    {"name": "Nandini Sharma", "prof": "Kathak Dancer", "loc": "Jaipur",
     "bio": "Jaipur gharana Kathak. 15 years of performance experience. Dance workshops & live shows across Rajasthan."},
    {"name": "Riya Iyer", "prof": "Contemporary Dancer", "loc": "Mumbai",
     "bio": "Contemporary & jazz fusion dancer. Bollywood background dancer turned solo artist. Available pan-India."},
    {"name": "Lakshmi Sundaram", "prof": "Classical Dancer", "loc": "Mysore",
     "bio": "Mysore-style Bharatanatyam. Performed at Dasara festival 5 times. Temple festivals & cultural programs."},
    {"name": "Tara Bhatt", "prof": "Hip-Hop Dancer", "loc": "Pune",
     "bio": "B-girl & hip-hop choreographer. Dance battles, college fests, brand events. Energy guaranteed! 🔥"},

    # Musicians (8)
    {"name": "Rohan Sharma", "prof": "Guitarist", "loc": "Bangalore",
     "bio": "Session guitarist & live performer. Rock, blues, jazz. 200+ gigs across India. Available for events & studio work."},
    {"name": "Kavya Iyer", "prof": "Vocalist", "loc": "Chennai",
     "bio": "Carnatic vocalist & playback singer. Trained for 10 years. Weddings, temples, corporate shows, private concerts."},
    {"name": "Arjun Mehta", "prof": "DJ", "loc": "Mumbai",
     "bio": "DJ & electronic music producer. Resident at top Mumbai clubs. Available for parties, weddings & brand events."},
    {"name": "Siddharth Patel", "prof": "Tabla Player", "loc": "Ahmedabad",
     "bio": "Classical tabla artist. Accompanist for concerts & recordings. 8 years with leading Hindustani musicians."},
    {"name": "Aditi Kulkarni", "prof": "Pianist", "loc": "Pune",
     "bio": "Classical & jazz pianist. Piano accompaniment for events. Teaching & performing since 2015. 🎹"},
    {"name": "Dev Saxena", "prof": "Drummer", "loc": "Delhi",
     "bio": "Professional drummer. Rock, funk, Bollywood. Touring band experience. Available for live shows & sessions."},
    {"name": "Sneha Reddy", "prof": "Flautist", "loc": "Hyderabad",
     "bio": "Bamboo flute artist. Carnatic & Hindustani styles. Perfect for intimate events, weddings & meditation sessions."},
    {"name": "Vikram Joshi", "prof": "Singer-Songwriter", "loc": "Goa",
     "bio": "Indie singer-songwriter. Acoustic sets, cafe gigs, private events. Hindi & English originals + covers. 🎵"},

    # Painters / Visual Artists (8)
    {"name": "Priya Deshmukh", "prof": "Painter", "loc": "Pune",
     "bio": "Oil & watercolor artist. Commissioned portraits, murals, live painting at events. Gallery exhibitions across India."},
    {"name": "Arjun Reddy", "prof": "Digital Artist", "loc": "Hyderabad",
     "bio": "Digital illustrator & concept artist. Event caricatures, live digital art, brand illustrations. Tech meets art."},
    {"name": "Zara Khan", "prof": "Muralist", "loc": "Mumbai",
     "bio": "Large-scale muralist. Transformed 50+ walls across Mumbai. Available for commercial & residential projects."},
    {"name": "Ananya Das", "prof": "Sketch Artist", "loc": "Kolkata",
     "bio": "Charcoal & pencil sketch artist. Live event sketching, commissioned portraits. 300+ happy clients."},
    {"name": "Rahul Verma", "prof": "Painter", "loc": "Jaipur",
     "bio": "Miniature painting specialist. Rajasthani & Mughal styles. Workshops, exhibitions & commissioned work."},
    {"name": "Ishita Ghosh", "prof": "Digital Artist", "loc": "Bangalore",
     "bio": "UI designer by day, digital artist by passion. NFTs, prints & live digital painting at tech events."},
    {"name": "Karthik Nair", "prof": "Muralist", "loc": "Kochi",
     "bio": "Street art & mural artist. Public art installations, cafe murals, festival art. Color is my language. 🎨"},
    {"name": "Divya Rajan", "prof": "Painter", "loc": "Chennai",
     "bio": "Tanjore painting & contemporary art. Gold leaf specialist. Custom pieces for homes, offices & temples."},

    # Photographers (6)
    {"name": "Dev Mehra", "prof": "Photographer", "loc": "Mumbai",
     "bio": "Wedding & portrait photographer. 10 years, 500+ weddings shot. Candid, fine art & documentary styles."},
    {"name": "Nandini Chakraborty", "prof": "Photographer", "loc": "Kolkata",
     "bio": "Street & documentary photographer. Published in national magazines. Available for events & editorial shoots."},
    {"name": "Sameer Gupta", "prof": "Videographer", "loc": "Delhi",
     "bio": "Cinematic wedding films & event videos. Drone + gimbal specialist. Editing included. Pan-India available."},
    {"name": "Pooja Kapoor", "prof": "Photographer", "loc": "Chandigarh",
     "bio": "Fashion & product photographer. Studio & outdoor shoots. E-commerce, lookbooks & social media content."},
    {"name": "Aakash Singh", "prof": "Photographer", "loc": "Bangalore",
     "bio": "Event & concert photographer. Low-light specialist. 1000+ events captured. Fast delivery guaranteed."},
    {"name": "Rhea Fernandes", "prof": "Videographer", "loc": "Goa",
     "bio": "Travel & lifestyle videographer. Short films, reels & brand content. Telling stories through the lens. 📸"},

    # Stand-up / Spoken Word (5)
    {"name": "Kabir Malhotra", "prof": "Stand-up Comedian", "loc": "Mumbai",
     "bio": "Professional stand-up comedian. 5 years on the circuit. Corporate shows, open mics & college tours. Clean humor."},
    {"name": "Aisha Siddiqui", "prof": "Emcee", "loc": "Bangalore",
     "bio": "Bilingual emcee & event host. Weddings, award nights, corporate events. Keeping your audience engaged! 🎤"},
    {"name": "Nikhil Rane", "prof": "Stand-up Comedian", "loc": "Pune",
     "bio": "Observational comedy. Featured in comedy specials. Available for private shows & brand collaborations."},
    {"name": "Swati Mishra", "prof": "Event Host", "loc": "Delhi",
     "bio": "Professional anchor & moderator. Panel discussions, product launches, galas. Hindi, English & Marathi."},
    {"name": "Ravi Teja", "prof": "Stand-up Comedian", "loc": "Hyderabad",
     "bio": "Telugu & English comedy. Corporate shows, college fests. Making South India laugh, one city at a time. 😂"},

    # Mehendi / Folk Art (5)
    {"name": "Pooja Verma", "prof": "Mehendi Artist", "loc": "Jaipur",
     "bio": "Bridal mehendi specialist. Arabic, Indian & Indo-fusion styles. 1000+ brides served. Advance booking only."},
    {"name": "Fatima Sheikh", "prof": "Mehendi Artist", "loc": "Lucknow",
     "bio": "Intricate Lucknowi mehendi designs. Bridal, festive & corporate events. Natural henna only. ✋"},
    {"name": "Savita Kumari", "prof": "Rangoli Artist", "loc": "Pune",
     "bio": "Traditional & modern rangoli. Diwali, weddings, corporate lobbies. Large installations a specialty."},
    {"name": "Geeta Devi", "prof": "Calligrapher", "loc": "Ahmedabad",
     "bio": "Hindi & Urdu calligraphy. Wedding cards, wall art, live calligraphy at events. Ink meets tradition."},
    {"name": "Meenakshi Pillai", "prof": "Rangoli Artist", "loc": "Mysore",
     "bio": "Mysore-style rangoli & kolam expert. Temple festivals, government events & cultural programs."},

    # DJs / Event MCs (5)
    {"name": "Kabir Singh", "prof": "DJ", "loc": "Delhi",
     "bio": "Club DJ & wedding specialist. Bollywood, EDM & retro mixes. Own sound system available. Book early! 🎧"},
    {"name": "Radhika Menon", "prof": "Emcee", "loc": "Bangalore",
     "bio": "Corporate emcee & team-building facilitator. Product launches, hackathons & award ceremonies. Energy+!"},
    {"name": "Farhan Ali", "prof": "DJ", "loc": "Mumbai",
     "bio": "Techno & house DJ. Underground scene veteran. Available for festivals, clubs & private parties."},
    {"name": "Deepa Nambiar", "prof": "Event Host", "loc": "Kochi",
     "bio": "Multilingual event host. Malayalam, English & Hindi. Weddings, cultural events & TV shows. Warm & fun."},
    {"name": "Rajesh Kumar", "prof": "DJ", "loc": "Chennai",
     "bio": "Tamil party DJ & karaoke host. College fests, house parties, sangeets. Bringing the beat since 2018. 🎶"},

    # Mixed / Versatile (5)
    {"name": "Arun Pillai", "prof": "Magician", "loc": "Kochi",
     "bio": "Close-up & stage magician. 12 years of wonder. Birthday parties, corporate shows & TV appearances. ✨"},
    {"name": "Simran Kaur", "prof": "Mime Artist", "loc": "Chandigarh",
     "bio": "Professional mime & physical theater artist. Street performances, corporate events & art festivals."},
    {"name": "Varun Khanna", "prof": "Emcee", "loc": "Delhi",
     "bio": "High-energy emcee & entertainer. Weddings, sangeets, receptions. Trilingual: Hindi, English, Punjabi."},
    {"name": "Neha Banerjee", "prof": "Vocalist", "loc": "Kolkata",
     "bio": "Rabindra Sangeet & modern Bengali vocalist. Intimate concerts, cultural events & studio recordings."},
    {"name": "Manish Agarwal", "prof": "Acoustic Duo", "loc": "Jaipur",
     "bio": "Guitar-vocal acoustic duo. Cafe gigs, house concerts, sundowner sets. Bollywood + international covers."},
]


def _load_test_images(directory):
    """Load JPEG files from a directory. Returns list of (filename, bytes)."""
    images = []
    img_dir = Path(directory)
    if img_dir.exists():
        for f in sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.jpeg")):
            images.append((f.name, f.read_bytes()))
    if not images:
        # Fallback: generate a 400x400 colored JPEG in memory (~20KB)
        try:
            from PIL import Image
            for i in range(10):
                img = Image.new("RGB", (400, 400), color=(
                    random.randint(30, 220),
                    random.randint(30, 220),
                    random.randint(30, 220),
                ))
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=85)
                images.append((f"fallback_{i}.jpg", buf.getvalue()))
        except ImportError:
            pass
    return images


def _make_upload(profile, image_data, caption):
    """Create an Upload record from raw image bytes."""
    filename, img_bytes = image_data
    Upload.objects.create(
        profile=profile,
        image=ContentFile(img_bytes, name=filename),
        caption=caption,
    )


def _random_future_date():
    """Random date 7–60 days from now."""
    return date.today() + timedelta(days=random.randint(7, 60))


def _random_time():
    """Random time between 10:00 and 21:00."""
    hour = random.randint(10, 20)
    minute = random.choice([0, 15, 30, 45])
    return time(hour, minute)


class Command(BaseCommand):
    help = "Seed 2,000 load test users + 50 demo users for Load Test V2."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=TOTAL_LOADTEST_USERS)
        parser.add_argument("--demo", type=int, default=TOTAL_DEMO_USERS)
        parser.add_argument("--skip-bookings", action="store_true",
                            help="Skip pre-seeding engagements (faster for testing)")

    def handle(self, *args, **options):
        total_users = options["users"]
        total_demo = options["demo"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Load Test V2 Seeder ===\n"
            f"Load test users: {total_users}  |  Demo users: {total_demo}\n"
        ))

        # Load images
        test_images = _load_test_images(TEST_IMAGES_DIR)
        demo_images = _load_test_images(DEMO_IMAGES_DIR)
        self.stdout.write(f"  Test images loaded: {len(test_images)}")
        self.stdout.write(f"  Demo images loaded: {len(demo_images)}")

        if not test_images:
            self.stdout.write(self.style.WARNING(
                "  ⚠️ No test images found! Uploads will use fallback colored squares."
            ))

        # --- Phase 1: Load test users ---
        tokens = {}
        performers = []
        clients = []

        for i in range(1, total_users + 1):
            username = f"lt2_user_{i}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@loadtest.local"},
            )
            if created:
                user.set_password(PASSWORD)
                user.save()

            profile, _ = Profile.objects.get_or_create(user=user)

            # Performer setup (1–800)
            if i in PERFORMER_RANGE:
                prof = random.choice(PROFESSIONS)
                loc = random.choice(LOCATIONS)
                years = random.randint(2, 15)
                bio = random.choice(BIO_TEMPLATES).format(
                    prof=prof, loc=loc, years=years
                )[:140]  # Profile.bio max_length=140

                profile.is_performer = True
                profile.performer_blacklisted = False
                profile.profession = prof
                profile.location = loc
                profile.bio = bio
                performers.append(user.id)

                # Create 3–10 uploads per performer (varied count)
                existing = Upload.objects.filter(profile=profile).count()
                target_uploads = random.randint(3, 10)
                if existing < target_uploads and test_images:
                    for j in range(existing, target_uploads):
                        img = random.choice(test_images)
                        _make_upload(
                            profile, img,
                            f"{prof} portfolio piece {j+1}"
                        )

            # Client setup (801–1700)
            if i in CLIENT_RANGE:
                profile.is_potential_client = True
                profile.client_approved = True
                profile.client_blacklisted = False
                profile.location = profile.location or random.choice(LOCATIONS)
                profile.bio = profile.bio or f"Looking to hire performers in {profile.location}."
                clients.append(user.id)

            # Dual-role (601–800 get client flags too)
            if i in DUAL_ROLE_RANGE:
                profile.is_potential_client = True
                profile.client_approved = True
                profile.client_blacklisted = False
                if user.id not in clients:
                    clients.append(user.id)

            profile.save()

            # Auth token
            token, _ = Token.objects.get_or_create(user=user)
            tokens[username] = token.key

            # Progress logging
            if i % 100 == 0:
                self.stdout.write(f"  Load test users created: {i}/{total_users}")

        self.stdout.write(self.style.SUCCESS(
            f"  ✅ {total_users} load test users ready "
            f"({len(performers)} performers, {len(clients)} clients)"
        ))

        # --- Phase 2: Demo/showcase users ---
        demo_data = DEMO_USERS[:total_demo]
        demo_user_ids = []

        for idx, d in enumerate(demo_data):
            # Create username from name: "Meera Krishnan" → "demo_meera_krishnan"
            safe_name = d["name"].lower().replace(" ", "_").replace(".", "")
            username = f"demo_{safe_name}"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{safe_name}@createscale.demo",
                    "first_name": d["name"].split()[0],
                    "last_name": " ".join(d["name"].split()[1:]),
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.is_performer = True
            profile.performer_blacklisted = False
            profile.is_potential_client = True
            profile.client_approved = True
            profile.client_blacklisted = False
            profile.profession = d["prof"]
            profile.location = d["loc"]
            profile.bio = d["bio"][:140]
            profile.save()

            demo_user_ids.append(user.id)

            # Create 5–8 uploads per demo user
            existing = Upload.objects.filter(profile=profile).count()
            target = random.randint(5, 8)
            source_images = demo_images if demo_images else test_images
            if existing < target and source_images:
                for j in range(existing, target):
                    img = source_images[j % len(source_images)]
                    _make_upload(
                        profile, img,
                        f"{d['prof']} — {d['name']} showcase {j+1}"
                    )

            # Auth token (demo users also get tokens for testing)
            token, _ = Token.objects.get_or_create(user=user)
            tokens[username] = token.key

            if (idx + 1) % 10 == 0:
                self.stdout.write(f"  Demo users created: {idx+1}/{total_demo}")

        self.stdout.write(self.style.SUCCESS(
            f"  ✅ {len(demo_data)} demo users ready"
        ))

        # --- Phase 3: Pre-seed engagements ---
        if not options.get("skip_bookings"):
            self._seed_engagements(performers, clients)

        # --- Phase 4: Write tokens file ---
        output = {
            "tokens": tokens,
            "performer_user_ids": performers,
            "client_user_ids": clients,
            "demo_user_ids": demo_user_ids,
        }
        with open(TOKEN_OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"  ✅ SEED COMPLETE\n"
            f"  Load test users: {total_users}\n"
            f"  Demo users:      {len(demo_data)}\n"
            f"  Performers:      {len(performers)}\n"
            f"  Clients:         {len(clients)}\n"
            f"  Tokens:          {TOKEN_OUTPUT_PATH}\n"
            f"{'='*60}\n"
        ))

    def _seed_engagements(self, performer_ids, client_ids):
        """Create 500 pre-seeded engagements in various statuses."""
        self.stdout.write("  Seeding 500 engagements...")

        statuses_to_create = (
            [Engagement.STATUS_PENDING] * 200 +
            [Engagement.STATUS_ACCEPTED] * 150 +
            [Engagement.STATUS_DECLINED] * 50 +
            [Engagement.STATUS_CANCELLED_CLIENT] * 50 +
            [Engagement.STATUS_CANCELLED_PERFORMER] * 50
        )
        random.shuffle(statuses_to_create)

        created = 0
        for status in statuses_to_create:
            perf_id = random.choice(performer_ids)
            client_id = random.choice(client_ids)

            # Avoid self-booking
            if perf_id == client_id:
                continue

            event_date = _random_future_date()
            event_time = _random_time()

            # Check if this exact combo already exists
            if Engagement.objects.filter(
                client_id=client_id,
                performer_id=perf_id,
                date=event_date,
            ).exists():
                continue

            try:
                eng = Engagement(
                    client_id=client_id,
                    performer_id=perf_id,
                    date=event_date,
                    time=event_time,
                    venue=random.choice(VENUES),
                    occasion=random.choice(OCCASIONS),
                    status=Engagement.STATUS_PENDING,
                )
                # Save as pending first (to pass clean() validation)
                eng.save()

                # Then update status directly if needed
                if status != Engagement.STATUS_PENDING:
                    Engagement.objects.filter(pk=eng.pk).update(status=status)

                created += 1
            except Exception:
                # Skip validation errors (max 3 future, duplicate, etc.)
                continue

            if created % 100 == 0:
                self.stdout.write(f"    Engagements: {created}")

        self.stdout.write(self.style.SUCCESS(
            f"  ✅ {created} engagements seeded"
        ))
