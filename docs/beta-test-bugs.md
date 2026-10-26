# Trekly beta test bugs

## Round 1

Round 1 was never run, or its log wasn't saved, so there are no Round 1 bugs to retest. Because there's no Round 1 baseline, this round can't flag regressions.

## Round 2: 2026-10-24

- **Site:** https://trekly-web.vercel.app (production), API https://trekly-api.onrender.com
- **Tested as:** a guest, and signed in as `jtorske27+trekly-beta@gmail.com` (created by Jordan in the Supabase dashboard)
- **Browser:** Chrome on Windows 11 at 1920px, plus a 390px-wide frame for mobile (see "Couldn't test")
- **Test data:** every record created was named `BETA2…` and removed afterwards. Before testing, the account already had one Durston Kakwa 55 and one saved trail (Egypt Lake / Healy Pass); both were left as they were.

### Fix batch 1: 2026-10-24

Fixed B-001, B-002 (display only), B-004, B-005, B-006 and B-007. B-003 was skipped because Jordan is handling the policy text.

- **Build and tests:** frontend build passes, frontend tests pass (60), backend tests pass (238 passed, 10 skipped).
- **Deploy:** pushed to master; Vercel served the new build about 50 seconds after the push.
- **B-004 concurrency:** checked against local Postgres.
  - With the fix, 5 simultaneous identical requests gave one 201 and four 409s.
  - 5 simultaneous requests at 9 active alerts left exactly 10 (the cap).
  - With the lock disabled, the cap test reached 14, so the lock is needed alongside the index.
