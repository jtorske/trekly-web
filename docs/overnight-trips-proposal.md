# Overnight trip flow: Phase 1 proposal

Status: **proposal, 2026-10-15. Awaiting review.** Nothing here is built
yet. The draft trail ↔ campground mapping is in
[`backend/catalog_data/trail_campgrounds.json`](../backend/catalog_data/trail_campgrounds.json).

The flow: pick a trail → see the campgrounds along it → check availability
or set an alert → pick a gear setup → get a trip plan.

## 1. What exists today

### Trails (`backend/app/models/trail.py`, `app/trail_catalog.py`, `routers/trails.py`)
- `trails` is synced from `catalog_data/trails_canada.json`: the top 100 by
  editorial rank are live and the rest are retired, never deleted. The
  natural key is `(name, province_code)`. "Skyline Trail" exists in both AB
  and NS, so a name alone isn't unique.
- `typical_duration_nights` separates day hikes (0) from overnight trips
  (≥ 1). **34 of the top 100 are overnight.**
- API: `GET /api/trails` (search) and `GET /api/trails/{id}` (detail plus
  seasonal conditions). The trail page (`frontend/app/trails/page.tsx`)
  shows stats, description, seasons and location. "Find campsites" links
  to the mock `/campalert` page.
- Reusable: the guest-first "save, then sign in, then return" pattern
  (`?save=<id>` plus `returnTo`). It works the same way for "alert me" and
  "plan this trip".

### Backcountry catalogue (`app/models/backcountry.py`, `app/backcountry/*`)
- 860 sites in 26 parks (756 publicly listed). For each site we store
  `provider_location_id`, `provider_map_id` and
  `provider_booking_category_id`, which is everything an availability call
  needs. `reservable_capacity` is the zone quota.
- `ParksCanadaClient` already sends browser-like headers, spaces requests
  1 s apart, backs off exponentially on 5xx/429/network errors, and caches
  responses to disk. **Reusable for availability as is** (with a TTL cache
  instead of the forever disk cache).
- RLS: public read, no write policies, and `is_publicly_listed = false`
  rows are hidden. Sites are retired, never deleted, so FKs to
  `backcountry_sites.id` are safe.
- No coordinates (the API exposes none), so trail ↔ site links can't be
  computed.

### Gear and setups (`models/setup.py`, `routers/me_setups.py`, `frontend/app/gear/*`)
- `gear_setups` / `gear_setup_items` reference the user's own
  `user_gear_items`. `SetupOut` already returns `items`, `known_weight_g`
  and `items_missing_weight`. Owner-only RLS.
- `frontend/app/gear/slots.ts` maps catalogue subcategories to slots and
  marks *core* slots (backpack, tent/shelter, sleeping bag/quilt, sleeping
  pad, stove, footwear, rain jacket). **The "missing core gear" check
  reuses this mapping** rather than inventing a new one. `FlatLay.tsx` is
  the visual to reuse on the plan page.
- PackPlan's leftover gear tables (`gear_items`, `gear_rules`) stay
  untouched.

### campalert-service (Node / MySQL / Redis)
- **A partly built scaffold, not a working service.** `src/index.js` is a
  stub ("Jobs not yet wired in"). There is no notifier (it's referenced
  but missing), no HTTP API (express is a dependency but unused) and no
  tests.
- `parksCanadaClient.js` has the useful part: the confirmed
  `availability/map` request shape (fresh random cart/booking UUIDs, a
  Referer built from the results URL, `getDailyAvailability=true`) and
  the availability enum (0 unavailable, 1 available, 3 not bookable
  online; 5 seen but unknown, see `KNOWN_ISSUES.md`).
- `availabilityPoller.js` has a sound design: one call per map covering
  the union of all alert windows, 0→1 transition detection, a
  consecutive-nights check, a `notifications_sent` dedupe table and jitter.
