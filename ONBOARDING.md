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
9. [Payments and Payouts](#9-payments-and-payouts)
10. [React Native / Expo Frontend](#10-react-native--expo-frontend)
11. [Docker and Containerization](#11-docker-and-containerization)
12. [AWS Infrastructure](#12-aws-infrastructure)
13. [Nginx and Load Balancing](#13-nginx-and-load-balancing)
14. [CI/CD Pipeline](#14-cicd-pipeline)
15. [Git Workflow](#15-git-workflow)
16. [Monitoring and Observability](#16-monitoring-and-observability)
17. [Django Admin, Grafana and GlitchTip](#17-django-admin-grafana-and-glitchtip)
18. [Environment Variables Reference](#18-environment-variables-reference)
19. [Common Commands Cheat Sheet](#19-common-commands-cheat-sheet)
20. [DOs and DON'Ts](#20-dos-and-donts)
21. [Further Reading](#21-further-reading)
22. [Kubernetes and k3s Infrastructure](#22-kubernetes-and-k3s-infrastructure)

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

## 9. Payments and Payouts

Money moves through **Razorpay Route** — an escrow-style payout system.

Clients pay upfront. The platform holds the **performer's share** in escrow until the event completes, then releases it. If something goes wrong, it refunds instead.

This section covers KYC onboarding, checkout, refunds, disputes, webhooks, and scheduled payouts.

### Architecture — Razorpay Escrow

All payments use [Razorpay Route](https://razorpay.com/docs/route/) with held transfers. When a client pays, the amount splits immediately:

- **Platform fee** (default 5%) — available at capture time
- **Performer's share** — placed on hold (`on_hold=1`) in Razorpay's ledger

The hold releases only after the **event date + 24h dispute window**. If cancelled, Razorpay unwinds the transfer and refunds the full amount.

```
Client pays ₹1000 (total)
         │
         ▼
   Razorpay captures ₹1000
         │
    ┌────┴────┐
    ▼         ▼
₹50          ₹950
(platform    (performer's share)
 fee 5%)          │
available     held in escrow
 immediately   (on_hold=1)
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   Event OK              Cancellation
   + 24h passes          or dispute
        │                     │
        ▼                     ▼
   release_to_performer()   refund_to_client()
   (unhold transfer)        (reverse_all=1)
        │                     │
        ▼                     ▼
   Performer gets ₹950     Client gets ₹1000 back
```

### Engagement Payment State Machine

The `payment_status` field on the Engagement model tracks the money lifecycle through these states:

```
unpaid ──(pay)──→ paid ──(release)────→ released
                     │
                     ├──(cancel)──────→ refunded
                     │
                     └──(dispute)────→ [stays paid, escrow frozen]
```

- **unpaid** — No payment started. Engagements expire if unpaid past `payment_deadline()`.
- **paid** — Client paid. Money held in Razorpay escrow.
- **released** — Performer received their share. Platform fee already settled.
- **refunded** — Full amount returned to client via `reverse_all=1`.
- **disputed** — Client raised an issue. Money stays frozen until admin resolves.

### Performer KYC Onboarding (users/models.py, users/views.py)

Performers must complete **Razorpay Route KYC** before they can receive payments. All fields live on the `Profile` model:

- **`performer_fee`** (`PositiveIntegerField`, 500–500,000 INR) — Standard fee. Snapshotted at hire time.
- **`razorpay_account_id`** (`CharField(64)`, unique) — Route linked account ID. Set after creation.
- **`razorpay_kyc_status`** (`CharField`) — `""` → `"pending"` → `"approved"` / `"rejected"`
- **`pan_number`** (`CharField(10)`, regex validated) — Permanent Account Number
- **`bank_account_number`** (`CharField(20)`) — Bank account for payouts
- **`bank_ifsc`** (`CharField(11)`, regex validated) — IFSC code
- **`bank_account_holder_name`** (`CharField(120)`) — Name on bank account
- **`phone_number`** (`CharField(10)`, regex validated) — Indian mobile (required by Razorpay)

**KYC flow** (`users/views.py:update_payment_details`):

1. Performer submits `PaymentDetailsForm` (PAN, bank, phone, fee)
2. If all fields filled + no existing `razorpay_account_id` → creates a Razorpay Route linked account via `client.account.create()`
3. Saves `razorpay_account_id` and `razorpay_kyc_status = "pending"` to the Profile
4. Razorpay reviews the KYC (5-7 business days)
5. Status webhook not yet implemented — updates may be manual

**Gate:** `Profile.can_receive_payments` returns `True` only when both `razorpay_account_id` is set **and** `razorpay_kyc_status == "approved"`. `PaymentService.create_order()` rejects unapproved performers.

### Payment Models (bookings/models.py)

Two models track payment data.

**Engagement** — payment fields on the engagement itself:

- **`fee`** (`PositiveIntegerField`) — Snapshot of performer's fee at hire time. Immutable.
- **`payment_status`** (`CharField`) — `unpaid` → `paid` → `released` / `refunded`
- **`accepted_at`** (`DateTimeField`) — Starts the payment deadline clock
- **`paid_at`** (`DateTimeField`, indexed) — When Razorpay captured the payment
- **`released_at`** (`DateTimeField`) — When money reached the performer
- **`refunded_at`** (`DateTimeField`) — When money returned to the client
- **`disputed_at`** (`DateTimeField`) — Client raised a dispute
- **`dispute_reason`** (`TextField`) — 10–1000 char description
- **`dispute_resolved_at`** (`DateTimeField`) — Admin resolved it

Key methods:

- `payment_deadline()` — Deadline for the client to pay. **24h after `accepted_at`**, clamped to `event_time - 2h` for short-notice bookings. Controlled by `RAZORPAY_PAYMENT_WINDOW_HOURS`.
- `can_dispute` — `True` when `payment_status == "paid"`, no prior dispute, and within 24h of event end (`RAZORPAY_DISPUTE_WINDOW_HOURS`).

**Payment** — Razorpay audit trail. One Engagement can have multiple Payment rows (failed attempts, retries). The latest `status="captured"` row is the source of truth:

- **`engagement`** (`ForeignKey`) — Parent engagement
- **`amount`** (`PositiveIntegerField`) — Total in rupees
- **`platform_fee`** (`PositiveIntegerField`) — ArtKhoj's cut
- **`performer_share`** (`PositiveIntegerField`) — `amount - platform_fee`
- **`razorpay_order_id`** (`CharField`, unique) — Razorpay Order ID
- **`razorpay_payment_id`** (`CharField`, indexed) — Populated after capture
- **`razorpay_transfer_id`** (`CharField`, indexed) — Populated on transfer
- **`razorpay_refund_id`** (`CharField`, indexed) — Populated on refund
- **`status`** (`CharField`) — `created` → `captured` → `released` / `refunded` / `failed`
- **`raw_webhook_log`** (`JSONField`) — Append-only webhook audit trail

### Checkout Flow (bookings/views.py, bookings/services/payments.py)

A two-step flow between frontend and backend:

**Step 1 — `POST /engagement/<pk>/pay/` (Create Order)**

```
Frontend                         Backend
   │                                │
   │── POST /pay/ ──────────────→   │
   │                                │── Validate: unpaid, fee set, KYC approved
   │                                │── Split fee via _split_amount()
   │                                │── Create Razorpay Order + held transfer
   │                                │── Persist Payment(status="created")
   │←── {order_id, amount,         │
   │     currency, key_id} ──────   │
```

1. `PaymentService.create_order()` validates the engagement is unpaid, fee is set, and performer is KYC-approved
2. `_split_amount()` divides the total into `(platform_fee, performer_share)` using `RAZORPAY_PLATFORM_FEE_PERCENT`
3. Creates a Razorpay Order with a held transfer to the performer's linked account
4. Persists a `Payment` row with `status="created"`
5. Returns `{order_id, amount, currency, key_id}` for the frontend to open the Razorpay modal

**Step 2 — `POST /engagement/<pk>/verify/` (Verify and Capture)**

```
Frontend                         Backend
   │                                │
   │── checkout.js handler ─────→   │
   │   {order_id, payment_id,       │
   │    signature}                  │
   │                                │── Verify HMAC-SHA256 signature
   │                                │── select_for_update() row lock
   │                                │── Mark Payment "captured"
   │                                │── Mark Engagement "paid"
   │←── reload page ────────────   │
```

1. Razorpay checkout.js calls the handler with `{razorpay_order_id, razorpay_payment_id, razorpay_signature}`
2. Backend verifies **HMAC-SHA256** using `RAZORPAY_KEY_SECRET`
3. `select_for_update()` row lock ensures idempotency
4. `Payment.status = "captured"` and `Engagement.payment_status = "paid"`
5. Performer's share stays on hold in Razorpay

**Checkout JS** (in `engagement_detail.html`):

```javascript
fetch(`/engagement/${pk}/pay/`, { method: "POST" })
  .then(r => r.json())
  .then(order => {
    var options = {
      key: order.key_id,
      amount: order.amount,
      currency: order.currency,
      order_id: order.order_id,
      handler: function(response) {
        fetch(`/engagement/${pk}/verify/`, {
          method: "POST", body: JSON.stringify(response)
        }).then(() => location.reload());
      }
    };
    var rzp = new Razorpay(options);
    rzp.open();
  });
```

### Refunds (bookings/services/payments.py)

`PaymentService.refund_to_client()` fires when a **paid** engagement is cancelled:

- Calls Razorpay API with `reverse_all=1` → unwinds the held transfer → full refund to client
- Sets `Payment.status = "refunded"` and `Engagement.payment_status = "refunded"`
- **Idempotent** — no-op if already refunded
- Fires **synchronously** from the `engagement_detail` web view (`bookings/views.py:230-231, 245-246`)

> ⚠️ **API gap:** `bookings/api/views.py` calls the model's cancel methods but **not** `refund_to_client()`. API cancellations of paid engagements leave money stuck in escrow.

### Disputes (bookings/views.py, bookings/forms.py)

Clients can raise a dispute **within 24h** of the event end time:

1. Client submits `DisputeForm` (10–1000 chars) via `POST /engagement/<pk>/dispute/`
2. Guard: must be `paid`, no existing dispute, still within the window (`can_dispute`)
3. Engagement gets `disputed_at` + `dispute_reason` set
4. Celery release task **skips** disputed engagements — money stays frozen
5. Admin resolves in Django admin: sets `dispute_resolved_at`, then refunds or releases manually

### Scheduled Tasks (bookings/tasks.py)

Two Celery tasks handle time-based payment automation:

- **`expire_unpaid_engagements()`** — Hourly. Marks accepted-but-unpaid engagements past `payment_deadline()` as `auto_expired`.
- **`release_completed_event_payouts()`** — Daily 02:00. Releases payouts for paid engagements where the event + 24h dispute window has passed. Skips disputed engagements.

### Webhooks (bookings/views.py, bookings/services/payments.py)

Razorpay sends webhook events to `POST /webhook/razorpay/` (CSRF-exempt, HMAC-verified):

- **`payment.captured`** → `PaymentService.mark_captured_from_webhook()` — marks as captured (backup path when verify step is missed)
- **`refund.processed`** → Updates `Payment.status` to `refunded`
- **`transfer.processed`** → Updates `Payment.status` to `released`

The webhook endpoint:

1. Reads the raw body and `X-Razorpay-Signature` header
2. Verifies HMAC-SHA256 using `RAZORPAY_WEBHOOK_SECRET`
3. Routes to the appropriate handler
4. All webhook payloads are logged to `Payment.raw_webhook_log` for audit

### Service Layer (bookings/services/)

**`bookings/services/payments.py`** — the `PaymentService` class:

- **`_split_amount(total)`** — Divides into `(platform_fee, performer_share)` by `RAZORPAY_PLATFORM_FEE_PERCENT`
- **`create_order(engagement)`** — Creates Razorpay Order + held transfer, saves Payment row
- **`verify_and_capture(order_id, payment_id, sig)`** — HMAC check + capture with row lock
- **`mark_captured_from_webhook(order_id, payment_id)`** — Same, no HMAC (already verified upstream)
- **`release_to_performer(engagement)`** — Unholds the transfer
- **`refund_to_client(engagement)`** — Full refund via `reverse_all=1`
- **`verify_webhook_signature(raw_body, sig)`** — HMAC-SHA256 for webhooks
- **`handle_webhook_event(event)`** — Routes to the right handler

**`bookings/services/razorpay_client.py`** — lazy Razorpay SDK init. Raises `RuntimeError("Razorpay is not configured")` if keys are missing. Uses lazy import to dodge the `pkg_resources` issue with setuptools 70+.

### Configuration

All payment settings are read from environment variables in `myproject/settings.py`:

- **`RAZORPAY_KEY_ID`** (empty) — Razorpay API key ID
- **`RAZORPAY_KEY_SECRET`** (empty) — Razorpay API key secret
- **`RAZORPAY_WEBHOOK_SECRET`** (empty) — Secret for HMAC webhook verification
- **`RAZORPAY_PLATFORM_FEE_PERCENT`** (default `5`) — Percentage deducted as platform fee
- **`RAZORPAY_PAYMENT_WINDOW_HOURS`** (default `24`) — Hours client has to pay after acceptance
- **`RAZORPAY_DISPUTE_WINDOW_HOURS`** (default `24`) — Hours after event to raise a dispute

### Known Gaps

1. **No API refund on cancel** — `bookings/api/views.py` skips `refund_to_client()`. Money stays stuck in escrow on API cancellations.
2. **No KYC webhook handler** — `razorpay_kyc_status` stays `"pending"` forever. KYC updates must be manual.
3. **No partial refunds** — only full refunds with `reverse_all=1`. Can't refund part of a booking.
4. **Synchronous refunds** — `refund_to_client()` calls Razorpay during the HTTP request. Slow for large refunds.

---

## 10. React Native / Expo Frontend

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

## 11. Docker and Containerization

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

## 12. AWS Infrastructure

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

## 13. Nginx and Load Balancing

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

## 14. CI/CD Pipeline

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

## 15. Git Workflow

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

## 16. Monitoring and Observability

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

## 17. Django Admin, Grafana and GlitchTip

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

## 18. Environment Variables Reference

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

## 19. Common Commands Cheat Sheet

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

## 20. DOs and DON'Ts

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

## 21. Further Reading

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

## 22. Kubernetes and k3s Infrastructure

The application runs on **k3s** — a lightweight Kubernetes distribution — on Hetzner Cloud servers in Singapore. This section explains Kubernetes from scratch: why we use it, how it works, what every manifest does, how pods scale, how nodes scale, and how to operate the cluster. By the end you should be able to read, modify, and write your own manifests.

### The Big Picture

Before Kubernetes, we ran Docker containers directly on AWS EC2 instances. Nginx discovered Spot instances by polling the EC2 API. Scaling meant launching new VMs, waiting for boot scripts, and hoping Nginx picked them up. If a container crashed, nothing restarted it. If a VM died, traffic hit a dead backend until Nginx's health check noticed (up to 10 seconds).

Kubernetes replaces all of that with a single system that:

1. **Runs your containers** and restarts them if they crash
2. **Scales pods** (containers) up/down based on CPU usage — automatically
3. **Scales nodes** (servers) up/down based on pod demand — automatically
4. **Routes traffic** to healthy pods only (built-in load balancing)
5. **Rolls out new versions** with zero downtime
6. **Self-heals** — if a node dies, pods are rescheduled to surviving nodes

```
Internet
  │
  ▼
Cloudflare (SSL, DDoS, CDN)
  │
  ▼
AWS Global Accelerator (3.33.130.190)
  │
  ▼
Hetzner Load Balancer (5.223.35.241)
  │
  ▼ (targets servers labeled role=k3s)
  │
  ├────────────────────────────────────────────┐
  │                                            │
  ▼                                            ▼
k3s Master Node (5.223.45.51)           Worker Nodes (auto-scaled)
CPX22 · 3 CPU · 4GB · 10.0.0.3         CPX22 · 3 CPU · 4GB · 10.0.0.x
  │                                            │
  ├─ Traefik (ingress controller)              ├─ Django pods (fleet)
  ├─ Django pod (resident)                     ├─ Node Exporter
  ├─ Celery Worker                             └─ Promtail
  ├─ Celery Beat
  ├─ Prometheus Agent                    Created/destroyed by
  ├─ Cluster Autoscaler                  Cluster Autoscaler based
  ├─ Node Exporter                       on pod demand
  └─ Promtail

      Private Network: 10.0.0.0/16 (artkhoj-net)
      All inter-node traffic stays on this network.
      DB box (10.0.0.2) is on the same private net.
```

### Why k3s and Not Full Kubernetes (k8s)?

**Kubernetes (k8s)** is a container orchestration platform originally built by Google for managing thousands of servers. Full k8s requires multiple control-plane nodes, etcd clusters, and significant memory overhead — overkill for a small fleet.

**k3s** is a certified Kubernetes distribution by Rancher (now SUSE) that strips out the bloat:

| | Full k8s | k3s |
|---|---|---|
| Control plane RAM | ~2 GB | ~512 MB |
| Binary size | ~300 MB + many components | Single ~60 MB binary |
| Default ingress | None (install yourself) | Traefik (built-in) |
| Default storage | None | SQLite or embedded etcd |
| Container runtime | containerd (configurable) | containerd (built-in) |
| Certificate management | Manual setup | Auto-generated |
| Certified Kubernetes? | Yes | Yes — passes the same conformance tests |

k3s runs the exact same Kubernetes API. Every `kubectl` command, every manifest, every Helm chart works identically. The difference is operational — k3s is easier to install, uses less memory, and has sane defaults.

**Why we chose it:** Our fleet is 1 master + up to 15 workers. We do not need multi-master HA or complex networking plugins. k3s gives us real Kubernetes without the operational tax.

### Core Concepts

Before reading manifests, you need to understand six concepts. Everything else builds on these.

| Concept | What it is | Analogy |
|---------|-----------|---------|
| **Cluster** | The entire system — master + all workers | The whole fleet of servers |
| **Node** | A single server in the cluster. Master nodes run the control plane. Worker nodes run your app. | One server (like one EC2 instance) |
| **Pod** | The smallest deployable unit. Contains one or more containers sharing a network. Usually 1 pod = 1 container. | One running Docker container |
| **Namespace** | A virtual partition of the cluster. Keeps resources organized and isolated. | A folder — `artkhoj` for our app, `kube-system` for k8s internals |
| **Manifest** | A YAML file that declares the desired state ("I want 3 Django pods"). Kubernetes makes reality match. | A Dockerfile, but for infrastructure |
| **Label** | Key-value tag on any resource. Used for selecting, filtering, and connecting resources. | Tags on AWS resources |

**The key mental model:** You do not tell Kubernetes what to do step-by-step. You tell it what you want (declarative), and it figures out how to get there. If you say "I want 3 replicas" and a pod crashes, Kubernetes launches a new one. You never say "start a container" — you say "I want this deployment to exist" and Kubernetes handles the rest.

### Our Nodes

The cluster runs on Hetzner Cloud in Singapore (`sin` region):

| Node | Role | IP (private) | IP (public) | What runs on it |
|------|------|-------------|------------|-----------------|
| k3s master | Control plane + workloads | 10.0.0.3 | 5.223.45.51 | Traefik, resident Django pod, Celery, Prometheus, autoscaler |
| web-pool workers | Workloads only | 10.0.0.x | auto-assigned | Fleet Django pods, Node Exporter, Promtail |
| DB box | Not part of k3s | 10.0.0.2 | (has public IP) | PostgreSQL, Redis, Grafana, Loki, Prometheus server |

The master runs the Kubernetes API server, scheduler, and controller manager. Workers only run pods. The DB box is a standalone server on the same private network — not managed by Kubernetes.

**Private networking:** All nodes connect via Hetzner's private network `artkhoj-net` (10.0.0.0/16). Pod-to-pod traffic, metrics scraping (Prometheus), and database connections all use private IPs. Public IPs are only used for the Hetzner Load Balancer to reach nodes and for SSH access.

When a new worker boots, its cloud-init script:
1. Configures the private network interface (`enp7s0`)
2. Sets up k3s-agent to use the private IP
3. Labels the server in Hetzner's API (`role=k3s`) so the load balancer targets it
4. Starts k3s-agent, which joins the cluster

### Anatomy of a Manifest

Every Kubernetes manifest is a YAML file with four top-level fields:

```yaml
apiVersion: apps/v1          # Which API group and version
kind: Deployment              # What type of resource
metadata:                     # Name, namespace, labels
  name: django
  namespace: artkhoj
spec:                         # The actual specification (varies by kind)
  replicas: 1
  ...
```

**apiVersion** tells Kubernetes which schema to validate against. Common ones:
- `v1` — core resources (Namespace, Service, Secret, ConfigMap, Pod)
- `apps/v1` — workloads (Deployment, DaemonSet)
- `batch/v1` — batch jobs (Job, CronJob)
- `autoscaling/v2` — autoscaling (HorizontalPodAutoscaler)
- `networking.k8s.io/v1` — networking (Ingress)
- `rbac.authorization.k8s.io/v1` — permissions (ClusterRole, ClusterRoleBinding)

**kind** is the resource type. The next section covers every kind we use.

### Resource Kinds — What We Use and Why

Our cluster uses 11 resource types across 16 manifest files in `deploy/k8s/`. Here is every kind, what it does, and a real example from our codebase.

---

#### Namespace (`00-namespace.yaml`)

A namespace is a virtual partition. Resources in one namespace cannot accidentally interfere with resources in another.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: artkhoj
```

Our app lives in `artkhoj`. Kubernetes system components live in `kube-system`. When you run `kubectl` commands, you almost always need `-n artkhoj` or `-n kube-system` to specify which namespace.

---

#### Deployment (`11-deployment-web.yaml`, `11b-deployment-web-resident.yaml`, `12-deployment-worker.yaml`, `13-deployment-beat.yaml`)

A Deployment manages a set of identical pods. You declare how many replicas you want, what container image to run, and Kubernetes maintains that count. If a pod crashes, the Deployment creates a new one.

Here is our main Django deployment (`11-deployment-web.yaml`), annotated:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: django                    # Name of this deployment
  namespace: artkhoj              # Lives in the artkhoj namespace
spec:
  replicas: 1                     # Start with 1 pod (HPA scales this up)
  selector:
    matchLabels:                  # "This deployment manages pods with these labels"
      app: django
      role: fleet
  strategy:
    type: RollingUpdate           # Replace pods one-by-one, not all at once
    rollingUpdate:
      maxUnavailable: 0           # Never kill a pod before its replacement is ready
      maxSurge: 1                 # Launch 1 extra pod during updates
  template:                       # Template for the pods this deployment creates
    metadata:
      labels:
        app: django               # These labels must match selector above
        role: fleet               # "fleet" = runs on workers, scaled by HPA
    spec:
      affinity:
        nodeAffinity:             # WHERE to schedule these pods
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: node-role.kubernetes.io/control-plane
                    operator: DoesNotExist    # NOT on the master node
      containers:
        - name: django
          image: ghcr.io/datatwine/createscale:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: artkhoj-env   # All env vars from a Kubernetes Secret
          resources:
            requests:               # "I need at least this much"
              cpu: "250m"           # 250 millicpu = 25% of one CPU core
              memory: "512Mi"       # 512 megabytes
            limits:                 # "Never exceed this"
              cpu: "1"              # 1 full CPU core
              memory: "1Gi"         # 1 gigabyte
          startupProbe:             # "Is the container booting up?"
            httpGet:
              path: /metrics
              port: 8000
            failureThreshold: 30    # Try 30 times (30 × 5s = 150s max boot time)
            periodSeconds: 5
          readinessProbe:           # "Can this pod accept traffic?"
            httpGet:
              path: /metrics
              port: 8000
            periodSeconds: 5
          livenessProbe:            # "Is this pod still alive?"
            httpGet:
              path: /metrics
              port: 8000
            periodSeconds: 15
```

**Key details:**

- **`selector.matchLabels`** connects the Deployment to its pods. The Deployment only manages pods whose labels match.
- **`role: fleet`** vs **`role: resident`**: Fleet pods run on workers and are scaled by HPA. The resident pod (`11b-deployment-web-resident.yaml`) runs on the master (operator: `Exists` instead of `DoesNotExist`) and is NOT scaled — it is a safety net so the master always serves traffic even if all workers die.
- **Resources**: `requests` are guaranteed minimums (used for scheduling decisions). `limits` are hard caps (pod is killed if it exceeds memory limit). CPU is measured in millicores — `250m` = 0.25 CPU cores.
- **Probes**: `startupProbe` runs during boot (generous timeout). Once passed, `readinessProbe` and `livenessProbe` take over. If `readinessProbe` fails, the pod is removed from the Service (no traffic). If `livenessProbe` fails, the pod is killed and restarted.
- **`envFrom: secretRef`**: All environment variables come from a Kubernetes Secret named `artkhoj-env`. This replaces the `.env` file from the Docker Compose setup.

**Celery Worker** (`12-deployment-worker.yaml`) and **Celery Beat** (`13-deployment-beat.yaml`) are the same pattern — different `command`, different resource limits, no probes (they do not serve HTTP). Beat uses `strategy: Recreate` because only one beat scheduler should run at a time (no rolling update).

---

#### Service (`20-service-web.yaml`)

A Service gives pods a stable internal address. Pods come and go (scaling, crashes, updates), but the Service name stays constant.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: django
  namespace: artkhoj
spec:
  selector:
    app: django              # Route traffic to ALL pods with label app=django
  ports:
    - port: 8000
      targetPort: 8000
```

Any pod in the cluster can reach Django at `django.artkhoj.svc.cluster.local:8000` (or just `django:8000` from within the same namespace). The Service load-balances across all pods matching `app: django` — both `role: fleet` and `role: resident` pods receive traffic.

Think of a Service as the Kubernetes equivalent of Nginx's upstream block — but automatic. No discovery scripts, no config reloads.

---

#### Ingress (`21-ingress-web.yaml`)

An Ingress exposes a Service to the outside world by defining routing rules. It tells the ingress controller (Traefik, in our case) how to route external HTTP requests to internal Services.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: artkhoj
  namespace: artkhoj
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: >-
      artkhoj-sec-headers@kubernetescrd,
      artkhoj-body-limit@kubernetescrd,
      artkhoj-gzip@kubernetescrd
spec:
  rules:
    - host: stagefreedom.org
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: django
                port:
                  number: 8000
```

This says: "Requests to `stagefreedom.org/*` go to the `django` Service on port 8000." The annotations attach Traefik middlewares for security headers, body size limits, and gzip compression — the same things Nginx config used to handle.

**Traefik** is k3s's built-in ingress controller. It replaces Nginx. It watches for Ingress resources and automatically configures routing. No config files to edit, no reload commands to run.

---

#### Middleware (`22-middlewares.yaml`)

Traefik middlewares are the equivalent of Nginx config directives. They are Kubernetes custom resources (CRDs) specific to Traefik.

```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: sec-headers
  namespace: artkhoj
spec:
  headers:
    customResponseHeaders:
      X-Content-Type-Options: "nosniff"
      X-Frame-Options: "DENY"
      Referrer-Policy: "strict-origin-when-cross-origin"
```

We have three middlewares: `sec-headers` (security headers), `body-limit` (max upload size 25MB), and `gzip` (compression). They are referenced by name in the Ingress annotations.

---

#### Job (`10-job-migrate.yaml`)

A Job runs a container to completion and then stops. Unlike a Deployment (which keeps pods running forever), a Job runs once and exits.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: django-migrate
  namespace: artkhoj
spec:
  backoffLimit: 3                # Retry up to 3 times if it fails
  template:
    spec:
      restartPolicy: Never       # Do not restart on failure (let backoffLimit handle it)
      containers:
        - name: migrate
          image: ghcr.io/datatwine/createscale:latest
          command: ["python", "manage.py", "migrate", "--noinput"]
          envFrom:
            - secretRef:
                name: artkhoj-env
```

CI/CD deletes the old Job and creates a new one on each deploy. This runs `python manage.py migrate` exactly once per deployment.

---

#### DaemonSet (`41-daemonset-node-exporter.yaml`)

A DaemonSet runs exactly one pod on every node in the cluster. When a new worker joins, the DaemonSet automatically schedules a pod on it. When a worker is removed, the pod goes with it.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: artkhoj
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    spec:
      hostNetwork: true          # Use the node's network, not pod networking
      containers:
        - name: node-exporter
          image: prom/node-exporter:v1.8.1
          ports:
            - containerPort: 9100
              hostPort: 9100     # Expose on the node's IP directly
          volumeMounts:          # Mount host filesystem (read-only) to read CPU/memory
            - name: proc
              mountPath: /host/proc
              readOnly: true
            - name: sys
              mountPath: /host/sys
              readOnly: true
```

Node Exporter collects CPU, memory, and load metrics from each node. Prometheus scrapes it at port 9100. `hostNetwork: true` means the pod uses the node's IP address directly — necessary because Prometheus needs to reach each node individually.

Promtail (`40-daemonset-promtail.yaml`) is also a DaemonSet — it ships container logs from every node to Loki on the DB box.

---

#### HorizontalPodAutoscaler (`30-hpa-web.yaml`)

HPA scales the **number of pods** based on metrics. It watches CPU usage and adjusts the Deployment's replica count.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: django-hpa
  namespace: artkhoj
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: django                 # Which deployment to scale
  minReplicas: 1
  maxReplicas: 60                # Upper bound
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60   # Target: 60% average CPU across all pods
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0    # Scale up immediately
      policies:
        - type: Percent
          value: 100                   # Double the pod count per 30s
          periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 600  # Wait 10 minutes before scaling down
      policies:
        - type: Pods
          value: 2                     # Remove max 2 pods per 60s
          periodSeconds: 60
```

**How it works:**
1. HPA checks average CPU across all `django` pods every 15 seconds
2. If average CPU > 60%, it calculates how many pods are needed to bring it to 60%
3. It updates the Deployment's replica count
4. The Deployment creates new pods
5. Scale-up is aggressive (double every 30s, no stabilization). Scale-down is conservative (wait 10 minutes, remove 2 at a time). This prevents flapping — scaling up fast for traffic spikes, scaling down slowly to avoid premature removal.

**HPA vs Cluster Autoscaler:** HPA scales **pods** (containers). If there are not enough nodes to run the new pods, they sit in `Pending` state. That is where the Cluster Autoscaler comes in — it watches for Pending pods and adds new servers.

---

#### ConfigMap and Secret

**ConfigMap** stores non-sensitive configuration. **Secret** stores sensitive data (encoded in base64).

Our Prometheus agent config (`60-prometheus-agent.yaml`) uses a ConfigMap:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-agent-config
  namespace: artkhoj
data:
  prometheus.yml: |
    global:
      scrape_interval: 45s
    remote_write:
      - url: http://10.0.0.2:9090/api/v1/write    # DB box private IP
    scrape_configs:
      - job_name: 'web-fleet'
        kubernetes_sd_configs:
          - role: pod
        ...
```

The ConfigMap is mounted as a file inside the Prometheus container. Prometheus reads it as `/etc/prometheus/prometheus.yml`.

Our app's environment variables live in a Secret named `artkhoj-env`. Every Deployment references it via `envFrom: secretRef`. This is the k3s equivalent of the `.env` file — but managed by Kubernetes instead of sitting on disk.

> **Warning:** `01-secret.example.yaml` is an EXAMPLE file with placeholder values. NEVER apply it to the cluster — it will overwrite the real secret with dummy values. The real secret was created manually on the master with `kubectl create secret`.

---

#### RBAC — ServiceAccount, ClusterRole, ClusterRoleBinding (`50-rbac-prometheus.yaml`)

RBAC (Role-Based Access Control) controls what pods are allowed to do inside the cluster. By default, pods cannot query the Kubernetes API. Prometheus needs to discover pods for scraping, so it needs explicit permission.

```yaml
# 1. Create a service account (an identity for the pod)
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus-discovery
  namespace: artkhoj

# 2. Create a role defining what actions are allowed
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prometheus-discovery
rules:
  - apiGroups: [""]
    resources: ["nodes", "pods", "endpoints", "services"]
    verbs: ["get", "list", "watch"]       # Read-only access

# 3. Bind the role to the service account
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prometheus-discovery
roleRef:
  kind: ClusterRole
  name: prometheus-discovery
subjects:
  - kind: ServiceAccount
    name: prometheus-discovery
    namespace: artkhoj
```

The Prometheus Deployment then uses `serviceAccountName: prometheus-discovery` in its pod spec. This gives it permission to list pods — which is how Prometheus discovers Django pods and Node Exporter pods automatically using `kubernetes_sd_configs`.

---

### The Two Autoscalers — Pods vs Nodes

Scaling in Kubernetes happens at two levels, and two separate systems handle them:

```
Traffic increases
       │
       ▼
HPA detects high CPU (>60% average)
       │
       ▼
HPA increases Deployment replicas (e.g., 3 → 8 pods)
       │
       ▼
Scheduler tries to place new pods on nodes
       │
       ├── Nodes have room → pods start immediately
       │
       └── No room → pods stuck in "Pending"
                │
                ▼
       Cluster Autoscaler detects Pending pods
                │
                ▼
       Autoscaler provisions new Hetzner server
                │
                ▼
       Server boots, joins cluster (~90 seconds)
                │
                ▼
       Scheduler places Pending pods on new node
```

| | HPA (Pod Autoscaler) | Cluster Autoscaler (Node Autoscaler) |
|---|---|---|
| Scales | Pods (containers) | Nodes (servers) |
| Trigger | CPU > 60% average | Pods stuck in Pending |
| Config location | `deploy/k8s/30-hpa-web.yaml` | `deploy/k8s/hetzner/cluster-autoscaler-values.yaml` |
| Range | 1–60 pods | 1–15 nodes |
| Managed by | Kubernetes built-in | Helm chart (third-party) |
| Scale-up speed | Seconds (just start a container) | ~90 seconds (boot a server) |
| Scale-down | Wait 10 min, remove 2 pods/min | Wait 20 min, node must be <15% utilized |

**Cluster Autoscaler scale-down settings** (from `cluster-autoscaler-values.yaml`):

```yaml
extraArgs:
  scale-down-unneeded-time: 20m              # Node must be idle for 20 minutes
  scale-down-delay-after-add: 15m            # After adding a node, wait 15 min before removing any
  scale-down-delay-after-delete: 5m          # After removing a node, wait 5 min before removing another
  scale-down-utilization-threshold: "0.15"   # Node must be below 15% utilization
```

These conservative settings prevent the autoscaler from killing workers too aggressively during load tests or variable traffic.

### Helm — Package Manager for Kubernetes

**Helm** is like `pip` for Kubernetes. Instead of writing complex manifests by hand for third-party tools, you install them from pre-built packages called **charts**.

Our 16 manifest files in `deploy/k8s/` are for our own app — we wrote them. The Cluster Autoscaler, however, is a third-party tool with its own Deployment, ServiceAccount, RBAC roles, and configuration — roughly 8-10 resources. Instead of writing all those manifests ourselves, we use the official Helm chart.

**Key terms:**

| Term | What it is |
|------|-----------|
| Chart | A package of Kubernetes manifests with templated values. Like a Python package on PyPI. |
| Values file | YAML that configures the chart. Like passing arguments to a function. |
| Release | A deployed instance of a chart. `helm upgrade` updates the release. |
| Repository | Where charts are hosted. Like PyPI for Python. `autoscaler` repo hosts the cluster-autoscaler chart. |

**How we use Helm:**

```bash
# Add the chart repository (one-time)
helm repo add autoscaler https://kubernetes.github.io/autoscaler

# Install/upgrade the autoscaler with our values
helm upgrade cluster-autoscaler autoscaler/cluster-autoscaler \
  -n kube-system \
  -f /root/cluster-autoscaler-values.yaml \
  -f /tmp/autoscaler-secrets.yaml
```

Helm reads the values files, generates the full set of manifests, and applies them. The `-f` flag merges values files in order — later files override earlier ones.

**Critical rule:** Once Helm manages a resource, do NOT modify it with `kubectl set env` or `kubectl edit`. Helm does not know about imperative changes and will overwrite them on the next `helm upgrade`. This is exactly what caused the LT7.4 incident — a manual `kubectl set env` fix was silently wiped by a subsequent `helm upgrade`.

**CI/CD integration:** The `deploy-autoscaler` job in `.github/workflows/deploy-k3s.yml` runs `helm upgrade` automatically when `cluster-autoscaler-values.yaml` changes. Secrets (`HCLOUD_TOKEN`, `HCLOUD_CLUSTER_CONFIG`) are stored in GitHub Secrets and reconstructed at deploy time — they never appear in the repo.

### Networking — How Everything Talks

All nodes (master, workers, DB box) are on Hetzner's private network `artkhoj-net` (10.0.0.0/16). Here is how traffic flows:

**External traffic (user → app):**
```
User → Cloudflare → AWS Global Accelerator → Hetzner LB (5.223.35.241)
  → k3s nodes (port 80/443) → Traefik → Django Service → Django pod
```

The Hetzner Load Balancer targets all servers with the label `role=k3s`. Traefik (running on the master) routes based on the Ingress rules to the Django Service, which load-balances across all Django pods.

**Internal traffic (pod → database):**
```
Django pod → 10.0.0.2:5432 (PostgreSQL on DB box, private IP)
Django pod → 10.0.0.2:6379 (Redis on DB box, private IP)
```

Database connections use private IPs. No traffic leaves the private network. The DB box is not part of the k3s cluster — it is a standalone server running PostgreSQL and Redis in Docker.

**Metrics traffic (Prometheus scraping):**
```
Prometheus Agent (pod in cluster)
  → scrapes Django pods at pod-IP:8000/metrics  (via Kubernetes service discovery)
  → scrapes Node Exporter at node-IP:9100       (via Kubernetes service discovery)
  → remote_write to 10.0.0.2:9090               (Prometheus on DB box, private IP)
```

Prometheus Agent runs inside the cluster and uses `kubernetes_sd_configs` to automatically discover pods. It scrapes metrics and forwards them to the Prometheus server on the DB box via `remote_write`.

**Flannel (pod networking):** k3s uses Flannel as its network overlay. Each node gets a subnet (e.g., 10.42.0.0/24, 10.42.1.0/24). Pods get IPs from this range. Flannel handles routing between pods on different nodes using VXLAN tunnels over the private network interface (`enp7s0`). You rarely need to think about this — just know that any pod can reach any other pod by IP.

### kubectl — The Command Line Tool

`kubectl` is how you interact with the cluster. It runs on the master node (SSH in first: `ssh root@5.223.45.51`). Every command needs `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` set first, or you get "connection refused."

#### Viewing Resources

```bash
# Set this first (or add to ~/.bashrc)
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# ---- Nodes (servers) ----
kubectl get nodes                           # List all nodes and their status
kubectl get nodes -o wide                   # With IPs, OS, kernel version
kubectl describe node <node-name>           # Detailed info: capacity, pods, conditions
kubectl top nodes                           # CPU/memory usage per node (needs metrics-server)

# ---- Pods (containers) ----
kubectl get pods -n artkhoj                 # List pods in our namespace
kubectl get pods -n artkhoj -o wide         # With node name and IP
kubectl get pods -n kube-system             # System pods (autoscaler, traefik, etc.)
kubectl get pods --all-namespaces           # Everything across all namespaces
kubectl describe pod <pod-name> -n artkhoj  # Events, status, restart count, node placement
kubectl top pods -n artkhoj                 # CPU/memory usage per pod

# ---- Deployments ----
kubectl get deployments -n artkhoj          # List deployments with replica counts
kubectl describe deployment django -n artkhoj  # Detailed deployment info

# ---- Services ----
kubectl get svc -n artkhoj                  # List services and their cluster IPs

# ---- HPA ----
kubectl get hpa -n artkhoj                  # Current targets, min/max, current replicas

# ---- Everything ----
kubectl get all -n artkhoj                  # Pods, deployments, services, HPAs in one view
```

#### Reading Logs

```bash
# Logs from a specific pod
kubectl logs <pod-name> -n artkhoj

# Follow logs (like tail -f)
kubectl logs -f <pod-name> -n artkhoj

# Logs from ALL pods in a deployment
kubectl logs deployment/django -n artkhoj

# Last 50 lines
kubectl logs --tail=50 <pod-name> -n artkhoj

# Logs from a crashed/restarted pod (previous container)
kubectl logs <pod-name> -n artkhoj --previous
```

#### Debugging

```bash
# Shell into a running pod
kubectl exec -it <pod-name> -n artkhoj -- /bin/bash

# Run a one-off command
kubectl exec <pod-name> -n artkhoj -- python manage.py shell

# Check why pods are Pending (look at Events section)
kubectl describe pod <pod-name> -n artkhoj

# Check events cluster-wide (useful for debugging scheduling/scaling)
kubectl get events -n artkhoj --sort-by=.lastTimestamp

# Check cluster autoscaler logs
kubectl logs deployment/cluster-autoscaler-hetzner-cluster-autoscaler -n kube-system --tail=100

# Check what is in a Secret (base64 encoded)
kubectl get secret artkhoj-env -n artkhoj -o yaml
```

#### Modifying Resources

```bash
# Apply a manifest (create or update)
kubectl apply -f deploy/k8s/11-deployment-web.yaml

# Apply all manifests in a directory
kubectl apply -f deploy/k8s/

# Delete a resource
kubectl delete pod <pod-name> -n artkhoj           # Pod will be recreated by Deployment
kubectl delete job django-migrate -n artkhoj        # Delete a completed Job

# Force restart all pods in a deployment (rolling restart)
kubectl rollout restart deployment/django -n artkhoj

# Set a new image (CI/CD does this)
kubectl set image deployment/django django=ghcr.io/datatwine/createscale:<sha> -n artkhoj

# Watch rollout progress
kubectl rollout status deployment/django -n artkhoj

# Scale manually (bypasses HPA temporarily)
kubectl scale deployment/django --replicas=5 -n artkhoj
```

#### The `-n` Flag

Almost every command needs `-n <namespace>`:
- `-n artkhoj` — our app resources
- `-n kube-system` — Kubernetes system components (autoscaler, Traefik, metrics-server, CoreDNS)

If you forget `-n`, kubectl uses the `default` namespace and you will see nothing.

### CI/CD Pipeline for k3s (`.github/workflows/deploy-k3s.yml`)

The k3s pipeline has 7 jobs:

```
Push to main
    │
    ▼
GUARDRAILS ──── Ruff (lint) + Bandit (security scan)
    │
    ▼
BUILD ───────── docker compose build (validates Dockerfile)
    │
    ▼
TEST ────────── PostgreSQL + Redis services, migrations check, pytest
    │
    ├──────────────────────┬──────────────────────┐
    ▼                      ▼                      ▼
PUSH-IMAGE             DEPLOY-DB             DEPLOY-AUTOSCALER
ARM64 to GHCR          SSH to DB box         Helm upgrade (if values changed)
    │                   git pull + compose up  via kubeconfig
    ▼
DEPLOY-WEB
Apply manifests
Run migration Job
Roll new image
Wait for rollout
```

**Key differences from the AWS pipeline:**
- No Nginx. Traefik handles routing automatically via the Ingress resource.
- No SSM. Deploy-web uses `kubectl` directly (kubeconfig stored as GitHub Secret).
- No upstream discovery. Kubernetes Service auto-discovers pods by label.
- No canary deploy. Rolling update strategy handles zero-downtime natively.
- Autoscaler config deployed via Helm (only when values file changes).
- Firewall is opened for the CI runner's IP before deploy, closed after (Hetzner API).

### Manifest File Reference

All files live in `deploy/k8s/`. The naming convention uses a numeric prefix for ordering:

| File | Kind | Purpose |
|------|------|---------|
| `00-namespace.yaml` | Namespace | Creates the `artkhoj` namespace |
| `01-secret.example.yaml` | Secret | EXAMPLE only — never apply this |
| `10-job-migrate.yaml` | Job | Runs `python manage.py migrate` once per deploy |
| `11-deployment-web.yaml` | Deployment | Django fleet pods (run on workers, HPA-scaled) |
| `11b-deployment-web-resident.yaml` | Deployment | Django resident pod (runs on master, always 1) |
| `12-deployment-worker.yaml` | Deployment | Celery worker |
| `13-deployment-beat.yaml` | Deployment | Celery beat scheduler |
| `20-service-web.yaml` | Service | Internal load balancer for Django pods |
| `21-ingress-web.yaml` | Ingress | Routes `stagefreedom.org` traffic to Django |
| `22-middlewares.yaml` | Middleware | Traefik: security headers, body limit, gzip |
| `30-hpa-web.yaml` | HPA | Autoscales Django pods (1–60) at 60% CPU |
| `40-daemonset-promtail.yaml` | DaemonSet | Ships logs from every node to Loki |
| `41-daemonset-node-exporter.yaml` | DaemonSet | CPU/memory metrics from every node |
| `50-rbac-prometheus.yaml` | SA + RBAC | Permissions for Prometheus to discover pods |
| `60-prometheus-agent.yaml` | ConfigMap + Deployment | Scrapes metrics, remote_writes to DB box |
| `promtail-config.yaml` | ConfigMap | Promtail log shipping configuration |
| `hetzner/cluster-autoscaler-values.yaml` | Helm values | Cluster Autoscaler config (1–15 nodes) |

### DOs and DON'Ts

| DO | DO NOT |
|----|--------|
| Always specify `-n artkhoj` or `-n kube-system` | Run `kubectl` without `-n` (hits empty `default` namespace) |
| Use `kubectl apply -f` to change resources | Use `kubectl edit` or `kubectl set env` on Helm-managed resources (autoscaler) |
| Check `kubectl get events` when debugging | Guess why pods are Pending or CrashLooping |
| Read pod logs with `kubectl logs` before theorizing | Assume the cause of a failure without observing |
| Set `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` first | Run kubectl without KUBECONFIG (connection refused) |
| Use Helm for the autoscaler, `kubectl apply` for everything else | Mix Helm and kubectl for the same resource |
| Let HPA handle scaling — do not manually set replicas | Run `kubectl scale` in production (HPA will override it anyway) |
| Delete a Job before re-creating it (Jobs are immutable once complete) | `kubectl apply` an existing completed Job (will fail) |
| Use private IPs (10.0.0.x) for inter-node traffic | Use public IPs (costs money, higher latency, may be firewalled) |
| Commit manifest changes to the repo | Apply manifests on the master without updating the repo (causes drift) |

[k3s docs](https://docs.k3s.io/) | [Kubernetes concepts](https://kubernetes.io/docs/concepts/) | [kubectl cheat sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/) | [Helm docs](https://helm.sh/docs/)

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
