# Trekly

A backpacking-first hiking app for Canada, centred on the Rockies. Find a
trail, see its backcountry campgrounds, plan each night of the trip, and get
an email when a sold-out Parks Canada campsite opens up.

**Live site:** [trekly-web.vercel.app](https://trekly-web.vercel.app)

<!-- Screenshot: landing page -->
<!-- Screenshot: trail page with campgrounds and availability -->
<!-- Screenshot: trip plan -->
<!-- Screenshot: gear page -->

## Features

- **Explore trails:** search and filter 100 popular Canadian trails (most in
  Alberta and BC), with distance, elevation, terrain and seasonal conditions.
  Metric or imperial units.
- **Backcountry campgrounds:** each trail lists its Parks Canada backcountry
  campgrounds, with live availability for your dates and a booking link.
- **Trip plans:** build a multi-night itinerary with a campground for each
  night, then check every night's availability at once.
- **Campground alerts:** watch a sold-out stay and get an email when it opens
  up. A scheduled poller checks Parks Canada every 30 minutes.
- **Gear:** pick items from a curated product catalogue, track the gear you
  own, and save named setups.
- **Accounts:** email sign-up with confirmation, password reset, saved
  trails, a profile with an avatar, and account deletion.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, CSS Modules |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Uvicorn |
| Database & auth | Supabase: Postgres with row-level security, Auth, Storage |
| Email | SendGrid (alerts); Mailpit for local development |
| Hosting | Vercel (web), Render (API, Docker), GitHub Actions (alert poller) |

## Architecture

```mermaid
flowchart LR
    browser([Browser])
    subgraph Vercel
        web[Next.js frontend]
    end
    subgraph Render
        api[FastAPI API]
    end
    subgraph Supabase
        auth[Auth]
        db[(Postgres)]
        storage[Storage]
    end
    subgraph GitHub Actions
        poller[Alert poller<br/>every 30 min]
    end
    pc[Parks Canada<br/>reservation site]
    mail[SendGrid]

    browser --> web
    browser -- sign-in --> auth
    browser -- photos --> storage
    web -- JWT --> api
    api -- verifies JWT via JWKS --> auth
    api --> db
    api -- availability --> pc
    poller --> db
    poller -- availability --> pc
    poller -- alert emails --> mail
```

- The browser signs in with Supabase Auth and sends the access token to the
  API. The API verifies it against Supabase's published signing keys and
  scopes every `/api/me/...` query to that user.
- The API connects to Postgres directly. Row-level security also protects
  every user table from direct access with an anon or user key.
- Avatars and gear photos go straight from the browser to Supabase Storage.
- The poller (`backend/scripts/poll_alerts.py`) shares the API's code and a
  global rate limit on Parks Canada requests. It refuses overlapping runs.

## Local setup

**Prerequisites:** Python 3.11, Node.js 20+, Docker (for the local Supabase
stack).

### 1. Start Supabase

```bash
npx supabase start   # API :44321, Postgres :44322, Studio :44323, Mailpit :44324
npx supabase status  # prints the local anon key
```

Ports are moved to 443xx because Windows reserves 543xx.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
```

In `.env`, set:

```
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres
SUPABASE_URL=http://127.0.0.1:44321
```

Run the migrations and load the data:

```bash
python -m alembic upgrade head
python scripts/catalog.py import          # gear catalogue
python scripts/seed_trails.py             # trails
python scripts/sync_backcountry.py        # Parks Canada campgrounds (~1 min, ~55 requests)
python scripts/seed_trail_campgrounds.py  # trail ↔ campground links
uvicorn app.main:app --reload             # http://localhost:8000
```

> **Known issue:** on an empty database, `alembic upgrade head` stops at
> migration `ac80d30d85f6`. The `gear_rules` and `gear_items` tables
> predate Alembic and no migration creates them.

To try alerts locally, set `EMAIL_BACKEND=mailpit` and
`MAILPIT_URL=http://127.0.0.1:44324`, then run `python scripts/poll_alerts.py`.
Emails show up in Mailpit.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev                        # http://localhost:3000
```

In `.env.local`, set `NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:44321` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` to the anon key from `npx supabase status`.

## Environment variables

### Frontend (`frontend/.env.local`)

All three are public and end up in the browser bundle.

| Variable | Purpose | Required |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon (publishable) key | Yes |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL | No (default `http://localhost:8000`) |

### Backend (`backend/.env`)

| Variable | Purpose | Required |
| --- | --- | --- |
| `DATABASE_URL` | Postgres connection for the API, Alembic and scripts | Yes |
| `SUPABASE_URL` | Supabase project URL, used to verify access tokens | Yes |
| `SUPABASE_JWT_SECRET` | Only for projects still signing tokens with legacy HS256 | No |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API | No (default `http://localhost:3000`) |
| `CORS_ORIGIN_REGEX` | Full-match regex for changing origins, such as Vercel previews | No |
| `APP_URL` | Site base URL used in alert email links | No (default `http://localhost:3000`) |
| `EMAIL_BACKEND` | `sendgrid`, `mailpit` or `console` | No (default `console`) |
| `SENDGRID_API_KEY` | SendGrid API key | Only with `sendgrid` |
| `SENDGRID_FROM_EMAIL` | Sender address for alert emails | Only with `sendgrid` |
| `MAILPIT_URL` | Local Mailpit address | Only with `mailpit` |
| `AVAILABILITY_CACHE_MINUTES` | How long Parks Canada responses are cached | No (default 5) |
| `AVAILABILITY_REQUESTS_PER_MINUTE` | Global cap on live Parks Canada requests | No (default 20) |

### Alert poller (GitHub Actions secrets)

The poller runs the backend code, so it reads the same variables. The
workflow sets these:

| Variable | Purpose | Required |
| --- | --- | --- |
| `DATABASE_URL` | Production Postgres connection (secret) | Yes |
| `APP_URL` | Production site URL for email links (secret) | Yes |
| `SENDGRID_API_KEY` | SendGrid API key (secret) | Yes |
| `SENDGRID_FROM_EMAIL` | Sender address (secret) | Yes |
| `EMAIL_BACKEND` | Set to `sendgrid` in the workflow | Set in workflow |
| `ALERT_POLL_MIN_INTERVAL_MINUTES` | Skip runs closer together than this; set to 25 | Set in workflow |
| `ALERT_POLL_MAX_REQUESTS` | Parks Canada requests per run | No (default 20) |

## Deployment

| Piece | Where | How |
| --- | --- | --- |
| Frontend | Vercel project `trekly-web`, Root Directory `frontend` | Deployed with the Vercel CLI; the GitHub integration isn't connected yet |
| API | Render web service `trekly-api` | Blueprint in [`render.yaml`](render.yaml): Docker build from `backend/`, auto-deploys on push |
| Alert poller | GitHub Actions | [`.github/workflows/alert-poller.yml`](.github/workflows/alert-poller.yml), every 30 minutes plus manual runs |
| Database & auth | Supabase hosted project | Migrations and seed scripts are run by hand from `backend/` |

**Where each secret goes**

- **Vercel** (Preview and Production): `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`.
- **Render** (entered in the dashboard, never in `render.yaml`):
  `DATABASE_URL`, `SUPABASE_URL`, `CORS_ORIGINS`, `CORS_ORIGIN_REGEX`,
  `APP_URL`. Use Supabase's pooler connection string (session mode) for
  `DATABASE_URL`, because the direct database host is IPv6-only and Render
  can't reach it.
- **GitHub Actions** repository secrets: `DATABASE_URL`, `APP_URL`,
  `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`. Until all four are set, the
  workflow skips the run with a warning instead of using up alerts without
  sending email.

Supabase dashboard settings (email confirmation, redirect URLs, password
policy, SMTP) are listed in
[docs/supabase-and-accounts.md](docs/supabase-and-accounts.md#required-supabase-dashboard-settings-hosted-project).

## Testing

```bash
# Backend (from backend/): API, auth, ownership, catalogue pipeline, alerts, plans
python -m pytest

# Storage policy tests, which run only against the local Supabase stack
LOCAL_SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres   python -m pytest tests/test_avatar_storage_policies.py

# Frontend (from frontend/)
npm test && npx tsc --noEmit -p . && npm run lint && npm run build
```

Backend tests use an in-memory database and never touch `DATABASE_URL`.

## Project structure

```
.github/workflows/   Scheduled alert poller
backend/
  app/               FastAPI app: routers, models, auth, Parks Canada client, alert poller
  alembic/           Database migrations
  catalog_data/      Curated trail, campground and gear data
  scripts/           Seeding, catalogue sync and poller entry points
  tests/             pytest suite
frontend/
  app/               Next.js routes (Explore, trail pages, plans, alerts, gear, profile)
  components/        Shared UI
  lib/               API clients, auth and domain logic, with node:test tests
supabase/            Local Supabase stack config
docs/                Design notes: accounts and RLS, gear catalogue, backcountry data
campalert-service/   Earlier Node prototype of the alert worker; not used
render.yaml          Render Blueprint for the API
```
