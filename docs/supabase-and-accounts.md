# Supabase, accounts and user data

How Trekly uses Supabase for sign-in and private user data, what was changed,
and what has to be configured in the Supabase dashboard.

## Architecture

- **Auth** — Supabase Auth, email + password, used from the browser with the
  public anon key (`frontend/lib/supabaseClient.ts`). PKCE flow: every email
  link (signup confirmation, password recovery, email change) lands on
  `/auth/callback`, which exchanges the code and forwards to a safe `next`
  path. Sessions persist in `localStorage` and refresh automatically.
- **API** — FastAPI verifies the user's access token itself against the
  project's published signing keys (`backend/app/auth.py`; ES256/RS256 via
  JWKS, or HS256 with `SUPABASE_JWT_SECRET` for legacy/local projects). No
  service-role key is used anywhere. Every `/api/me/...` query is scoped to
  the token's user id; ids in URLs or bodies are never trusted for ownership.
- **Database** — the backend connects with `DATABASE_URL` (the `postgres`
  role, which bypasses RLS), so the API enforces ownership in code. Row-level
  security enforces the same rules for anyone using Supabase's REST API
  directly with a user or anon key.

## What existed before, and what changed

| Area | Before | Now |
| --- | --- | --- |
| Sign up / sign in | Minimal forms, no confirmation handling | Validation, password rules, confirmation step with resend, unconfirmed-login handling, safe `?next=` redirects |
| Password reset | None | `/forgot-password` → email → `/auth/callback` → `/reset-password`; invalid/expired/used links handled |
| Session | Per-component hook | `AuthProvider` context; loading/signed-in/signed-out/expired states; route guard without flashing content |
| Navigation | Sign up / Login / Log out buttons | Avatar → `/profile`; Sign up / Sign in for guests; sign-out lives in Profile → Settings |
| Profile | Empty `app/profile/` | Profile with Overview / My gear / Saved trails / Trips / Settings; edit name, username, bio, region, avatar; email & password change; sign out; account deletion |
| Saved trails | None | Bookmark on Explore cards and trail pages; guests are sent to sign in and the save completes afterwards |
| Gear | Unapplied `user_gear` table | Shared catalogue + per-user inventory + named setups (see `docs/gear-catalog.md`) |
| Trips / completed hikes | PackPlan doesn't persist trips; no hike records | Not invented — the Trips tab says trips aren't saved yet and links to PackPlan; no completed-hike section |

## Migrations (Alembic, `backend/alembic/versions/`)

| Revision | Adds |
| --- | --- |
| `c3d4e5f6a7b8` | Gear catalogue (`catalog_*`), `user_gear_items`, private `gear-photos` bucket |
| `e5f6a7b8c9d0` | `profiles` (+ signup trigger and backfill), `saved_trails`, private `avatars` bucket |
| `f6a7b8c9d0e1` | `gear_setups`, `gear_setup_items` |

All three are applied to the hosted project. Apply to another database with
`cd backend && python -m alembic upgrade head`.

> The `trails`, `campsites` and PackPlan `gear_*` tables predate Alembic and
> aren't created by any migration. A fresh database needs them first (see
> "Local stack" below for how they were copied).

### Row-level security

Every user-owned table has RLS enabled with owner-only policies for the
`authenticated` role:

| Table | select | insert | update | delete | Rule |
| --- | --- | --- | --- | --- | --- |
| `profiles` | ✓ | ✓ | ✓ | (cascade only) | `id = auth.uid()` |
| `saved_trails` | ✓ | ✓ | — | ✓ | `user_id = auth.uid()` |
| `user_gear_items` | ✓ | ✓ | ✓ | ✓ | `user_id = auth.uid()` |
| `gear_setups` | ✓ | ✓ | ✓ | ✓ | `user_id = auth.uid()` |
| `gear_setup_items` | ✓ | ✓ | ✓ | ✓ | user owns both the setup and the gear item |
| `catalog_*` | public read | — | — | — | written only by the import pipeline; unapproved images hidden |
| Storage `gear-photos`, `avatars` | own folder | own folder | — | own folder | first path segment = `auth.uid()` |