- Problems: it keeps its own copy of the catalogue in MySQL, and its
  `resourceModel === 2` filter drops every site-booked Eastern park
  (Fundy, Bruce, Kejimkujik, …, which `backcountry_sites` already handles
  correctly). Alerts are keyed by campground *location*, not site. It has
  no user accounts (just an email plus a cancel token).
- The frontend `/campalert` page is a mock: a hard-coded list of 4 trails,
  and the form submits nowhere.

## 2. Availability and alerts: recommendation

**Move alerts into the Python backend.** Keep campalert-service in the repo
until Phase 3 works, then retire it (a separate decision for you).

Why:
1. **One Parks Canada client, one rate limit.** A global cap on polling is
   only enforceable if every request goes through one client. With two
   services, both the on-demand checks (Python, needed for the trail page
   anyway) and the poller (Node) hit reservation.pc.gc.ca with separate
   budgets.
2. **The data already lives in Postgres.** Alerts belong to Supabase users
   and must link to `backcountry_sites` and trip plans. In Node they'd need
   cross-database IDs, service-to-service auth and a second copy of the
   catalogue (the one with the Eastern-parks bug).
3. **Auth and RLS come for free.** "View and cancel my alerts" is the same
   owner-only pattern as gear setups.
4. **Less to run.** Node + MySQL + Redis would add three moving parts for a
   job that is a loop over a few dozen map groups every few minutes.
5. **Little working code is lost.** What's valuable in the Node service is
   knowledge (request shape, enum, poller design), and that ports directly.

Cost: we need a scheduled poller process (`python scripts/poll_alerts.py`,
run by cron or a worker every N minutes, not inside uvicorn) and an email
sender (the backend has none today).

### Proposed mechanics
- **On-demand check** (`GET /api/trails/{id}/availability?start=&nights=&party=`):
  groups the trail's sites by `(provider_location_id, provider_map_id,
  provider_booking_category_id)`. That's usually one or two
  `availability/map` calls per trail. Results go in a shared Postgres
  `availability_cache` table (5 minute TTL) so the API workers and the
  poller share it. Every call goes through a global token bucket (e.g. at
  most 1 request/s and 30/min across the app). When the budget is used up
  the user gets "busy, try again in a minute", never a queue that piles up.
- **Alert poller**: every 10 minutes (with jitter), it collects active
  alerts, merges them into map groups with one window each (the
  campalert-service design), and stops after a fixed number of requests
  per run (e.g. 20) with a 2 s spacing. Alerts are capped at 10 active per
  user and at most 14 nights each, and expire once their first night has
  passed. An alert fires **once**, when the whole requested window is
  available at that site. It then moves to `notified`, and the user can
  re-arm it. This avoids repeated emails as quota flickers.
- **Availability values**: 1 is available, 0 is full, 3 isn't bookable
  online. Unknown values (such as 5) show as "unknown" and never trigger an
  alert. Permits (WCT, Long Range) and site-booked parks use other booking
  categories, and I haven't verified their availability responses yet (see
  the open questions).

## 3. Data model

All new tables get RLS, follow the existing revoke-then-grant pattern, and
are created in migrations chained off the single head (`f270bc5e799a` today).

### Trail ↔ campground links (Phase 2)
```
trail_campgrounds
  trail_id      uuid  FK trails  ON DELETE RESTRICT
  site_id       uuid  FK backcountry_sites  ON DELETE RESTRICT
  route_order   smallint NOT NULL CHECK (>= 1)   -- ties allowed: pads at one stop
  stop_name     text NULL      -- groups individually booked pads ("Fish Harbour")
  notes         text NULL
  confidence    text NOT NULL CHECK (in ('exact','likely'))
  source        text NOT NULL  -- 'catalog_data/trail_campgrounds.json'
  created_at, updated_at
  PRIMARY KEY (trail_id, site_id)
  RLS: public read; no write policies (seed/backend only)

