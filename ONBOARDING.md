# CreateScale (ArtKhoj) — Developer Onboarding Guide

> **What is this app?** CreateScale is a marketplace connecting **performers** (musicians, dancers, comedians, magicians, etc.) with **clients** who want to hire them for events. Users browse a global feed, view portfolios, send hire requests, and manage engagements — all with admin oversight and blacklist controls. The platform serves both a Django web interface and a React Native (Expo) mobile app via a shared REST API.

---

## How It All Fits Together

Before diving into individual technologies, here is the big picture — how every piece connects to form a working system.

It starts with **code**. You write Python (Django) for the backend and JavaScript (React Native) for the mobile app. Both live in the same Git repository. Git tracks every change you make, lets you branch off to work on features without breaking things, and merge back when ready.

When you push code to the `main` branch on GitHub, **CI/CD** kicks in automatically. GitHub Actions runs a pipeline: first it lints your Python code and scans for security issues, then it builds a **Docker image** — a self-contained package of your Django app plus all its dependencies. Think of Docker as a shipping container for software: no matter where it runs, the contents are identical. The pipeline runs tests against a real PostgreSQL database, and if everything passes, it pushes the Docker image to GitHub's container registry (GHCR).

Now deployment. The pipeline uses **AWS SSM** (Systems Manager) to send commands to your **EC2 instances** — virtual machines running in Amazon's Mumbai data center. There are three types of instances. The **DB box** runs PostgreSQL (your database), Redis (your cache), and all the monitoring tools. The **Web OD instance** (On-Demand) is your always-running web server — it pulls the new Docker image, runs database migrations, and starts serving traffic. Then there are **Spot instances** — cheap, expendable copies of the web server that an **Auto Scaling Group** (ASG) launches automatically when traffic increases. A **Launch Template** tells AWS exactly how to set up each new Spot instance: install Docker, pull the image, download the `.env` config file from S3, and start everything.

On the OD instance, **Nginx** sits in front of everything as a reverse proxy and load balancer. It receives requests, decides which web server (local or a Spot instance) should handle them, and forwards the request. Nginx discovers Spot instances automatically by polling the EC2 API every 30 seconds.

But users never hit Nginx directly. **Cloudflare** sits at the very front — it terminates SSL (so users get HTTPS), blocks bots, caches some responses, and protects against DDoS attacks. Cloudflare forwards requests to Nginx over HTTP (called "Flexible SSL"), and Nginx tells Django it was originally HTTPS by setting a header.

Inside the Docker container, **Gunicorn** is the application server that runs your Django code. It spawns multiple worker processes and threads to handle concurrent requests. Django processes each request: reads from the database, checks the cache, renders HTML templates (for the web) or returns JSON (for the mobile app via Django REST Framework). User-uploaded images and videos are stored in **Cloudflare R2** (an S3-compatible object storage service), not on the server's disk.

Meanwhile, everything is being watched. **Prometheus** scrapes metrics from every web instance every 45 seconds — request rates, error rates, latency, cache hit ratios. **Grafana** visualizes these metrics in dashboards. **Promtail** ships container logs to **Loki** for centralized log aggregation. **GlitchTip** (a self-hosted Sentry) catches unhandled exceptions and groups them into trackable issues. Alert rules fire if the 5xx error rate spikes or an instance goes down.

The mobile app, built with **React Native** and **Expo**, talks to Django exclusively through the REST API. It authenticates with a token, fetches data, renders native iOS/Android UI, and handles OAuth login flows for Google, Twitter, and LinkedIn.

Here is the flow as a diagram:

```
  Developer                     GitHub                    AWS (ap-south-1)
  =========                     ======                    ================

  git push main ──────────> GitHub Actions Pipeline
                              │
                              ├─ 1. Lint + Security scan
                              ├─ 2. Docker build
                              ├─ 3. Pytest (Postgres + Redis)
                              ├─ 4. Push ARM64 image ──────> GHCR (container registry)
                              │
                              └─ 5. Deploy via SSM ─────────────────────────────────┐
                                                                                    │
                                                                                    ▼
  ┌── User ──────────────────────────────────────────────────────────────────────────┐
  │                                                                                  │
  │  Phone (Expo app)                        Browser                                 │
  │    │                                       │                                     │
  │    │  REST API (JSON)                      │  HTML pages                         │
  │    │                                       │                                     │
  │    └──────────────┐    ┌───────────────────┘                                     │
  │                   ▼    ▼                                                         │
  │              ┌──────────────┐                                                    │
  │              │  Cloudflare  │  SSL termination, DDoS protection, CDN             │
  │              └──────┬───────┘                                                    │
  │                     │ HTTP (Flexible SSL)                                        │
  │                     ▼                                                            │
  │    ┌─────────── Web OD Instance ───────────┐                                    │
  │    │   Nginx (reverse proxy + LB)          │                                    │
  │    │     ├─> localhost:8000  ───────────┐   │                                    │
  │    │     └─> Spot IPs:8000 ──────┐     │   │                                    │
  │    │                             │     │   │                                    │
  │    │   ┌─────────────────────┐   │     │   │   ┌── Spot Instances ──────┐       │
  │    │   │ Docker Container    │   │     │   │   │  Docker Container      │       │
  │    │   │  Gunicorn (Django)  │◄──┘     │   │   │   Gunicorn (Django)    │       │
  │    │   │  WhiteNoise(static) │         │   │   │   WhiteNoise(static)   │       │
  │    │   └─────────────────────┘         │   │   └────────────────────────┘       │
  │    └───────────────────────────────────┘   │                                    │
  │                                            │                                    │
  │                     ┌──────────────────────┘                                    │
  │                     ▼                                                            │
  │    ┌─────────── DB Box ────────────────────┐                                    │
  │    │   PostgreSQL 16     Redis 7           │                                    │
  │    │   Prometheus        Grafana           │                                    │
  │    │   Loki              GlitchTip         │                                    │
  │    └───────────────────────────────────────┘                                    │
  │                                                                                  │
  │    ┌──────────────┐                                                              │
  │    │ Cloudflare R2 │  Media uploads (images, videos)                             │
  │    └──────────────┘                                                              │
  │                                                                                  │
  │    ┌──────────────┐                                                              │
  │    │  S3 Bucket   │  Canonical .env config (single source of truth)              │
  │    └──────────────┘                                                              │
  └──────────────────────────────────────────────────────────────────────────────────┘
```

Every section below zooms into one part of this picture. Read them in order for the full picture, or jump to the section you need.

---

## Table of Contents

