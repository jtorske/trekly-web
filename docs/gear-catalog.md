# Gear: catalogue, inventory and setups

## Concepts

- **Catalogue** (`catalog_*` tables) — shared reference data about real
  products: brands, products, variants (sizes/versions), category-specific
  specs, images with licences, and provenance. Read-only for users; written
  only by the import pipeline.
- **Inventory** (`user_gear_items`) — what a user owns. Each row points at a
  catalogue product (optionally a variant) or is a custom item. User-specific
  facts live here: quantity, their own weight override, notes, condition, an
  optional private photo. Editing inventory never changes the catalogue.
- **Setups** (`gear_setups`) — named groups of a user's own items ("Ultralight
  2-Night Kit"). They reference inventory rows; deleting a setup never deletes
  gear, and deleting gear removes it from setups.

Gear is the equipment someone owns, not a per-trip packing list.

## The Gear page

- **Main setup** — seven core slots shown as large showcase cards: backpack,
  tent/shelter, sleeping bag or quilt, sleeping pad, stove or cook system,
  footwear, rain jacket.
- **More gear** — optional slots (pillows, filters, bottles, headlamps, poles,
  first aid, power, …) in a collapsed section so they never dominate.
- Each slot maps to specific catalogue subcategories (`frontend/app/gear/slots.ts`).
  Its picker queries `/api/gear/products?category=<those slugs>`, so the
  backpack picker can only ever return backpacks. Filters: type, brand,
  weight, and capacity for packs/bottles; search; "Show more" pagination.
- Custom items are a secondary "Can't find yours?" option prefilled with the
  slot's category.
- A slot fills only after the API confirms the save. Multiple items per slot
  are allowed; extra ones get their own cards and an "Another …" action.
- Setup chips switch the view between all gear and a saved setup.

## Canonical units and provenance

Mass in grams (`numeric(12,3)`), volume in millilitres, lengths in cm,
temperatures in °C. Conversions use exact constants and `Decimal`
(`backend/app/catalog/normalize.py`). The published figure is kept verbatim in
`specs.published_weight`. Unknown values stay `NULL` — nothing is estimated.
Each weight records its basis (`minimum`, `trail`, `packaged`, `claimed`, …).

Every product links to one or more `catalog_product_sources` rows: source,
stable record id, source URL, verification date and a content hash.

## Data sources actually used

No openly licensed backpacking-gear dataset exists; commercial retailer
scrapes have unclear terms. The catalogue is therefore curated by hand from
manufacturers' own public product pages — facts only, no copied descriptions,
logos or photography.

| Source (provider) | File | Method | Records |
| --- | --- | --- | --- |
| `trekly-curated-manufacturer-specs` (`curated`) | `backend/catalog_data/curated_manufacturer_specs.json` | Official page read directly | 57 |
| `trekly-curated-official-page-excerpts` (`official-excerpts`) | `backend/catalog_data/curated_official_excerpts.json` | Official page as indexed by a search engine, because the site blocks automated fetches (Osprey, Gregory, REI, NEMO, HOKA, Arc'teryx, …) | 56 |

Excerpt records use only figures attributed to the brand's own page and are
one confidence tier below direct reads; where a brand's own listings
conflicted, the value is left unknown with the conflict noted. Re-verify them
when a permitted feed becomes available.

**Images:** no product photos are stored — none were found under a licence
that permits reuse. Cards use Trekly's line illustrations or the user's own
photo. `catalog_product_images` supports licensed images with attribution; only
rows with `approved = true` are ever served.

## Coverage (2026-10-13): 113 products, 41 brands

| Category | Products | Notable brands |
| --- | --- | --- |
| Backpacks | 37 | Osprey 12, Gregory 14, ULA 3, Deuter 2, REI Co-op 2, Kelty, Zpacks, Durston, Gossamer Gear |
| Tents | 13 | MSR 4, NEMO 2, REI Co-op 2, Zpacks 2, Durston, Gossamer Gear, Naturehike |
| Sleeping bags & quilts | 8 | Western Mountaineering 3, Therm-a-Rest 3, Sea to Summit, Enlightened Equipment |
| Sleeping pads | 7 | Therm-a-Rest 5, Sea to Summit, Exped |
| Stoves | 6 | MSR 5, SOTO |
| Footwear | 7 | Altra 2, HOKA, Merrell, La Sportiva, KEEN, Topo Athletic |
| Rain shells | 8 | Arc'teryx 2, Rab 2, Zpacks, Outdoor Research, Patagonia, The North Face |
| Trekking poles | 6 | Black Diamond 3, LEKI, Gossamer Gear, Durston |
| Water treatment / bottles | 5 / 2 | MSR, Platypus, Katadyn, Sawyer |
| Other optional slots | 14 | pillows, stakes, cookware, mug, bear canister & spray, compasses, GPS, first aid, headlamp, dry bag, power bank |

Known gaps: **Big Agnes** (spec tables render only in the browser and aren't
indexed) and **Jetboil** (no per-model specs found on the official site) have
no products. Pack covers, tarps, footprints, bivies, liners, insulation, base
layers, gaiters, camp shoes, watches and repair kits have none yet; those
slots still work with custom items. Some products have partial specs where the
official page didn't list everything (e.g. Garmin inReach Mini 2 has no
weight).