trail_booking_systems
  trail_id      uuid  FK trails
  system        text   -- 'parks_canada', 'bc_parks', 'alberta_parks', …
  covers        text CHECK (in ('all','partial'))
  note          text NULL
  position      smallint
  PRIMARY KEY (trail_id, system)
  RLS: public read
```
The display names and URLs for booking systems stay in the mapping file
and the API (they're product copy, not data). The seed upserts both tables
and never deletes a link whose site was retired. The API returns
`retired: true` so the page can show "No longer listed by Parks Canada".
A link that disappears from the mapping file *is* removed, because that's
an editorial decision. The seed reports these removals.

### Alerts (Phase 3)
```
availability_alerts
  id, user_id (default auth.uid(), FK auth.users ON DELETE CASCADE)
  site_id       FK backcountry_sites
  start_date    date, nights smallint CHECK (1..14), party_size smallint
  status        'active' | 'notified' | 'cancelled' | 'expired'
  trip_plan_id  FK trip_plans ON DELETE SET NULL, NULL
  last_checked_at, notified_at, created_at, updated_at
  RLS: owner select/update(status → cancelled) only

availability_cache
  cache_key text PK, response jsonb, fetched_at timestamptz
  RLS on, no policies (backend only)
```

### Trip plans (Phase 4)
```
trip_plans
  id, user_id (owner, as above)
  trail_id     FK trails ON DELETE RESTRICT
  setup_id     FK gear_setups ON DELETE SET NULL   -- deleting a setup keeps the plan
  title        text NULL (≤ 80)
  start_date   date NOT NULL
  nights       smallint CHECK (1..21)
  party_size   smallint CHECK (1..12)
  notes        text NULL (≤ 2000)
  created_at, updated_at
  RLS: owner-only, like gear_setups

trip_plan_nights
  trip_plan_id  FK trip_plans ON DELETE CASCADE
  night_index   smallint  (0 .. nights-1; date = start_date + index)
  site_id       FK backcountry_sites NULL  -- NULL = not chosen / camping outside the system
  booked_by_me  boolean NOT NULL DEFAULT false
  PRIMARY KEY (trip_plan_id, night_index)
