# Backcountry campground catalogue

`backcountry_parks` / `backcountry_sites` hold every backcountry campground,
zone, shelter and trail permit bookable through a reservation provider. Only
Parks Canada (`provider = 'parks_canada'`) is synced today; BC Parks, Alberta
Parks and Ontario Parks can be added as further providers.

```bash
cd backend
python scripts/sync_backcountry.py --dry-run        # fetch + report, commit nothing
python scripts/sync_backcountry.py                  # upsert, retire vanished sites
python scripts/sync_backcountry.py --refresh-cache  # ignore cached responses
```

Raw responses are cached in `backend/.cache/parks_canada/` (gitignored) so
development reruns don't hit the server. Pass `--refresh-cache` for fresh data
in a scheduled run.

## Parks Canada API (reservation.pc.gc.ca, GoingToCamp / Camis)

The API is undocumented and was verified live on 2026-10-15. It returns 403
without browser-like `User-Agent`, `Accept-Language` and `Referer` headers.
The sync calls catalogue endpoints only, about 55 requests a run at 1s
spacing, and never calls `availability/*`.

| Endpoint (`/api/...`) | Used for |
| --- | --- |
| `searchcriteriatabs` | The **Backcountry** tab group: booking categories 5, 7, 4, 13, 17 |
| `bookingcategories` | Booking category → allowed resource categories. 5 Backcountry Campsite (site/cabin/yurt), 7 Backcountry Zone (zone/shelter), 4 West Coast Trail, 13 Long Range Mountains, 17 Chilkoot |
| `resourcecategory` | Category names (mapped to `kind`) |
| `attribute/filterable` | Attribute names: "Out of Park" (excluded), "Maximum Group Size" |
| `maps` (no params) | Organisation tree: All Locations → Western/Central/Eastern → park → booking location |
| `transactionlocation` | Park offices. The postal code's first letter gives the province |
| `resourceLocation` | Booking locations and the resource categories each contains |
| `maps?resourceLocationId=` | Published maps of a location; non-root map titles become `area` (e.g. Jasper "Tonquin Valley") |
| `resourcelocation/resources?resourceLocationId=` | The sites themselves |

`bookingCategoryId=7` on its own covers backcountry **zones** only. The
site-booked parks (Bruce, Fundy, Kejimkujik, Pukaskwa, La Mauricie, …) are in
category 5.

`resourceModel` is the booking model, not a validity flag: 0 = individual
site/pad, 2 = quota zone, 3 = trailhead / non-bookable access point (always
excluded), 4 = permit entry (West Coast Trail, Long Range). This is why
campalert-service's `resourceModel === 2` filter drops every Eastern site
(campalert-service/KNOWN_ISSUES.md).

### Rules

- A location is fetched only if its `resourceCategoryIds` include a
  backcountry category. A full sweep of all locations on 2026-10-15 found no
  backcountry resources outside such locations.
- Excluded: trailheads (`resourceModel` 3), "Out of Park" zones, and any
  non-backcountry resource in a mixed location (e.g. Kluane frontcountry
  sites).
- `is_publicly_listed = false` when none of a site's maps is published.
  Examples: Kluane's registration zones, Lake O'Hara staff/last-minute zones,
  and two Banff shelters with no map. RLS hides these rows from
  anon/authenticated.
- Site codes come in three name formats: `Name - Br17` (Banff),
  `70 - Name` (Jasper), and bare `HD1` / `SHI-3` (site-booked parks). Many
  parks publish no codes at all.
- Coordinates are always NULL. The API exposes none (only pixel positions
  on map images).

### Banff, Kootenay and Yoho

These three parks share one booking location, and the API never says which
park a site is in. The sync resolves it as follows:

1. `catalog_data/backcountry_park_overrides.json` (by resourceId; the sync
   warns if the provider name changes).
2. A Banff-style trail code suffix → Banff (only Banff publishes codes).
3. A "Banff/Yoho/Kootenay Random Camping" map → that park.

Anything else (today: the 42 horse-grazing camps) is left with no park or
province and listed in the sync report. Add new uncoded sites to the override
file.

### Not available online

Gwaii Haanas isn't in the system. Glacier and Mount Revelstoke only expose
Hermit Meadows, Eva Lake and Jade Lakes. Cape Breton Highlands only exposes
Fishing Cove.

## Trail ↔ campground links

`trail_campgrounds` links trails to backcountry sites in route order, and
`trail_booking_systems` records which reservation system(s) book each trail
(for "Booked through BC Parks" notes). Sites have no coordinates, so links
are curated by hand in `catalog_data/trail_campgrounds.json` and seeded:

```bash
cd backend
python scripts/seed_trail_campgrounds.py --dry-run
python scripts/seed_trail_campgrounds.py   # after seed_trails.py and sync_backcountry.py
```

- Trails are keyed by `(name, province_code)`; sites by provider resource id,
  with the provider name alongside so the seed warns if it drifts.
- `confidence: likely` links are curated, not confirmed by Parks Canada; the
  trail page shows "Route order is approximate for some stops".
- `notes` are shown to hikers; `review` holds evidence and open questions
  and is never seeded.
- Booking systems with `confirmed: false` show as "Booked outside Trekly".
  Non-Parks Canada URLs stay `null` until verified.
- Links to retired sites are kept and shown as "No longer listed by Parks
  Canada"; links taken out of the file are removed. Sites with
  `is_publicly_listed = false` are hidden by the API and by RLS.
- A few day hikes (`overnight_option: true`) keep their trip type but show
  their campgrounds as "Also doable as an overnight".

`GET /api/trails/{id}/campgrounds` returns the links in route order with
park, kind and capacity, the trail's booking systems, and `booking_links`:
one Parks Canada booking form per (booking location, booking category).
Verified 2026-10-15: `create-booking/results?resourceLocationId=&mapId=&bookingCategoryId=`
opens the Backcountry tab with that park and booking type selected. It needs
a `mapId` (without one it falls back to "All Locations"), and it never
selects a campground, because Parks Canada builds backcountry trips as an
itinerary in that form. So there are no per-campground booking links.