1. [Tech Stack at a Glance](#1-tech-stack-at-a-glance)
2. [Django Fundamentals](#2-django-fundamentals)
3. [Project Structure and Apps](#3-project-structure-and-apps)
4. [Models and Database](#4-models-and-database)
5. [Views, URLs and Templates](#5-views-urls-and-templates)
6. [REST API (DRF)](#6-rest-api-drf)
7. [Authentication and OAuth](#7-authentication-and-oauth)
8. [The Booking / Hiring System](#8-the-booking--hiring-system)
9. [React Native / Expo Frontend](#9-react-native--expo-frontend)
10. [Docker and Containerization](#10-docker-and-containerization)
11. [AWS Infrastructure](#11-aws-infrastructure)
12. [Nginx and Load Balancing](#12-nginx-and-load-balancing)
13. [CI/CD Pipeline](#13-cicd-pipeline)
14. [Git Workflow](#14-git-workflow)
15. [Monitoring and Observability](#15-monitoring-and-observability)
16. [Django Admin, Grafana and GlitchTip](#16-django-admin-grafana-and-glitchtip)
17. [Environment Variables Reference](#17-environment-variables-reference)
18. [Common Commands Cheat Sheet](#18-common-commands-cheat-sheet)
19. [DOs and DON'Ts](#19-dos-and-donts)
20. [Further Reading](#20-further-reading)

---

## 1. Tech Stack at a Glance

This section is your quick reference card. Every technology used in the project is listed here with its role. If you see a name you do not recognize while reading code or configs, come back to this table.

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Django 5.1 + DRF | Web framework + REST API |
| Frontend (web) | Django templates | Server-rendered HTML pages |
| Frontend (mobile) | React Native / Expo SDK 54 | iOS + Android app |
| Database | PostgreSQL 16 | Primary data store |
| Cache | Redis 7 | Session cache, API response cache |
| Object Storage | Cloudflare R2 (S3-compatible) | Media uploads (images, videos) |
| Web Server | Nginx 1.27 | Reverse proxy, load balancing, caching |
| App Server | Gunicorn (gthread) | WSGI server running Django |
| Containerization | Docker + Docker Compose | Packaging and orchestration |
| CI/CD | GitHub Actions | Lint, build, test, push, deploy |
| Infra | AWS EC2 (ARM Graviton3) | Compute (OD + Spot instances) |
| Scaling | AWS ASG + Launch Templates | Auto-scale Spot fleet |
| Config | AWS S3 | Canonical .env storage (single source of truth) |
| Remote Exec | AWS SSM | Deploying commands to instances (no SSH needed) |
| CDN/DDoS | Cloudflare (Flexible SSL) | TLS termination, bot protection, caching |
| Monitoring | Prometheus + Grafana | Metrics collection + dashboards |
| Logging | Loki + Promtail | Centralized log aggregation |
| Error Tracking | GlitchTip (Sentry-compatible) | Crash/error reporting |
| Profiling | django-silk | Request/query profiling (dev only) |
| Password Hashing | Argon2 | Primary password hasher |

---

## 2. Django Fundamentals

If you are new to Django, this section explains the core files and concepts you will encounter everywhere in the project. If you already know Django, skip ahead to Section 3.

Django is a Python web framework that follows the MTV (Model-Template-View) pattern — similar to MVC in other frameworks. A request comes in, the URL router matches it to a view function, the view queries models (database), and returns a response (usually an HTML template or JSON). [Django docs](https://docs.djangoproject.com/en/5.1/)

### Key files every Django project has

| File | What it does |
|------|-------------|
| manage.py | CLI entry point. You never edit this file — you use it to run commands. [Docs](https://docs.djangoproject.com/en/5.1/ref/django-admin/) |
| settings.py | Central config: database, middleware, installed apps, static files, caching, auth, everything. Ours is at myproject/settings.py. [Docs](https://docs.djangoproject.com/en/5.1/ref/settings/) |
| urls.py | Maps URL paths to views. Each app has its own urls.py, and the project-level one includes them all. [Docs](https://docs.djangoproject.com/en/5.1/topics/http/urls/) |
| views.py | Request handlers. Receives HTTP request, does logic, returns response. [Docs](https://docs.djangoproject.com/en/5.1/topics/http/views/) |
| models.py | Database schema as Python classes. Each model = one DB table. [Docs](https://docs.djangoproject.com/en/5.1/topics/db/models/) |
| admin.py | Registers models for the Django admin panel at /admin/. [Docs](https://docs.djangoproject.com/en/5.1/ref/contrib/admin/) |
| forms.py | Server-side form validation classes for template-rendered views. [Docs](https://docs.djangoproject.com/en/5.1/topics/forms/) |
| serializers.py | DRF equivalent of forms — validates and serializes data for REST API. [DRF docs](https://www.django-rest-framework.org/api-guide/serializers/) |
| signals.py | Event hooks. Example: when a User is created, auto-create a Profile. [Docs](https://docs.djangoproject.com/en/5.1/topics/signals/) |
| apps.py | App metadata and startup hooks (importing signals in ready()). |
| middleware.py | Code that runs on every request/response. [Docs](https://docs.djangoproject.com/en/5.1/topics/http/middleware/) |

### What are migrations?

Migrations are version-controlled database schema changes. When you modify a model (add a field, change a type), Django generates a migration file with the SQL needed to update the database. You apply them with a command. This means your database schema is tracked in Git just like your code.

**Commands:**

```bash
python manage.py makemigrations              # Generate migration files from model changes
python manage.py migrate                     # Apply pending migrations to the database
python manage.py showmigrations              # See which migrations have been applied
python manage.py makemigrations --check      # CI check: fail if unapplied model changes
```

### What are templates?

Django templates are HTML files with special tags for logic and variables. They live in each app's templates directory by convention. The extends tag lets you inherit a base layout, the if tag adds conditionals, and double-curly-braces insert variable values.

**Example:**

```django
{% extends 'users/base.html' %}
{% load static %}

{% if user.profile.is_performer %}
    <p>{{ user.username }} is a performer</p>
{% endif %}

<img src="{% static 'users/images/default-avatar.png' %}">
```

[Template docs](https://docs.djangoproject.com/en/5.1/topics/templates/)

---

## 3. Project Structure and Apps

This section maps out the entire repository so you know where to find things. Django projects are organized into "apps" — modular packages that each own a slice of functionality. Our project has two custom apps (users and bookings), a React Native frontend, Docker and deployment configs, and CI/CD workflows.

```
myproject/
├── myproject/                       # Django project config package
│   ├── settings.py                  # All Django settings
│   ├── urls.py                      # Root URL router
│   ├── wsgi.py                      # WSGI entry point (Gunicorn uses this)
│   └── storage.py                   # Custom WhiteNoise storage backend
│
├── users/                           # Users app: profiles, uploads, messaging, OAuth
│   ├── models.py                    # Profile, Upload, Message models
│   ├── views.py                     # 10 HTML views (signup, login, profile, feed, etc.)
│   ├── urls.py                      # /users/* routes
│   ├── forms.py                     # 5 forms (register, upload, profile, filter, message)
│   ├── admin.py                     # ProfileAdmin with role/blacklist filters
│   ├── middleware.py                # EnsureProfileMiddleware
│   ├── signals.py                   # Auto-create Profile on User creation
│   ├── linkedin_adapter.py          # Custom LinkedIn OIDC adapter
│   ├── oauth_views.py               # Unified OAuth endpoint for mobile
│   ├── api/
│   │   ├── views.py                 # DRF views (auth, profile, feed, uploads, events)
│   │   ├── serializers.py           # 5 serializers
│   │   └── urls.py                  # /api/* routes
│   ├── templates/users/             # HTML templates
│   ├── static/users/                # CSS, JS, images
│   └── management/commands/
│       └── seed_loadtest_v2.py      # Seed 2000 test users + 500 engagements
│
├── bookings/                        # Bookings app: the hiring/engagement system
│   ├── models.py                    # Engagement model (state machine, 6 statuses)
│   ├── views.py                     # 4 HTML views (hire, client list, performer list, detail)
│   ├── urls.py                      # /bookings/* routes
│   ├── forms.py                     # EngagementRequestForm, EmergencyCancelForm
│   ├── api/
│   │   ├── views.py                 # DRF ViewSet (hire, list, detail, action)
│   │   └── serializers.py           # 3 serializers
│   └── templates/bookings/          # Booking HTML templates
│
├── createscale-app/                 # React Native / Expo mobile app
│   ├── App.js                       # Root component, navigation stacks
│   ├── src/screens/                 # 7 screens (Login, Signup, Profile, Feed, etc.)
│   ├── src/api/auth.js              # API client functions
│   ├── src/config/api.js            # Base URL config (dev/prod)
│   ├── src/context/AuthContext.js    # Auth state (token + user)
│   └── src/components/              # SocialLoginButtons
│
├── compose/                         # Docker entrypoint + local nginx configs
│   ├── entrypoint.sh                # Boot: DB wait, migrate, collectstatic, gunicorn
│   ├── nginx.conf                   # Local dev nginx
│   └── nginx-fleet.conf             # Local fleet simulation nginx
│
├── deploy/                          # Production deployment configs
│   ├── web/                         # Web instance (docker-compose, promtail, .env.example)
│   ├── db/                          # DB box (postgres, redis, prometheus, grafana, loki)
│   └── nginx/                       # Production nginx (artkhoj.conf, upstream discovery)
│
├── .github/workflows/deploy.yml     # CI/CD pipeline (7 jobs)
├── Dockerfile                       # Python 3.12-slim container image
├── docker-compose.yml               # Local dev stack (full monitoring)
├── docker-compose.fleet.yml         # Local fleet simulation (3 replicas)
├── requirements.txt                 # Python dependencies
└── tests/test_layer1.py             # Layer 1 tests (run in CI)
```

---

## 4. Models and Database

The database is the foundation of everything. This section covers every model in the project, what fields they have, and how they relate to each other. Understanding the models tells you what data the application works with.

### Users App Models (users/models.py)

**Profile** — one-to-one with Django's built-in User model:

| Field | Type | Purpose |
|-------|------|---------|
| user | OneToOneField(User) | Links to Django auth User |
| profession | CharField(100) | What the user does (indexed for search) |
| location | CharField(100) | City/area |
| bio | CharField(140) | Short bio |
| profile_picture | ImageField | Avatar (stored in R2 in production) |
| is_performer | BooleanField | Opt-in: available to be hired |
| is_potential_client | BooleanField | Opt-in: wants to hire performers |
| client_approved | BooleanField | Admin-set gate: must be True before client can hire |
| performer_blacklisted | BooleanField | Admin-set: blocks user from being hired |
| client_blacklisted | BooleanField | Admin-set: blocks user from hiring |

**Upload** — foreign key to Profile (one profile has many uploads):

| Field | Type | Purpose |
|-------|------|---------|
| profile | ForeignKey(Profile) | Owner |
| image | ImageField | Portfolio image |
| video | FileField | Portfolio video (MP4 only, max 50MB) |
| caption | TextField | Description |
| upload_date | DateTimeField | Auto-set on creation |

**Message** — foreign key to User (sender and recipient):

| Field | Type | Purpose |
|-------|------|---------|
| sender | ForeignKey(User) | Who sent it |
| recipient | ForeignKey(User) | Who receives it |
| content | TextField | Message text |
| timestamp | DateTimeField | Auto-set |
| is_read | BooleanField | Read receipt |
| date, time, location | Optional fields | For legacy hiring requests embedded in messages |
| hiring_status | CharField | none/pending/accepted/declined (legacy hiring flow) |

Note: The Message model's hiring fields are the OLD hiring system. The Engagement model (Section 8) is the new, proper booking system.

### Bookings App Model (bookings/models.py)

The Engagement model is covered in detail in Section 8 (The Booking / Hiring System).

### Database Config

Production uses PostgreSQL 16 on the DB box (172.31.6.148), accessible via VPC private IP. Local dev uses PostgreSQL 16 via Docker Compose (or SQLite fallback). Connection pooling is set to CONN_MAX_AGE=60 seconds. The pg_stat_statements extension is preloaded for query performance tracking.

---

## 5. Views, URLs and Templates

Views are where request handling logic lives. A URL pattern maps to a view function, which processes the request and returns a response. This section maps out every URL in the application and what view handles it.

### Project-Level URL Map (myproject/urls.py)

| URL Pattern | Where it goes | Notes |
|-------------|---------------|-------|
| /admin/ | Django admin | Superuser access |
| /users/... | users.urls | Signup, login, profile, feed, messaging |
| /bookings/... | bookings.urls | Hire requests, engagement management |
| /api/... | users.api.urls + bookings.api.urls | REST API for mobile app |
| /accounts/... | django-allauth | OAuth login/callback (Google, Twitter, LinkedIn) |
| /silk/ | django-silk | Request profiler (dev only) |
| / (metrics) | django-prometheus | /metrics endpoint for Prometheus |

### Users App Views (users/views.py)

| View | URL | Method | What it does |
|------|-----|--------|-------------|
| signup | /users/signup/ | GET/POST | Create account + auto-create Profile |
| signin | /users/login/ | GET/POST | Session-based login |
| profile | /users/profile/ | GET/POST | Edit own profile, upload media |
| global_feed | /users/global-feed/ | GET | Browse all users, filter by profession (cached 60s) |
| profile_detail | /users/profile/id/ | GET | View another user's profile |
| send_message | /users/send_message/id/ | POST | Send a direct message |
| inbox | /users/inbox/ | GET | Thread-grouped conversations |
| message_thread | /users/message_thread/id/ | GET/POST | Chat + legacy hiring requests |
| live_events | /users/live-events/ | GET | Upcoming accepted engagements (cached 60s) |

### Bookings App Views (bookings/views.py)

| View | URL | Method | What it does |
|------|-----|--------|-------------|
| create_hire_request | /bookings/hire/performer_id/ | GET/POST | Send hire request (role checks enforced) |
| client_engagement_list | /bookings/client/ | GET | Client's bookings dashboard |
| performer_engagement_list | /bookings/performer/ | GET | Performer's incoming requests |
| engagement_detail | /bookings/engagement/pk/ | GET/POST | Accept/decline/cancel with business rules |

### Template Files

All templates live in app/templates/app/ by convention:

- base.html — shared layout (CSS, nav, footer)
- login.html, signup.html — auth pages
- profile.html — edit own profile + upload gallery
- global_feed.html — performer cards with profession filter
- profile_detail.html — public profile view
- inbox.html, message_thread.html — messaging
- live_events.html — upcoming events
- hire_form.html, engagement_detail.html, client_engagements.html, performer_engagements.html — booking system

---

## 6. REST API (DRF)

The mobile app communicates with Django entirely through REST API endpoints built with Django REST Framework. This section lists every endpoint, its HTTP method, authentication requirement, and purpose. All endpoints require Token auth unless marked otherwise.

### Auth Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/auth/token/ | POST | None | Login with username + password, returns token |
| /api/auth/signup/ | POST | None | Create account, returns token |
| /api/auth/logout/ | POST | Token | Delete token (logout) |
| /api/auth/me/ | GET | Token | Confirm auth, return profile summary |
| /api/auth/oauth/ | POST | None | Unified OAuth (Google/Twitter/LinkedIn) |

### User and Profile Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/users/me/ | GET/PATCH | Token | Own profile (multipart for picture upload) |
| /api/users/me/uploads/ | GET/POST | Token | Own media gallery |
| /api/users/me/uploads/id/ | DELETE | Token | Delete own upload |
| /api/users/feed/ | GET | Token | Paginated global feed (filter by profession) |
| /api/users/profiles/id/ | GET | Token | Other user's profile + uploads |
| /api/users/professions/ | GET | Token | List all professions (5min cache) |
| /api/users/live-events/ | GET | Token | Accepted future engagements |

### Booking Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| /api/bookings/hire/performer_id/ | POST | Token | Create engagement |
| /api/bookings/engagements/ | GET | Token | List all user's engagements |
| /api/bookings/engagements/client/ | GET | Token | List as client only |
| /api/bookings/engagements/performer/ | GET | Token | List as performer only |
| /api/bookings/engagements/pk/ | GET | Token | Engagement detail |
| /api/bookings/engagements/pk/action/ | POST | Token | Accept/decline/cancel |

### Caching Strategy

API views use a custom _cached(key, timeout, compute_fn) helper. Cache keys include user ID and pagination to prevent stale data across users. Cache is invalidated on profile updates, upload changes, and engagement actions.

[DRF documentation](https://www.django-rest-framework.org/)

---

## 7. Authentication and OAuth

Authentication is how the app knows who you are. This section covers the three auth mechanisms in use, how OAuth works with three providers, and how profiles are automatically created for new users regardless of how they sign up.

### Three auth mechanisms

1. **Session auth (web):** Django's built-in session cookies. Used by HTML templates — the login form sets a session cookie.
2. **Token auth (mobile):** DRF TokenAuthentication. The Expo app sends an Authorization: Token header with every request.
3. **OAuth (both):** django-allauth handles Google, Twitter, LinkedIn. The web uses allauth's redirect flow; mobile uses a custom unified endpoint (/api/auth/oauth/).

### OAuth Flows

| Provider | Web Flow | Mobile Flow |
|----------|----------|-------------|
| Google | allauth redirect to Google consent then callback | ID token verification (google-auth library) |
| Twitter | allauth redirect to Twitter consent then callback | PKCE authorization code then token exchange |
| LinkedIn | Custom adapter to LinkedIn OIDC then callback | Authorization code then token exchange then userinfo |

### LinkedIn Custom Adapter (users/linkedin_adapter.py)

LinkedIn deprecated their V1 API. Our custom LinkedInOIDCAdapter overrides allauth's default to use POST (not GET) for token exchange, use /v2/userinfo (OIDC) instead of the deprecated /v2/me endpoint, and map OIDC fields (sub, given_name, family_name, email) to allauth's expected format.

### Profile Auto-Creation

Profiles are auto-created via two mechanisms (belt and suspenders):

1. **signals.py:** post_save signal on User triggers Profile.objects.get_or_create()
2. **EnsureProfileMiddleware:** Runs on every authenticated request, calls Profile.objects.get_or_create()

This double-safety ensures a Profile always exists, even for OAuth signups that might skip the signal.

---

## 8. The Booking / Hiring System

This is the core business logic of the application. Clients hire performers for events through a structured request flow with admin oversight, blacklist controls, time-based expiration, and emergency cancellation rules. The Engagement model acts as a state machine with well-defined transitions.

### The Engagement Model (bookings/models.py)

The Engagement tracks a single hire request from creation to resolution.

| Field | Type | Purpose |
|-------|------|---------|
| client | ForeignKey(User) | The person hiring |
| performer | ForeignKey(User) | The person being hired |
| date | DateField | Event date |
| time | TimeField | Event time |
| venue | CharField(255) | Where the event happens |
| occasion | CharField(255) | What the event is |
| status | CharField | pending, accepted, declined, cancelled_client, cancelled_performer, auto_expired |
| client_emergency_reason | TextField | Required when client cancels within 24h |
| performer_emergency_reason | TextField | Required when performer cancels within 24h |
| created_at | DateTimeField | When the request was made |
| updated_at | DateTimeField | Last status change |

### Status Lifecycle

```
Client sends hire request
        |
        v
    PENDING  (created by client)
        |
   +---------+------------+
   |         |            |
   v         v            v
ACCEPTED   DECLINED   AUTO_EXPIRED
   |                  (24h, no response)
   |
   +----------------+
   |                |
   v                v
CANCELLED       CANCELLED
_CLIENT         _PERFORMER
(needs reason   (needs reason
 if < 24h)       if < 24h)
```

### Business Rules

| No. | Rule | Enforced In |
|-----|------|-------------|
| 1 | Cannot hire yourself | clean() |
| 2 | Performers opt-in via is_performer=True on Profile | create_hire_request view |
| 3 | Clients need admin approval (client_approved=True) | create_hire_request view |
| 4 | Blacklisted users cannot hire or be hired | create_hire_request view |
| 5 | Max 3 ongoing (pending + accepted) future engagements per client | clean() |
| 6 | No duplicate requests: same client, same performer, same day | clean() |
| 7 | One accepted booking per performer per date (auto-declines others) | accept() |
| 8 | Performer must respond within 24 hours or request auto-expires | accept() |
| 9 | Last-minute cancellation (less than 24h to event) requires emergency reason | cancel methods |
| 10 | Only pending engagements can be accepted or declined | _ensure_pending() |
| 11 | Client can hire multiple performers for the same day and venue | No restriction |

### Database Indexes

The Engagement model has three composite indexes optimized for the most common queries:

- (client, status, date) — Client dashboard + 3-booking limit check
- (performer, status, date) — Performer dashboard + daily uniqueness check
- (status, date, time) — Live events view

### Future Features (designed to accommodate)

These are not yet implemented but the data model supports them:

- Client engagement dashboard (view exists, needs UI polish)
- Performer engagement dashboard (same)
- Admin track record of past engagements (all data stored, just needs an admin view)
- Background check system for clients (extend the client_approved flow)

---

## 9. React Native / Expo Frontend

The mobile app gives performers and clients a native experience on iOS and Android. It talks to Django exclusively through the REST API and handles its own authentication, navigation, and media uploads. This section covers the app structure, screens, hooks, and how to run it locally.

### What is Expo?

Expo is a framework on top of React Native that simplifies mobile app development. It provides pre-built native modules (camera, location, auth), over-the-air updates, and build services. You write JavaScript/TypeScript and it compiles to native iOS and Android apps. [Expo docs](https://docs.expo.dev/)

### Key Config

- Expo SDK: 54, React Native: 0.81.5, React: 19.1
- New Architecture: Enabled (Fabric renderer + TurboModules)
- Navigation: React Navigation (stack-based, not file-based Expo Router)
- State Management: React Context API (AuthContext) — no Redux
- Styling: StyleSheet.create() with inline color constants — no NativeWind

### Screens

| Screen | File | Backend API | Key Features |
|--------|------|-------------|-------------|
| LoginScreen | src/screens/LoginScreen.js | POST /api/auth/token/ | Username/password + social OAuth buttons |
| SignupScreen | src/screens/SignupScreen.js | POST /api/auth/signup/ | Animated form, auto-login after signup |
| ProfileScreen | src/screens/ProfileScreen.js | GET/PATCH /api/users/me/ | Edit profile, upload media, GPS location, role toggles |
| GlobalFeedScreen | src/screens/GlobalFeedScreen.js | GET /api/users/feed/ | Profession filter pills, paginated performer cards |
| ProfileDetailScreen | src/screens/ProfileDetailScreen.js | GET /api/users/profiles/id/ | Public profile + inline hire form |
| BookingsScreen | src/screens/BookingsScreen.js | GET/POST /api/bookings/ | Client+performer dashboard, action buttons |
| LiveEventsScreen | src/screens/LiveEventsScreen.js | GET /api/users/live-events/ | Tabbed (upcoming/past), accepted events only |

### What are React Hooks?

Hooks are functions that let you use React features (state, lifecycle, context) in functional components. They are the modern way to write React — no class components needed. [React hooks docs](https://react.dev/reference/react/hooks)

| Hook | What it does |
|------|-------------|
| useState | Local component state. Returns [value, setter]. |
| useEffect | Side effects (API calls, subscriptions). Runs after render. |
| useContext | Access shared state (e.g., auth token from AuthContext). |
| useCallback | Memoize functions to prevent unnecessary re-renders. |
| useRef | Persist values across renders without triggering re-render. |
| useNavigation | React Navigation hook for screen transitions. |

### Auth Flow (mobile)

1. App starts and reads @auth_token from AsyncStorage
2. Token found? Show authenticated stack (Profile, Feed, Bookings, etc.)
3. No token? Show login/signup screens
4. Login or signup returns a DRF token which is stored in AsyncStorage
5. Logout clears AsyncStorage and returns to login screen

### API Integration

All API calls use fetch() with Authorization: Token header. Base URL is configured in src/config/api.js. In development, it points to your machine's LAN IP; in production, update it with your domain.

### Running the app

```bash
cd createscale-app
npm install                     # Install dependencies
npx expo start                  # Start dev server (scan QR with Expo Go)
npx expo start --android        # Android emulator
npx expo start --ios            # iOS simulator
npx expo start --web            # Browser
```

[React Native docs](https://reactnative.dev/docs/getting-started) | [Expo SDK reference](https://docs.expo.dev/versions/latest/)

---

## 10. Docker and Containerization

Docker is how we package and run the application consistently across local dev machines, CI, and production servers. This section explains Docker concepts, our Dockerfile, the boot sequence, and the various Compose files for different environments.

### What is Docker?

Docker packages your app plus all its dependencies (Python, system libraries, configs) into a container — a lightweight, isolated environment that runs identically everywhere. No more "works on my machine." [Docker docs](https://docs.docker.com/get-started/)

### Key Concepts

| Concept | What it is |
|---------|-----------|
| Image | A read-only blueprint. Built from Dockerfile. Tagged like ghcr.io/datatwine/createscale:latest. |
| Container | A running instance of an image. Has its own filesystem, network, process space. |
| Dockerfile | Recipe for building an image. Each line is a cached layer. |
| docker-compose | Tool for defining multi-container setups in YAML. |
| Volume | Persistent storage that survives container restarts. |
| Registry | Where images are stored. We use GHCR (GitHub Container Registry). |

### Our Dockerfile

The image is built from python:3.12-slim. It installs system deps (libpq-dev for PostgreSQL, netcat for DB health checks), copies requirements.txt and pip installs, copies the app code, creates a non-root appuser, creates /vol/static and /vol/media directories, and sets compose/entrypoint.sh as the entrypoint.

### Boot Sequence (compose/entrypoint.sh)

Every time a container starts, the entrypoint runs this sequence:

1. Fix ownership on /vol/static and /vol/media (needed because Docker volumes start as root)
2. Wait for PostgreSQL to be reachable (netcat ping loop)
3. Run migrations (OD instance only — controlled by RUN_MIGRATIONS env var)
4. Run collectstatic (ALL instances — WhiteNoise needs the manifest file)
5. Setup Prometheus multiprocess directory at /tmp/metrics
6. Start Gunicorn (becomes PID 1 via exec for proper signal handling)

### Docker Compose Files

| File | Purpose | When to use |
|------|---------|-------------|
| docker-compose.yml | Full local dev stack (DB, Redis, Nginx, Prometheus, Grafana, GlitchTip) | docker compose up |
| docker-compose.override.yml | Auto-applied: mounts source code, enables hot-reload | Applied automatically |
| docker-compose.fleet.yml | Simulates production: 3 web replicas, Loki, separate migrate service | docker compose -f docker-compose.yml -f docker-compose.fleet.yml up |
| deploy/web/docker-compose.web.yml | Production web instance (Gunicorn + Promtail + Node Exporter) | On EC2 web instances |
| deploy/db/docker-compose.data.yml | Production DB box (Postgres, Redis, Prometheus, Grafana, Loki, exporters) | On EC2 DB instance |

### Essential Commands

```bash
docker compose up -d                   # Start all services detached
docker compose down                    # Stop all services
docker compose logs -f web             # Follow web container logs
docker compose ps                      # Show running containers
docker compose exec web bash           # Shell into web container
docker compose build                   # Rebuild images
docker compose up -d --force-recreate  # Restart with fresh containers
docker system prune -a                 # Remove ALL unused images (reclaim disk)
```

---

## 11. AWS Infrastructure

AWS provides the servers, networking, storage, and scaling that run the application in production. This section explains each AWS service we use, how the instances are organized, and how environment config is centralized.

### Architecture Diagram

```
Internet
  |
  v
Cloudflare (SSL, DDoS, CDN)
  |
  v (HTTP)
Web OD Instance (c7g.large, always running)
  |-- Nginx (reverse proxy + load balancer)
  |     |-- localhost:8000 (own Gunicorn)
  |     |-- Spot IP 1:8000
  |     |-- Spot IP 2:8000 ...
  |-- Gunicorn (Django) in Docker
  |-- Promtail (ships logs to DB box)
  |-- Node Exporter (CPU/memory metrics)
  |
Spot Instances (c7g.large x N, auto-scaled)
  |-- Gunicorn (Django) in Docker
  |-- Promtail
  |-- Node Exporter
  |
DB Box (c7g.large, always running)
  |-- PostgreSQL 16 (port 5432)
  |-- Redis 7 (port 6379)
  |-- Prometheus (port 9090)
  |-- Grafana (port 3000)
  |-- Loki (port 3100)
  |-- GlitchTip (port 8000)
```

### AWS Concepts Explained

**EC2 (Elastic Compute Cloud):** Virtual machines in the cloud. We use c7g.large instances (2 CPU, 4GB RAM, ARM Graviton3) in the ap-south-1 (Mumbai) region. [Docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html)

**On-Demand (OD):** Pay-by-the-hour instance that always runs. Our web OD handles Nginx, migrations, and is the stable foundation.

**Spot Instances:** Spare EC2 capacity at 60-90% discount. They can be interrupted with 2 minutes warning. We use these for extra web capacity — stateless, expendable. [Docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html)

**Auto Scaling Group (ASG):** Automatically launches or terminates Spot instances based on demand. Configured to scale when OD CPU exceeds 60%. [Docs](https://docs.aws.amazon.com/autoscaling/ec2/userguide/auto-scaling-groups.html)

**Launch Template:** Blueprint for new instances — what AMI to use, what instance type, what user data script to run, what IAM role to attach. ASG uses this to create new Spot instances. [Docs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-templates.html)

**IAM Role:** Permissions attached to an EC2 instance. Our instances have EC2-SSM-Role which allows SSM commands and S3 config reads. Never hardcode AWS credentials — use IAM roles. [Docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)

**Security Groups:** Firewall rules. Allow inbound traffic on specific ports (8000 for Gunicorn, 9100 for metrics, 22 for SSH) from specific IP ranges. Think of them as "which doors are open." [Docs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)

**SSM (Systems Manager):** Run commands on instances without SSH. CI/CD uses aws ssm send-command to deploy. No SSH keys needed in GitHub secrets. [Docs](https://docs.aws.amazon.com/systems-manager/latest/userguide/what-is-systems-manager.html)

**S3:** Object storage. We store the canonical .env in s3://createscale-config/web/.env. All instances pull from this single source of truth.

**VPC:** Virtual private network. All instances share a VPC so they talk via private IPs (172.31.x.x) with microsecond latency and zero data transfer cost.

### .env Centralization

One canonical .env lives in S3. This prevents OD/Spot drift:

- OD deploy: pulls from S3, then sed flips RUN_MIGRATIONS=0 to 1
- Spot deploy: pulls from S3, keeps RUN_MIGRATIONS=0
- Spot boot: launch template user data pulls from S3
- To update env vars: edit the S3 file, redeploy, all instances get the new values

---

## 12. Nginx and Load Balancing

Nginx is the front door to the application on the OD instance. It receives every request from Cloudflare, decides which backend server should handle it, and forwards the request. This section covers how Nginx is configured and how it automatically discovers new Spot instances.

Nginx serves four roles in our setup:

1. **Reverse proxy:** Forwards requests to Gunicorn (local and on Spot instances)
2. **Load balancer:** least_conn algorithm distributes across all healthy backends
3. **Cache:** Caches /api/users/professions/ (5min) and /api/users/live-events/ (30s)
4. **Cloudflare IP restoration:** set_real_ip_from blocks restore the real client IP from CF-Connecting-IP header

### Dynamic Upstream Discovery

A Python script (deploy/nginx/update_upstream.py) runs as a systemd service, polling the EC2 API every 30 seconds:

1. Query EC2 for instances tagged Role=web in running state
2. Exclude OD's own IP
3. Write upstream.conf with all Spot IPs plus 127.0.0.1:8000 (local Gunicorn)
4. Validate config (nginx -t) and reload

Nginx automatically picks up new Spot instances and drops terminated ones with no manual intervention.

### Key Config Details

- X-Forwarded-Proto is hardcoded to https (not $scheme) because Cloudflare Flexible SSL terminates TLS
- Each upstream server has max_fails=2, fail_timeout=10s for health checking
- No /static/ location block — static files are served by WhiteNoise inside the Docker container

---

## 13. CI/CD Pipeline

CI/CD automates everything between pushing code and it running in production. This section walks through every job in the pipeline, what triggers it, and what happens at each stage.

**CI (Continuous Integration)** means every push triggers automated checks. **CD (Continuous Deployment)** means after CI passes, code deploys to production automatically. No manual SSH or docker pull.

### Pipeline (.github/workflows/deploy.yml)

Triggered on: push to main, or pull request to main.

```
Push to main
    |
    v
GUARDRAILS ---- Ruff (lint) + Bandit (security scan)
    |
    v
BUILD ---------- docker compose build (validates Dockerfile)
    |
    v
TEST ----------- PostgreSQL + Redis services, makemigrations --check, pytest
    |
    +------------------+
    |                  |
    v                  v
PUSH-IMAGE         DEPLOY-DB (parallel)
ARM64 to GHCR      SSM to DB box
    |
    v
DEPLOY-WEB -------- OD canary first, then rolling Spot restart (30s delays)
    |
    v
DEPLOY-NGINX ------- Copy configs, validate, reload
```

### Key Details

- ARM64 native build: The push-image job runs on an ARM runner. No QEMU emulation, fast builds.
- Canary deploy: OD deploys first. If it fails, Spot instances stay on the old image.
- Rolling restart: Spot instances restart one-by-one with 30-second delays for zero-downtime.
- Migration safety: Only OD runs migrations (RUN_MIGRATIONS=1). Spot instances skip to avoid race conditions when multiple instances ALTER TABLE simultaneously.
- SSM-based: All deploy commands run via AWS Systems Manager. No SSH keys in CI.

[GitHub Actions docs](https://docs.github.com/en/actions)

---

## 14. Git Workflow

Git is how you track code changes, collaborate with others, and maintain a history of every decision. This section covers the basics and the branching strategy used in this project.

Git tracks every change to your code. Think of it as unlimited undo plus the ability to work on multiple features in parallel without breaking each other. [Git book](https://git-scm.com/book/en/v2)

### Key Concepts

| Concept | What it is |
|---------|-----------|
| Repository (repo) | Your project folder tracked by git |
| Commit | A snapshot of files at a point in time, with a descriptive message |
| Branch | A parallel line of development. main is production |
| Merge | Combining changes from one branch into another |
| Pull Request (PR) | A request to merge a branch into main. Triggers CI |
| Remote | The repo copy on GitHub (called origin) |

### Branching Strategy

1. Create a feature branch: git checkout -b feature/my-feature
2. Make changes, commit them
3. Push: git push origin feature/my-feature
4. Open PR on GitHub. CI runs automatically
5. Review, approve, merge to main
6. CI/CD auto-deploys to production

### Essential Commands

```bash
git status                          # What files changed?
git diff                            # See actual changes
git log --oneline -10               # Last 10 commits, one line each
git add file.py                     # Stage a file for commit
git commit -m "feat: add feature"   # Commit with message
git push origin branch-name         # Push to GitHub
git pull origin main                # Pull latest from main
git checkout -b feature/new-thing   # Create and switch to new branch
git stash                           # Temporarily shelve changes
git stash pop                       # Restore shelved changes
```

[GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow) | [Conventional commits](https://www.conventionalcommits.org/)

---

## 15. Monitoring and Observability

Monitoring tells you what the system is doing right now. Observability helps you figure out why something went wrong. This section covers the four monitoring tools in use and what each one watches.

### Stack Overview

```
Prometheus (on DB box, port 9090)
  Scrapes metrics every 45 seconds from:
    - Every web instance: Django request metrics (port 8000/metrics)
    - Every web instance: Node Exporter CPU/memory (port 9100)
    - DB box: PostgreSQL stats, Redis stats, container stats

Grafana (on DB box, port 3000)
  Visualizes Prometheus metrics and Loki logs in dashboards.

Loki (on DB box, port 3100)
  Receives logs from Promtail on each web instance.
  Retention: 7 days.

GlitchTip (on DB box, port 8000)
  Receives unhandled exceptions from Django's sentry-sdk.
```

### Prometheus Alert Rules

These are defined in deploy/db/alert_rules.yml:

- HighErrorRate: 5xx rate above 5% for 3 minutes (critical)
- HighP95Latency: p95 response time above 5 seconds for 3 minutes (warning)
- WebInstanceDown: Any web instance unreachable for 2 minutes (critical)
- CacheHitRateLow: Redis hit rate below 50% for 5 minutes (warning)
- RedisEvictions: Any evictions happening (warning)
- HighDBConnections: PostgreSQL connections above 150 (warning)

### Prometheus Auto-Discovery

Production Prometheus uses EC2 service discovery (ec2_sd_configs). It queries the EC2 API for instances tagged Role=web, and automatically scrapes new Spot instances as they launch and drops them when they terminate.

[Prometheus docs](https://prometheus.io/docs/introduction/overview/) | [Grafana docs](https://grafana.com/docs/grafana/latest/) | [Loki docs](https://grafana.com/docs/loki/latest/)

---

## 16. Django Admin, Grafana and GlitchTip

These are the three admin interfaces you will use day-to-day. This section tells you how to access each one and what you can do with it.

### Django Admin (/admin/)

Access: https://stagefreedom.org/admin/ (superuser credentials required)

What you can do:
- **Profiles:** View/edit any user's profile. Toggle client_approved to let a client hire. Toggle performer_blacklisted or client_blacklisted to block from platform. Filterable by all role flags.
- **Uploads:** View all uploaded media.
- **Users:** Standard user management (password reset, active/inactive, staff status).
- **Tokens:** View/manage DRF auth tokens (one per user).

Creating a superuser:

```bash
docker compose exec web python manage.py createsuperuser
```

### Grafana (http://DB_BOX_IP:3000)

1. Login with GRAFANA_USER / GRAFANA_PASSWORD from DB box .env
2. Go to Dashboards, browse, select Fleet Dashboard v2
3. Use the Instance dropdown to filter by specific web instance
4. Key metrics to watch:
   - RPS (Requests Per Second) — baseline traffic
   - 5xx Error Rate — should be below 1%. Red alert if above 5%
   - P95 Latency — should be below 2s. Warning if above 5s
   - Cache Hit Rate — should be above 70%
5. Explore tab with Loki lets you query logs: {service="web", host="ak-spot-i-abc123"}

### GlitchTip (http://DB_BOX_IP:8000)

1. Create account on first visit (first user becomes admin)
2. Errors appear in Issues tab, grouped by type
3. Each issue shows: stack trace, request URL, user info, frequency
4. Use it to catch 500 errors before users report them

---

## 17. Environment Variables Reference

Environment variables configure the application without changing code. This section documents every variable the app reads, what it controls, and what values to use.

### Web Instance (deploy/web/.env.example)

| Variable | Example | Purpose |
|----------|---------|---------|
| DJANGO_SECRET_KEY | (random 50+ chars) | Cryptographic signing key |
| DJANGO_DEBUG | 0 | Never 1 in production |
| DJANGO_ALLOWED_HOSTS | * | Hosts Django will serve |
| CSRF_TRUSTED_ORIGINS | https://stagefreedom.org | Origins allowed for CSRF |
| ENVIRONMENT | production | Sentry environment tag |
| DB_HOST | 172.31.6.148 | PostgreSQL host (VPC private IP) |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | createscale | Database name |
| DB_USER | createscale | Database user |
| DB_PASSWORD | (secret) | Database password |
| REDIS_URL | redis://172.31.6.148:6379/1 | Redis connection string |
| AWS_ACCESS_KEY_ID | (R2 key) | Cloudflare R2 access key |
| AWS_SECRET_ACCESS_KEY | (R2 secret) | Cloudflare R2 secret key |
| USE_S3 | 1 | Enable R2/S3 media storage |
| AWS_STORAGE_BUCKET_NAME | artkhoj-media | R2 bucket name |
| AWS_S3_REGION_NAME | auto | Region (auto for R2) |
| AWS_S3_ENDPOINT_URL | https://xxx.r2.cloudflarestorage.com | R2 endpoint |
| ACCOUNT_HTTP_PROTOCOL | https | allauth OAuth redirect URI scheme |
| GOOGLE_CLIENT_ID | (from Google Cloud Console) | Google OAuth |
| GOOGLE_CLIENT_SECRET | (secret) | Google OAuth |
| TWITTER_CLIENT_ID | (from Twitter Dev Portal) | Twitter OAuth |
| TWITTER_CLIENT_SECRET | (secret) | Twitter OAuth |
| LINKEDIN_CLIENT_ID | (from LinkedIn Developer) | LinkedIn OAuth |
| LINKEDIN_CLIENT_SECRET | (secret) | LinkedIn OAuth |
| SENTRY_DSN | http://key@172.31.6.148:8000/1 | GlitchTip error tracking |
| RUN_MIGRATIONS | 0 or 1 | 1 on OD only, 0 on Spot |
| WEB_CONCURRENCY | 3 | Gunicorn worker count |
| WEB_THREADS | 2 | Threads per worker |
| WEB_TIMEOUT | 30 | Request timeout in seconds |

### DB Instance (deploy/db/.env.example)

| Variable | Example | Purpose |
|----------|---------|---------|
| DB_NAME | createscale | PostgreSQL database name |
| DB_USER | createscale | PostgreSQL user |
| DB_PASSWORD | (secret) | PostgreSQL password |
| GLITCHTIP_SECRET_KEY | (64 random chars) | GlitchTip signing key |
| DB_HOST_PUBLIC_IP | x.x.x.x | Public IP for GlitchTip domain |
| GRAFANA_USER | admin | Grafana admin username |
| GRAFANA_PASSWORD | (secret) | Grafana admin password |

---

## 18. Common Commands Cheat Sheet

Quick reference for the commands you will use most often. Organized by context.

### Local Development

```bash
docker compose up -d                            # Start everything
docker compose logs -f web                      # Django/Gunicorn logs
docker compose logs -f nginx                    # Nginx logs
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py shell
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py seed_loadtest_v2   # Load test data
docker compose exec web pytest tests/test_layer1.py -v      # Run tests
docker compose build web                        # Rebuild after requirements change
docker compose down                             # Stop everything
```

### Production (via SSH or SSM)

```bash
# On web instance
cd /home/ubuntu/AK-WEB
docker compose -f docker-compose.web.yml logs -f web
docker compose -f docker-compose.web.yml ps
docker compose -f docker-compose.web.yml exec web env
docker compose -f docker-compose.web.yml restart web

# On DB box
cd /home/ubuntu/AK/deploy/db
docker compose -f docker-compose.data.yml logs -f db
docker compose -f docker-compose.data.yml logs -f redis

# Nginx (on OD, runs on bare metal)
sudo nginx -t                              # Validate config
sudo systemctl reload nginx                # Reload
sudo cat /etc/nginx/upstream.conf          # Current upstream servers
sudo journalctl -u nginx-discovery -f      # Upstream discovery logs
```

### AWS CLI

```bash
aws s3 cp web.env s3://createscale-config/web/.env --sse AES256   # Update .env
aws s3 ls s3://createscale-config/web/                             # List configs

aws ec2 describe-instances \
  --filters "Name=tag:Role,Values=web" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,PrivateIpAddress,InstanceLifecycle]" \
  --output table                                                    # List web fleet
```

### Expo (Mobile App)

```bash
cd createscale-app
npm install                     # Install dependencies
npx expo start                  # Start dev server
npx expo start --android        # Android emulator
npx expo start --ios            # iOS simulator
npx expo start --web            # Browser
npx expo install package-name   # Install Expo-compatible version
```

### Git

```bash
git status                          # What changed?
git diff                            # See actual changes
git log --oneline -10               # Recent history
git add file.py                     # Stage
git commit -m "feat: description"   # Commit
git push origin branch-name         # Push
git pull origin main                # Pull latest
git checkout -b feature/new-thing   # New branch
```

---

## 19. DOs and DON'Ts

Hard-won lessons. Some of these come from actual production incidents.

### AWS

| DO | DO NOT |
|----|--------|
| Use SSM for remote commands | Leave SSH port 22 open to 0.0.0.0/0 |
| Use IAM roles on EC2 (not hardcoded keys) | Put AWS credentials in code or committed files |
| Tag instances properly (Role=web) — Nginx discovery and Prometheus depend on it | Create instances without tags |
| Use VPC private IPs for inter-instance traffic | Use public IPs for internal traffic (costs money, higher latency) |
| Update the S3 canonical .env when adding new env vars | SSH into each instance and edit .env manually (causes drift) |
| Set RUN_MIGRATIONS=0 on Spot instances | Let multiple instances run migrations simultaneously |
| Use Spot for stateless web workers | Use Spot for the DB box (data loss on interruption) |
| Run docker system prune periodically | Let old images fill up the 20GB disk |
| Test launch template changes by terminating a Spot and watching ASG relaunch | Assume launch template changes work without testing |

### Django

| DO | DO NOT |
|----|--------|
| Use os.getenv() with sensible defaults | Hardcode config values in settings.py |
| Add DB indexes for fields you filter/sort on | Create indexes on every field (slows writes) |
| Use select_related() / prefetch_related() for foreign keys | Let N+1 queries silently kill performance |
| Cache expensive queries (we use Redis) | Cache user-specific data with a shared key |
| Run collectstatic on ALL instances | Skip it on Spot (ManifestStaticFilesStorage will crash) |
| Keep DEBUG=0 in production | Set DEBUG=1 in production (exposes settings, disables caching) |

### Docker

| DO | DO NOT |
|----|--------|
| Use specific image tags in production (createscale:abc123) | Use :latest blindly (no rollback path) |
| Run as non-root user inside containers (appuser) | Run as root in production |
| Clean up old images with docker system prune -a | Let dangling images fill disk |

### Security

| DO | DO NOT |
|----|--------|
| Rotate secrets after any exposure | Reuse exposed credentials |
| Use Cloudflare WAF rules (5 free rules available) | Leave Django admin publicly accessible without challenge |
| Use Argon2 for password hashing (already configured) | Downgrade to weaker hashing |
| Set SECURE_PROXY_SSL_HEADER when behind a reverse proxy | Trust X-Forwarded-Proto without configuring Django to read it |

### General

| DO | DO NOT |
|----|--------|
| Run makemigrations --check before pushing | Manually edit migration files |
| Use environment variables for secrets | Hardcode secrets anywhere |
| Test locally with docker compose up before pushing | Push untested code to main |
| Use feature branches | Push directly to main |

---

## 20. Further Reading

Curated links to official documentation for every technology in the stack. Bookmark these.

### Django
- [Official tutorial (start here)](https://docs.djangoproject.com/en/5.1/intro/tutorial01/)
- [Django REST Framework quickstart](https://www.django-rest-framework.org/tutorial/quickstart/)
- [django-allauth docs](https://docs.allauth.org/en/latest/)
- [WhiteNoise](https://whitenoise.readthedocs.io/en/latest/)
- [Gunicorn deployment](https://docs.gunicorn.org/en/stable/deploy.html)

### React Native / Expo
- [Expo getting started](https://docs.expo.dev/get-started/introduction/)
- [React Native fundamentals](https://reactnative.dev/docs/getting-started)
- [React hooks reference](https://react.dev/reference/react/hooks)
- [React Navigation](https://reactnavigation.org/docs/getting-started)
- [Expo AuthSession (OAuth)](https://docs.expo.dev/versions/latest/sdk/auth-session/)

### AWS
- [EC2 getting started](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html)
- [Auto Scaling Groups](https://docs.aws.amazon.com/autoscaling/ec2/userguide/auto-scaling-groups.html)
- [Launch Templates](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-templates.html)
- [IAM roles for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [SSM Run Command](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html)
- [Spot Instance best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html)

### Docker
- [Docker getting started](https://docs.docker.com/get-started/)
- [Dockerfile best practices](https://docs.docker.com/build/building/best-practices/)
- [Docker Compose overview](https://docs.docker.com/compose/)

### CI/CD
- [GitHub Actions quickstart](https://docs.github.com/en/actions/quickstart)
- [Workflow syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)

### Monitoring
- [Prometheus first steps](https://prometheus.io/docs/introduction/first_steps/)
- [Grafana fundamentals](https://grafana.com/tutorials/grafana-fundamentals/)
- [Loki overview](https://grafana.com/docs/loki/latest/get-started/overview/)
- [GlitchTip docs](https://glitchtip.com/documentation)

### Git
- [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [Pro Git book (free)](https://git-scm.com/book/en/v2)
- [Conventional commits](https://www.conventionalcommits.org/)

### Cloudflare
- [How Cloudflare works](https://developers.cloudflare.com/fundamentals/concepts/how-cloudflare-works/)
- [WAF custom rules](https://developers.cloudflare.com/waf/custom-rules/)
- [R2 storage](https://developers.cloudflare.com/r2/)

---

## Project Idiosyncrasies

Things that are not obvious and will bite you if you do not know about them.

1. **Two hiring systems coexist.** The Message model has a hiring_status field (the old approach). The Engagement model is the new, proper booking system. The old messaging-based hiring still works but is being phased out.

2. **django-appointment is installed but unused.** It is in requirements.txt but NOT in INSTALLED_APPS. We built a custom Engagement model instead. Do not remove it from requirements yet — it may be evaluated later.

3. **LinkedIn adapter is custom.** allauth's built-in LinkedIn adapter uses deprecated V1 endpoints. Our linkedin_adapter.py overrides it with OIDC v2. If allauth updates their adapter, we may be able to remove ours.

4. **Silk profiling is 0% in production.** The middleware is always loaded but SILKY_INTERCEPT_PERCENT=0 in prod. Zero overhead but ready to toggle on for debugging.

5. **EnsureProfileMiddleware runs on EVERY request.** It calls Profile.objects.get_or_create() on every authenticated request. This is a safety net for OAuth signups that might skip the signal. It is a DB hit per request, but it is a single indexed lookup.

6. **OD box repo is on a feature branch.** The repo at /home/ubuntu/AK on the OD instance is on Scale_Out_v1, not main. git pull origin main merges main into it. Known quirk.

7. **SSM logs in as ssm-user, not ubuntu.** When CI/CD runs commands via SSM, it runs as ssm-user. Files owned by ubuntu need sudo to access.

8. **Prometheus multiprocess mode.** Gunicorn forks workers, which breaks Prometheus's default in-process metrics. The entrypoint creates a shared /tmp/metrics directory. This also means process_cpu_seconds_total does not work — that is why we run node_exporter separately for host-level CPU and memory.

9. **Static files served by WhiteNoise, not Nginx.** Nginx has no /static/ location block. All static requests proxy through to Django, where WhiteNoise middleware intercepts them. This works because static files are inside the Docker container where host Nginx cannot reach them.

10. **manifest_strict = False.** Our custom ForgivingStaticFilesStorage will not crash if a template references a missing static file. It returns the unhashed URL instead. This prevents a single missing image from taking down the entire page.

11. **c7g.large = 2 CPUs, 4GB RAM.** Gunicorn is tuned for this: 3 workers times 2 threads = 6 concurrent requests per instance. Do not increase workers beyond (2 times CPU + 1) without also increasing instance size.

12. **Cloudflare Flexible SSL.** SSL terminates at Cloudflare. Traffic between Cloudflare and Nginx is HTTP. X-Forwarded-Proto is hardcoded to https in Nginx (not $scheme). Django reads it via SECURE_PROXY_SSL_HEADER.

13. **Redis has no persistence.** It is a pure cache. If Redis restarts, all cached data is lost. Sessions use cached_db backend (Redis plus PostgreSQL), so session data survives Redis restarts.