```
The API only accepts a `site_id` from that trail's `trail_campgrounds`.
Shortening a trip deletes the extra nights. Each night's status is
**derived**, not stored: *booked by me* (the flag) → *alert set* (an
active alert covering that site and date) → *available* / *full*
(fetched on demand from the cache) → *not checked*.

Missing core gear: a plan warns when its setup has no item in the
**shelter** (tents/tarps/bivy) or **sleeping bag/quilt** slot, and notes a
missing **sleeping pad**. The categories come from `slots.ts` (the core
slots). That logic lives in the frontend, next to the slot mapping.

## 4. First trail ↔ campground mappings

The draft is in `backend/catalog_data/trail_campgrounds.json`. It covers
**all 34 overnight trails** in the top 100 and has **69 links on 15
trails**. Every resource ID, name, code and kind was checked against the
local catalogue: all 69 resolve to publicly listed, unretired sites.

Ordering rule: Banff campground codes are trail + km (`Sk5`, `Sk11`,
`Sk18`), and Jasper numbers run along each route, so ordering by code is
reliable there. Elsewhere I used route knowledge.

| Trail | Links | Confidence | Notes |
| --- | --- | --- | --- |
| West Coast Trail | 3 permits (Pachena, Nitinaht, Gordon River) | exact | Entry permits, not campgrounds |
| Skyline Trail (AB) | Evelyn Creek → Signal (27–32) | exact | Watchtower (33) excluded |
| Lake O'Hara / Elizabeth Parker Hut | Lake O'Hara Backcountry Sites | exact | Hut is ACC |
| Mount Assiniboine via Sunshine | Howard Douglas Lake (Su8) | exact | The rest is BC Parks |
| Rockwall Trail | Floe → Numa → Tumbling → Helmet Falls → Helmet/Ochre | exact | |
| Fundy Footpath | Point Wolfe PW162/164, Goose River GR4–6 | **likely** | The Footpath's own sites are Fundy Trail Parkway |
| Tonquin Valley | Astoria → Portal (42–48) | exact | |
| Long Range Traverse | LRT permit; combined N+LRT permit | exact / **likely** | |
| Skoki Valley | Hidden Lake, Baker Lake, Merlin Meadows, Red Deer Lakes | exact | |
| Egypt Lake / Healy Pass | Healy Creek (E5), Egypt Lake (E13) | exact | Egypt Lake Shelter is unlisted, so left out |
| Pukaskwa Coastal | 22 pads at 10 stops, Hook Falls → North Swallow | exact ×8, **likely** ×14 | Order of the middle stops unverified |
| Shadow Lake - Twin Lakes loop | Lost Horse Creek, Shadow Lake, Twin Lakes | exact | |
| Glacier Lake | Glacier Lake (Gl9) | exact | |
| Ball Pass | Lost Horse, Shadow Lake (**likely**), Ball Pass Jct (exact) | mixed | |
| Mystic Pass | Larry's Camp, Mystic Valley, Mystic Junction, Mt Cockscomb | mixed | See the description question below |

Overnight trails with **no Parks Canada sites** (they get a "Booked through
…" note):

| Trail | Booked through |
| --- | --- |
| Garibaldi Lake, Panorama Ridge, Elfin Lakes, Wedgemount Lake, Berg Lake | BC Parks |
| Juan de Fuca, Cape Scott | BC Parks backcountry permit (no reserved sites) |
| Kokanee Glacier | BC Parks + Alpine Club of Canada (cabin) |
| Northover Ridge / Three Isle Lake, Elbow Lake | Alberta Parks |
| La Cloche Silhouette, Lake Superior Coastal, Highland Backpacking | Ontario Parks |
| Grizzly Lake | Yukon Parks |
| Mantario Trail | Manitoba Parks |
| Traversée de Charlevoix | The trail operator |
| East Coast Trail, Sunshine Coast Trail | No reservations (first come) |
| Grey Owl Trail | Parks Canada, but **not online** |

Mixed (Parks Canada for part of the route): Mount Assiniboine (BC Parks),
Fundy Footpath (Fundy Trail Parkway), Lake O'Hara (ACC hut), Kokanee (ACC).

## 5. UI flow

Existing tokens (olive / dark olive / cream / tan / rust, display + sans
fonts), the `Dialog` component (including its `sheet` mode on phones) and
`ui.module.css` buttons are reused throughout.

**1. Landing.** The headline and subtext lead with the core flow, and the
search box stays. *Mobile:* unchanged layout.

**2. Explore trails.** Overnight trails get a "Backpacking · 3 nights"
badge and there's a "Backpacking / Day hikes / All" filter. Day hikes stay
listed.

**3. Trail page, overnight.**
- Desktop (≥ 960 px): two columns. On the left: header, stats, about,
  **Campgrounds on this route**, seasons and location. On the right, a
  sticky **Trip dates** card with start date, nights (pre-filled from the
  typical length), party size, *Check availability*, and *Plan this trip*
  as the primary button.
- *Campgrounds on this route* is an ordered list with a numbered rail.
  Each row shows the name and code, a kind chip (Campground / Permit /
  Shelter), the park, "Quota 8 parties per night", and a *Book on Parks
  Canada ↗* link. Pads at one stop are grouped ("Fish Harbour · 3 pads"),
  collapsed by default. Retired sites are shown greyed, with "No longer
  listed by Parks Canada". *Likely* links aren't labelled to users.
- After *Check availability*, each row gets a strip of night cells
  (available / full / not online / unknown) and an *Alert me* button on
  rows that aren't fully available.
- Booked elsewhere: a callout card, "Campsites on this trail are booked
  through **BC Parks** ↗", with the note from the mapping. Mixed trails
  show the Parks Canada list *and* the callout for the other system.
- *Mobile (≤ 640 px):* one column. The Trip dates card turns into a sticky
  bottom bar ("Jul 12 · 3 nights · 2 people  [Check]") that opens a
  `Dialog sheet`. The night strip scrolls horizontally inside each row.
  *Plan this trip* sits in the header actions.
- Day hikes show none of this; the page is unchanged.

**4. Alert dialog** (`Dialog`, `sheet` on phones). It shows the campground,
dates and party, plus "We'll email you at you@… once the whole stay opens
up." Guests see "Sign in to get alerts" and return to the trail with
`?alert=<site>&start=&nights=`, and the dialog reopens, like Save does.

**5. My alerts** (a profile section, linked from the alert success state).
A list with campground, trail, dates and a status chip
(watching / opened up / expired), plus *Cancel* (with a confirm dialog) and
*Re-arm* on notified alerts. *Mobile:* stacked cards.

**6. Plan this trip** (`Dialog`, lg; a full-screen sheet on phones). It
asks for start date, nights and party (pre-filled from the trail page),
then has one row per night with a campground select limited to this
trail's campgrounds in route order (with "Not decided" and "Outside Parks
Canada" options), a gear setup select from the user's setups (with a link
to create one), and notes. Guests are asked to sign in first and return
with the dialog open. Saving opens the plan page.

**7. Plan page** (`/plans?id=`).
- Desktop: a header (trail, dates, party, *Edit*, *Delete*). Left: a
  night-by-night itinerary timeline. Each night shows the date, campground
  (code, park) and a status pill (Booked by me / Alert set / Available /
  Full / Not checked), with a "Mark as booked" toggle, an *Alert me*
  action and a *Book ↗* link. Right: a **gear panel** in the flat-lay mat
  style, with the setup's items as tiles, the total known weight, "3 items
  have no weight", and warning chips for missing shelter, sleeping bag or
  pad.
- *Mobile:* header, itinerary cards, gear panel as a two-column tile grid,
  and Edit / Delete in an overflow menu.

**8. Profile.** A "Trip plans" section (cards with trail, dates, and the
night count and booked count) next to the new "Alerts" section.

## 6. Open questions

1. **`backend/.env` points at the hosted database.** For all local work I'll
   pass `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:44322/postgres`
   explicitly. Do you want `.env` switched to local instead?
2. **Email for alerts.** SendGrid (the campalert-service choice), or SMTP?
   Locally I'd send to the Supabase stack's mail catcher.
3. **Where the poller runs** in production: cron on the API host, a
   separate worker, or a scheduled job? Phase 3 builds it as a CLI script
   either way.
4. **Live calls to capture fixtures.** Tests won't make live calls, but to
   record realistic fixtures (zone, site-booked pad, trail permit) I'd make
   about 3 to 6 `availability/map` calls, spaced out, once. OK?
5. **campalert-service and `/campalert`.** Leave both untouched for now and
   retire them after Phase 3? I'd point the navbar's CampAlert link and
   "Find campsites" at the new flow.
6. **Day hikes with bookable campgrounds.** Some day hikes in the top 100
   have Parks Canada campgrounds on them: Iceline (Little Yoho, Yoho Lake,
   Twin Falls, Laughing Falls), Bertha Lake, Carthew-Alderson (Alderson
   Lake), Green Gardens. They're left out of the mapping because the brief
   says day hikes don't show campgrounds. Should any become overnight
   trips (`typical_duration_nights`)?
7. **Mapping review points.** These are marked in the file under `review`
   and `confidence: likely`: the Pukaskwa middle-stop order, the Fundy
   links, the Mystic Pass exit (its catalogue description says "Panther
   River area"), how Grey Owl is booked, and the non-Parks Canada booking
   systems. I'm fairly sure of those systems, but I didn't verify each
   one, and most of their URLs are left `null` on purpose.