- **B-004 hosted migration:** `f3a4b5c6d7e8` hasn't been run on hosted. Until it is, the API's lock stops new duplicates, and the index will be the backstop once the migration runs.
- **B-002 data gap** (from `backend/catalog_data/trails_canada.json`):
  - **What's missing:** 89 of 100 trails have no distance or route type, 84 have no elevation gain and 74 have no high point. 58 of the 89 are day hikes and 31 are overnight trips.
  - **Distance and route type:** rerun the OSM route measurement against a working Overpass mirror (the main server was overloaded during the first pass). Expect about half to resolve cleanly; the rest need manual entry from Parks Canada and provincial-park pages, about 3–5 minutes per trail.
  - **Elevation gain and high point:** OSM rarely has elevation at both ends of a route, so these need an elevation dataset sampled along each route geometry (e.g. Canada's CDEM or Copernicus 30 m, via OpenTopoData), or manual entry.
  - **Estimate:** roughly 1–2 days of work for full coverage.

### Fix batch 2: 2026-10-26

Fixed B-008 to B-012 and B-014 to B-022, plus UX suggestions 1, 5 and 6. B-004's hosted migration has run (confirmed read-only). B-013 is closed as not a bug.

- **Build and tests:** frontend build passes, frontend tests pass (77), backend tests pass (254 passed, 10 skipped), and lint and type check are clean.
- **Account menu tests:** two tests had failed since `ab3955c`, which removed the Settings and Contact support rows. `7bc2a94` updates them to match.
- **Deploy:** pushed `f52489b` to master at 22:50 UTC. Vercel served it about 40 seconds later (the `/privacy` space is fixed live), and Render about 70 seconds later: `/docs`, `/redoc` and `/openapi.json` return 404, and searching `%` or `_` returns 0 trails. Client-side changes (sorting, cropper, error states) were checked with tests and the build, not clicked through on the live site.
- **B-009 limit:** uploads go straight from the browser to Supabase Storage, so the content check runs in the browser. A hand-crafted request could still store a non-image. The bucket is private and responses send `nosniff`, so the risk stays low.

### Known issue (logged once)

| ID | Severity | Area | Notes |
|---|---|---|---|
| B-000 | Known | Email delivery | Sign-up confirmations, password resets, email changes and alert emails aren't fully set up. `render.yaml` sets `EMAIL_BACKEND=console` for the API, so alert emails are only logged. Not retested in each flow below. |

### Bugs

Sorted by severity, then by impact.

| ID | Severity | Status | Page / feature | Steps to reproduce | Expected | Actual | Screenshot |
|---|---|---|---|---|---|---|---|
| B-001 | High | Fixed (`12a13f6`): route deleted; live `/campalert` now returns 404. | `/campalert` (old mock page) | 1. Go to `/campalert` (guest or signed in). 2. Search "berg" and pick Berg Lake Trail. 3. Pick an arrival date, enter an email, then click **Create alert**. | The page doesn't exist, or it creates a real alert. | It shows "Your alert is set" but nothing is saved: no request reaches the API. The page has 4 hard-coded trails (`app/campalert/campsites.ts`) and a fake submit. Nothing in the app links to it, but it's live and anyone with the URL can use it. Someone who finds it will believe a site is being watched when it isn't. | `docs/beta-test-screenshots/b001-campalert-page.jpg`, `b001-campalert-fake-success.jpg` |
| B-002 | High | Partly fixed (`34e67cd`): pages and cards now hide unknown distance and elevation (checked live). The data is still missing; see the fix notes. | Explore list and trail pages: distances | 1. Open Explore and scroll the list. 2. Open e.g. Johnston Canyon, Grouse Grind or Berg Lake Trail. | Every trail shows its distance and route type. | 89 of the 100 live trails have no `distance_km` or `route_type`, and 84 have no `elevation_gain_m`. Rows show only "Day hike" or "3 nights", and trail pages have no distance. Includes multi-night trips like Berg Lake and Garibaldi Lake. (Known data gap from the Phase 5 distance backfill.) | |
| B-003 | Medium | Fixed (`ee3d8af`): Jordan's updated text, dated October 26, 2026. Both pages now say there are no public profiles and that everything is private. Google sign-in is described and now built (`5f77da3`). The Terms list provincial parks and OpenStreetMap as trail sources, and the Privacy Policy lists GitHub for alert checks. | Privacy Policy and Terms of Use | Read `/privacy` ("What other users can see") and `/terms` ("Your content"), then compare with Profile → Settings → Privacy. | The legal pages match how the app works. | Both legal pages say your display name, profile, profile picture and gear loadouts are visible to other users. The app says "Trekly doesn't have public profiles … only visible to you", and the API returns `visibility: "private"`. The Privacy Policy also describes "Sign in with Google", which isn't built (no Google code in the frontend). The Terms say trail data comes from Parks Canada, but the catalogue includes provincial-park and municipal trails (Grouse Grind, Joffre Lakes). | |
| B-004 | Medium | Fixed (`bad752a`). Migration `f3a4b5c6d7e8` is applied locally and on hosted. Read-only check on 2026-10-26: hosted `alembic_version` is `f3a4b5c6d7e8`, and the partial unique index `availability_alerts_active_unique` exists. | Alerts API: duplicates | Send the same `POST /api/me/alerts` request 3 times at once (e.g. a flaky network retry or a script). | One alert is created; the others get 409 "You already have an alert…". | All 3 return 201 and create 3 identical active alerts. The duplicate check and the active-alert cap are read-then-insert with no unique constraint, so simultaneous requests get past both. Each duplicate means extra polling of Parks Canada and extra emails. The UI's double-click guard works, so this needs concurrent requests. | |
| B-005 | Medium | Fixed (`2280711`): checked live, one request per check, and shared links still check once. | Trail page: Check availability | 1. Open a trail page with campgrounds (e.g. Egypt Lake / Healy Pass). 2. Click **Check availability** once. 3. Watch the network tab. | One `/availability` request. | Two requests on the first check after the page loads. `submit()` puts `?start=…` in the URL and calls `check()`, then the "shared link" effect (`autoChecked` is still false) sees the new URL and calls `check()` again, cancelling the first. Every first check hits Parks Canada twice. (`app/trails/CampgroundsSection.tsx` around lines 301–324.) | |
| B-006 | Medium | Fixed (`0844134`): checked live in dark mode. | 404 page | Visit any unknown URL, e.g. `/this-page-does-not-exist`, with the OS in dark mode. | A readable "page not found" with a link home. | The default Next.js 404 switches to dark-mode white text but stays on Trekly's cream background, so "404 / This page could not be found" is almost invisible. There's no custom `not-found.tsx` and no link back home apart from the nav. | |
| B-007 | Medium | Fixed (`5b63928`): headers confirmed on the live site, and framing is blocked. | Security headers (site-wide) | `curl -I https://trekly-web.vercel.app/landing` | Headers that block other sites from framing Trekly (CSP `frame-ancestors` or `X-Frame-Options`), plus `X-Content-Type-Options`. | Only HSTS is set. Any site can load Trekly in an iframe, so a malicious page could trick a signed-in user into clicking something like **Permanently delete my account** (clickjacking). Confirmed by loading the site in an iframe during testing. | |
| B-008 | Low | Fixed (`37e3294`): files are checked by their contents, not the name; "We couldn't read that image" shows instead of the cropper, and each pick gets a fresh cropper. | Profile: avatar upload | 1. Edit profile → Add photo. 2. Pick a file named `.jpg` that isn't really an image. 3. Click **Use this photo**. | An error like "We couldn't read that image." | The cropper shows a blank dark square and **Use this photo** silently does nothing. Closing and reopening the dialog keeps the broken state; only a page reload clears it. | |
| B-009 | Low | Fixed (`37e3294`): non-images are rejected on save with a clear error, and real images are stored as their actual type. Checked in the browser only; Storage still trusts the declared type. | Gear: item photo upload | Edit a gear item and upload a text file renamed to `.jpg`, then save. | It's rejected as not an image. | It's accepted and stored as the item's photo (the edit dialog then shows "Remove current photo" with no preview). Storage only checks the declared type and size; it is served as `image/jpeg` and the bucket is private, so the risk is low. | |
| B-010 | Low | Fixed (`f52489b`, `0ab1b10`): plan titles, setup names, trip cards, setup chips and trail cards wrap long words. | Long text | 1. Create a trip plan whose title is a long word with no spaces (the field allows 80 characters). 2. Or rename a setup to 80 characters with no spaces and view Profile → Overview at 390px. | Text wraps or truncates with an ellipsis. | The plan page title runs about 160px past the page edge and is clipped. The setup name runs past its card on the profile. | |
| B-011 | Low | Fixed (`3f7147d`): `%`, `_` and `\` are escaped; API test added. | Explore search | Search for `%` or `_`. | Matches trails whose names contain that character (none). | `%` matches all 100 trails, because the search text is put into an `ILIKE` pattern without escaping wildcards. | |
| B-012 | Low | Fixed (`0ab1b10`): shows the exact count. | Explore count | Open Explore with no filters. | "100 trails". | "100+ trails". The API caps the catalogue at exactly 100 (`TRAIL_CATALOG_LIMIT`), so the "+" overstates it. | |
| B-013 | Low | Closed, not a bug (no data changed): 15 is the zone's nightly quota (`zoneCapacitySettings.capacity`), which is what the UI shows. 5 is Parks Canada's per-booking `maxCapacity`, not the site's capacity. | Trail data: campground capacity | Open Egypt Lake / Healy Pass and look at Egypt Lake (E13). | The nightly quota is at most the site's max capacity. | It shows "Quota 15 a night". The API returns `reservable_capacity: 15` but `max_capacity: 5` for the same site. | |
| B-014 | Low | Fixed (`859786c`): metric weight filter (250 g to 1.5 kg), and dual-unit spec text puts the reader's units first. | Gear: units | Set units to kg/g, open a gear picker (e.g. Sleeping pad), and look at the weight filter and a product's "Packed size". | Metric everywhere. | The weight filter offers "Under 8 oz / 1 lb / 2 lb / 3 lb", and packed size shows inches first ("9 x 4.1 in (23 x 10 cm)"), while the cards show grams. | |
| B-015 | Low | Fixed (`f52489b`): "That's already your email." (case-insensitive). | Settings: change email | Enter your current email as the new email and click **Change email**. | "That's already your email." | "Check both jtorske27+trekly-beta@gmail.com and jtorske27+trekly-beta@gmail.com — confirm the change from the links we sent." | |
| B-016 | Low | Fixed (`f52489b`): now also lists setups, trip plans and campsite alerts. | Settings: delete account wording | Settings → **Delete account…** | The warning lists everything that's deleted. | It lists "profile, photos, saved trails and gear inventory" but not trip plans or alerts. (Those are deleted by the database's `ON DELETE CASCADE`, so this is only the wording.) | |
| B-017 | Low | Fixed (`f52489b`): "Nothing to finish here" with a Sign in link. | `/auth/callback` | Open `/auth/callback` with no parameters. | A neutral message or a redirect. | "Your email is confirmed. Sign in to continue", even though nothing was confirmed. | |
| B-018 | Low | Fixed (`f52489b`, `859786c`). Cause: the compiler drops the space between `</strong>` and text containing an HTML entity (`&apos;`, `&ldquo;`), so the spaces are now explicit. Checked in the built output. | Copy: missing spaces | Gear as a guest (banner); a gear picker's "Add to my gear" as a guest; `/privacy`. | Normal spacing. | "Sign in to save your setup.Browse the catalogue…", "Sign in to save your gear.We'll keep your selection…", "Google sign-in:if you choose…". | |
| B-019 | Low | Fixed (`0ab1b10`, `f52489b`): Explore has plain wording and a Try again button; Gear hides the counts and the empty board when loading fails; Profile wording simplified and failed counts show "–". | Error states | Load Explore, Gear or Profile while the API can't be reached (simulated by blocking requests to `trekly-api.onrender.com`). | A plain-language error with a retry button, and no misleading numbers. | Explore says "Check that the trail service is running and try again" (developer wording, no retry button). Gear shows the error but also "0 of 7 main pieces · 0 items · 0 g", as if the gear were empty. | |
| B-020 | Low | Fixed (`f52489b`): "about every 30 minutes" on the alerts page and the alert dialog. | Alerts copy | Alerts page, on a new alert. | Matches how often alerts are really checked. | Says "We check every few minutes", but the poller runs every 30 minutes from GitHub Actions (`.github/workflows/alert-poller.yml`), and GitHub can start runs late. | |
| B-021 | Low | Fixed (`f52489b`): `/plans` lists your trips (same list as Profile → Trips). | `/plans` with no ID | Go to `/plans`. | Your trip list, or a link to it. | "No plan picked / Your trip plans" with no link. Plans are only listed under Profile → Trips. | |
| B-022 | Low | Fixed (`3f7147d`): `/docs`, `/redoc` and `/openapi.json` are off on Render (`API_DOCS` overrides). | API docs public | Open `https://trekly-api.onrender.com/docs` or `/openapi.json`. | Hidden in production, unless that's intended. | The Swagger UI and full OpenAPI schema are public. All `/api/me/*` routes do require auth (401 without a valid token), so this is information exposure only. | |

### What passed

- **Auth guard:** every `/api/me/*` route returns 401 without a token or with a bad one. Patching another user's gear ID returns 404. Setups refuse items you don't own ("Setups can only include gear you own").
- **Storage:** you can't write into another user's folder (blocked by row-level security). Avatars and gear photos reject SVG and HTML and anything over 5 MB on the server. Gear photos aren't reachable by public URL. Replaced or removed photos are deleted from storage.
- **Validation:** gear quantity is 1–99 in both UI and API. Notes are capped at 2000 characters, setup names at 80, usernames must be 3–30 lowercase characters. Setup names must be unique (409). Alerts reject past dates, nights outside 1–14, party size outside 1–12, unknown sites, a site that isn't on the trail, and extra fields.
- **Double-click:** Save plan, Set alert, Create setup, Save profile and the trail save button each produce exactly one record.
- **XSS:** `<script>` in plan notes and `<b>` in the bio show as plain text.
- **Explore:** search trims spaces, filters match the API counts (34 backpacking, 66 day hikes, 6 extreme backpacking), filters stay in the URL, the empty state is clear, and back/forward keeps the search, filters and scroll position.
- **Trail page:** unit conversions are correct (24.6 km = 15.3 mi, 650 m = 2,133 ft, −5 °C = 23 °F). Booking links go to Parks Canada with the dates filled in, and "View on map" opens OpenStreetMap.
- **Plans, alerts, gear, setups, profile, saved trails:** create, edit, delete, cancel and remove all work, and the profile counts update.
- **Signing out** clears the session and goes to `/landing`. Back afterwards shows guest views with no leftover private data. Protected pages redirect to `/login?next=…`, and `next` only allows same-site paths.
- **Session after refresh:** stayed signed in across reloads and new navigations throughout the session.
- **Mobile at 390px:** no page scrolls sideways (13 pages plus the auth pages checked).
- **Loading and error states:** each page shows a loading state while the API is slow, and an error message if the API fails.

### Account deletion

_Pending: needs the throwaway account to be signed in. See the summary in chat._

### UX suggestions (not bugs)

1. **Done (`0ab1b10`): Sorting on Explore.** There are no sort options at all (by distance, difficulty, nights, name). I couldn't test sorting because none exists.
2. **Navigation.** The top nav and mobile menu only have Explore, Gear and Profile. Alerts, Trips and Sign out are only reachable from inside the profile. Consider adding "Trips" and "Alerts" to the menu.
3. **Profile tabs on mobile.** At 390px the tab row cuts off after "Saved trails". It does scroll sideways, but nothing shows that, and Settings (with Sign out and Delete account) is fully hidden.
4. **Cold-start message.** The API is on Render's free plan, which sleeps after about 15 minutes. "Loading trails…" can then sit for about 50 seconds with no explanation. Show "Waking up the trail server…" after a few seconds.
5. **Done (`f52489b`): Cancelled alerts** still show **Check now**. Either hide it or explain what it does for a cancelled alert.
6. **Done (`0ab1b10`): Trails with the same name** (two "Skyline Trail"s: Jasper and Cape Breton) are told apart only by the small region line. Consider showing the park in the title, or in search results when names clash.
7. **Done (`0ab1b10`): Retry button** on the Explore error state, to match Profile and Gear.

### Couldn't test, and why

- **Sign-up, sign-in, password reset and password change submissions.** Typing passwords on production is outside what I'm allowed to do. I tested field validation, error messages, labels and the redirects into and out of the auth pages. You created and signed in the test account yourself.
- **Google sign-in.** Not built: no Google provider anywhere in the frontend. Only the privacy policy mentions it (B-003).
- **Render cold start.** The API was already awake when testing started and stayed warm, so a real cold start never happened. I simulated a 6-second-slow API instead (see UX 4).
- **Real network throttling.** I don't have a throttling tool. Slow and offline API responses were simulated by wrapping `fetch` in the page.
- **Mobile at a true 390px window.** Resizing the Chrome window didn't take effect, so mobile checks ran in a 390×844 same-origin iframe. That's fine for layout and overflow, but it's not a real phone (no touch, no mobile browser chrome).
- **Alert poller in production.** I can't see whether the GitHub Actions poller is running (`gh` isn't installed). I kept alert testing light (one UI alert and a few short-lived API alerts, all deleted within seconds), so no alert was ever polled.
- **Email flows.** Known issue B-000.
