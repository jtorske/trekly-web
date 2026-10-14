# Trekly

A hub for backpackers: find trails, show off and organize the gear you own,
build a packing list for a trip, and get alerts for campsite availability.

| Part | Stack | Folder |
| --- | --- | --- |
| Web app | Next.js 16, React 19, TypeScript | `frontend/` |
| API | FastAPI, SQLAlchemy, Alembic | `backend/` |
| Data & auth | Supabase (Postgres, Auth, Storage) | `supabase/` (local stack config) |
| CampAlert worker | Node | `campalert-service/` |

Features: Explore trails and trail pages with saved trails · Gear showcase
with a verified product catalogue and named setups · PackPlan packing lists ·
CampAlert · accounts with private profiles.

## Setup

```bash
# API
cd backend
pip install -r requirements-dev.txt
cp .env.example .env            # fill in DATABASE_URL and SUPABASE_URL
python -m alembic upgrade head  # gear, profiles, saved trails, setups
python scripts/catalog.py import
uvicorn app.main:app --reload   # http://localhost:8000

# Web app
cd frontend
npm install
cp .env.example .env.local      # Supabase URL + anon key, API URL
npm run dev                     # http://localhost:3000
```

Supabase dashboard settings (email confirmation, redirect URLs, password
policy) are listed in [docs/supabase-and-accounts.md](docs/supabase-and-accounts.md#required-supabase-dashboard-settings-hosted-project).

## Checks

```bash
cd backend && python -m pytest          # API, auth, ownership, catalogue pipeline
cd frontend && npm test && npx tsc --noEmit -p . && npm run lint && npm run build
cd backend && python scripts/verify_rls_local.py   # RLS against the local Supabase stack
```

## Docs

- [Accounts, Supabase, RLS and local end-to-end testing](docs/supabase-and-accounts.md)
- [Gear catalogue, inventory, setups and data sources](docs/gear-catalog.md)