Run `python scripts/catalog.py coverage` for live numbers.

## Maintaining the catalogue

```bash
cd backend
python scripts/catalog.py import --dry-run   # validate every provider, write nothing
python scripts/catalog.py import             # import/update all providers (idempotent)
python scripts/catalog.py coverage           # products per category and brand
python scripts/catalog.py retire msr/hubba-hubba-hd-2   # mark discontinued (never delete)
```

### Adding or updating a curated record

1. Open the manufacturer's official product page. Record only figures printed
   there; leave anything else out.
2. Add or edit a record in the right JSON file: stable `source_record_id`
   (`brand-slug:product-slug`), `category` (a subcategory slug from
   `app/catalog/taxonomy.py`), `source_url`, `verified_at`, and `weight` as
   either published text (`"2 lb 3 oz"`) or a value + unit. Use `variants` for
   sizes with different weights.
3. Spec keys must exist in `app/catalog/specs.py` for that category; unknown
   keys are rejected so typos surface as import errors.
4. Run `import --dry-run`, then `import`. Re-running reports `unchanged`.

### Retiring products

Set `"status": "discontinued"` in the record (or run `retire`). Products are
never deleted, so users who own them keep them in their inventory.

### Adding a data provider

A provider yields dicts in the `CatalogRecord` shape
(`app/catalog/records.py`); the pipeline does validation, normalization,
deduplication (stable source ids, brand aliases, brand+slug) and upserts.

1. Confirm the source's terms allow this use and record them in the source's
   `terms_notes`.
2. For a spreadsheet feed, use `CsvFeedProvider` with a column map — no code
   needed: `python scripts/catalog.py import --csv feed.csv --source-slug acme --source-name "Acme feed" --source-kind licensed_feed`.
3. For an API, implement `source` + `records()` (see
   `app/catalog/providers/base.py`) and register it in
   `app/catalog/providers/__init__.py`.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/gear/categories` | taxonomy tree |
| GET | `/api/gear/brands?q=&category=` | brands with products |
| GET | `/api/gear/products?q=&category=&brand=&max_weight_g=&min_capacity_ml=&max_capacity_ml=&include_discontinued=&cursor=&limit=` | `category` accepts a comma-separated list; opaque `next_cursor`; typo-tolerant search on Postgres (pg_trgm) only when nothing matches exactly |
| GET | `/api/gear/products/{id}` | detail with variants and sources |
| GET/POST | `/api/me/gear` | list with summary / add (send `client_request_id` to make retries idempotent) |
| PATCH/DELETE | `/api/me/gear/{id}` | edit, replace product, convert to custom / remove |
| GET/POST | `/api/me/setups` | list / create |
| PATCH/DELETE | `/api/me/setups/{id}` | edit / delete (gear unaffected) |
| GET/PATCH | `/api/me/profile` | private profile and counts |
| GET | `/api/me/saved-trails` | bookmarks |
| PUT/DELETE | `/api/me/saved-trails/{trail_id}` | idempotent save / unsave |
| DELETE | `/api/me` | delete account (`{"confirm": "delete my account"}`) |

`/api/me/*` requires `Authorization: Bearer <Supabase access token>`; another
user's ids return 404.