Profiles are **private**: there are no public profiles, and nothing a user
enters is visible to anyone else.

### Profile creation

`on_auth_user_created_profile` (trigger on `auth.users`, `SECURITY DEFINER`,
empty `search_path`) inserts a profile with `ON CONFLICT DO NOTHING`, copying
an optional `display_name` from signup metadata. If a profile is ever missing,
`GET /api/me/profile` creates it idempotently.

### Account deletion

Settings → Delete account (type "delete my account"): the browser removes the
user's photos through the Storage API, then `DELETE /api/me` deletes setups,
gear, saved trails, the profile and finally the `auth.users` row. Shared
catalogue data is untouched.

## Required Supabase dashboard settings (hosted project)

These can't be set from SQL or the repository. In **Authentication**:

1. **Sign In / Providers → Email**: enable *Confirm email*. Enable *Secure
   password change* (requires recent sign-in or an emailed code — the
   Settings page handles the code prompt).
2. **Password requirements**: minimum length **8** (the UI also requires a
   letter and a number or symbol).
3. **URL Configuration**: *Site URL* = your production origin. Add redirect
   URLs: `https://<your-domain>/auth/callback` and
   `http://localhost:3000/auth/callback`.
4. **Emails / SMTP**: Supabase's built-in mailer is heavily rate-limited;
   configure custom SMTP before launch.
5. **OAuth**: none is configured, so no social sign-in buttons are shown. To
   add one, enable the provider in the dashboard and add a button that calls
   `signInWithOAuth` with the same `/auth/callback` redirect.

The local stack (`supabase/config.toml`) is already configured this way.

## Environment variables

| Where | Variable | Notes |
| --- | --- | --- |
| frontend | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | public values |
| frontend | `NEXT_PUBLIC_API_URL` | FastAPI base URL |
| backend | `DATABASE_URL` | Postgres connection (server-side only) |
| backend | `SUPABASE_URL` | used to verify tokens via JWKS |
| backend | `SUPABASE_JWT_SECRET` | optional; legacy HS256 projects and the local CLI stack |
| backend | `CORS_ORIGINS` | comma-separated allowed origins (default `http://localhost:3000`) |

## Local stack and end-to-end testing

`supabase/config.toml` runs a full local Supabase (Auth, Postgres, Storage,
Mailpit inbox) with Docker. Ports are moved to 443xx because Windows reserves
543xx.

```bash
npx supabase start                    # API 127.0.0.1:44321, DB :44322, mail :44324
# base tables (trails, PackPlan gear_*) were copied from hosted with pg_dump, then:
cd backend
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres python -m alembic stamp a1b2c3d4e5f6
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres python -m alembic upgrade head
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres python scripts/catalog.py import
python scripts/verify_rls_local.py    # direct REST checks that users can't reach each other's rows
```

Local-only test accounts are in `supabase/e2e-test-users.env`.

### Verified end to end on the local stack (2026-10-13)

- Signup validation → "check your email" → unconfirmed sign-in message with
  resend → confirmation link → signed in and returned to the intended page;
  profile row created by the trigger.
- Sign in returns to `?next=`; session survives reload and browser restart.
- Adding a backpack and a tent from slot pickers; mat updates after save and
  persists after reload.
- Creating a named setup; it shows on the Gear page and the profile.
- Saving a trail from Explore; it appears on the profile.
- Editing the bio; persists after reload.
- Sign out from Settings with confirmation; protected pages then redirect to
  sign in.
- Password reset: request → email → new password; new password works, old
  one is rejected; reusing the link shows "That link didn't work".
- `verify_rls_local.py`: 14/14 checks pass (no cross-user read/update/delete/
  insert on gear, profiles, saved trails or photos; catalogue read-only).

Not exercised in a browser: email change, the secure-password-change code
prompt, avatar upload, and account deletion (covered by API tests).
