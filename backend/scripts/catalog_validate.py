"""Pre-import validation report for the curated gear catalogue.

Checks every record in backend/catalog_data/curated_*.json without touching
the database:

- schema: the record validates as a CatalogRecord (category, specs, units)
- slot: its category maps to a Gear-mat slot in frontend/app/gear/slots.ts
  (and every taxonomy subcategory has one)
- weight: canonical grams, plausible for
  its category (hard bounds per subcategory, plus a robust outlier test)
- capacity: canonical millilitres, plausible bounds for packs/cookware
- duplicates: the same brand + product name appearing twice
- links (optional, --links): every source_url answers 200, fetched politely
  with scripts/catalog_fetch.py (robots.txt, rate limit, identifying UA)

Run from backend/:

    python scripts/catalog_validate.py                 # offline checks
    python scripts/catalog_validate.py --links         # + source_url checks
    python scripts/catalog_validate.py --markdown out.md

Exit code is 1 if any record fails a hard check (schema, slot, duplicate).
Weight outliers, weightless records and link failures are reported for
review, not failed.
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.catalog.normalize import slugify  # noqa: E402
from app.catalog.providers import CURATED_FILES  # noqa: E402
from app.catalog.records import CatalogRecord, normalize_record  # noqa: E402
from app.catalog.taxonomy import SUBCATEGORY_TO_TOP  # noqa: E402

SLOTS_FILE = Path(__file__).resolve().parents[2] / "frontend" / "app" / "gear" / "slots.ts"

# Plausible claimed weight per item (grams). Generous on purpose: these catch
# unit slips (oz read as g, kg as g, a pair entered as one) rather than judge gear.
WEIGHT_BOUNDS_G: dict[str, tuple[float, float]] = {
    "backpacks": (150, 3500),
    "pack-accessories": (10, 400),
    "tents": (250, 6000),
    "tarps": (100, 2000),
    "footprints": (50, 1000),
    "bivy-sacks": (100, 1200),
    "stakes-guylines": (3, 400),
    "sleeping-bags": (300, 3500),
    "quilts": (250, 2000),
    "sleeping-pads": (60, 2500),
    "pillows": (25, 500),
    "sleep-liners": (50, 800),
    "rainwear": (80, 900),
    "insulation": (100, 1200),
    "fleece-midlayers": (80, 900),
    "base-layers": (60, 600),
    "wind-layers": (30, 400),
    "headwear-gloves": (10, 400),
    "stoves": (25, 1500),
    "cookware": (40, 1200),
    "fuel-accessories": (20, 800),
    "utensils": (5, 300),
    "food-storage": (20, 2000),
    "water-treatment": (5, 1200),
    "bottles-reservoirs": (15, 600),
    "hiking-boots": (200, 1200),
    "trail-runners": (150, 600),
    "gaiters": (20, 400),
    "camp-shoes": (50, 700),
    "gps-satellite": (50, 500),
    "compasses": (10, 200),
    "watches": (20, 200),
    "first-aid": (30, 1500),
    "emergency": (10, 500),
    "bear-safety": (150, 1500),
    "lighting": (20, 400),
    "trekking-poles": (100, 800),
    "storage": (5, 500),
    "repair": (5, 300),
    "power": (50, 700),
    "camp-furniture": (200, 2500),
    "sanitation": (10, 200),
    "misc": (1, 3000),
}

CAPACITY_BOUNDS_L: dict[str, tuple[float, float]] = {
    "backpacks": (10, 110),
    "pack-accessories": (5, 120),
    "cookware": (0.2, 5),
    "utensils": (0.1, 1),
    "storage": (0.5, 120),
    "bottles-reservoirs": (0.3, 10),
    "water-treatment": (0.3, 12),
    "stoves": (0.5, 3),
}

OUTLIER_LOG_MAD = 3.5  # robust z-score on log(weight) within a category


def slot_categories() -> dict[str, str]:
    """subcategory slug -> slot key, parsed from the frontend slot table."""
    text = SLOTS_FILE.read_text(encoding="utf-8")
    mapping: dict[str, str] = {}
    for key, cats in re.findall(r'key:\s*"([^"]+)"[^}]*?categories:\s*\[([^\]]*)\]', text):
        for cat in re.findall(r'"([^"]+)"', cats):
            mapping[cat] = key
    return mapping


def load_records() -> list[tuple[str, dict]]:
    out = []
    for path in CURATED_FILES:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        out.extend((Path(path).name, record) for record in payload["records"])
    return out


def weights_of(normalized) -> list[tuple[str, float]]:
    rows = []
    if normalized.weight_g is not None:
        rows.append(("(product)", float(normalized.weight_g)))
    rows.extend((v.name, float(v.weight_g)) for v in normalized.variants if v.weight_g is not None)
    return rows


def capacities_of(normalized) -> list[tuple[str, float]]:
    rows = []
    if normalized.capacity_ml is not None:
        rows.append(("(product)", float(normalized.capacity_ml) / 1000))
    rows.extend((v.name, float(v.capacity_ml) / 1000) for v in normalized.variants if v.capacity_ml is not None)
    return rows


def link_status(urls: list[str]) -> dict[str, str]:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import catalog_fetch as cf  # noqa: PLC0415 — only needed with --links
    from urllib.parse import urlsplit  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    results: dict[str, str] = {}
    with cf._client() as client:
        for url in urls:
            allowed, reason = cf.robots_allows(client, url)
            if not allowed:
                results[url] = f"not checked ({reason})"
                continue
            cf._wait(urlsplit(url).netloc)
            try:
                response = client.get(url)
                status = str(response.status_code)
                if response.status_code == 200 and str(response.url).rstrip("/") != url.rstrip("/"):
                    final = str(response.url)
                    # A redirect to a home page means the product page is gone.
                    if urlsplit(final).path in ("", "/") or re.fullmatch(r"/[a-z]{2}(-[a-z]{2})?/?", urlsplit(final).path):
                        status = f"redirected to home ({final})"
            except httpx.HTTPError as error:
                status = error.__class__.__name__
            results[url] = status
            print(f"  {status:>4} {url}", file=sys.stderr, flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--links", action="store_true", help="also GET every source_url (slow, polite)")
    parser.add_argument("--markdown", help="write the report to this file as Markdown")
    args = parser.parse_args()

    slots = slot_categories()
    unmapped_taxonomy = sorted(set(SUBCATEGORY_TO_TOP) - set(slots))
    records = load_records()

    hard: list[str] = []
    outliers: list[str] = []
    capacity_flags: list[str] = []
    weightless: list[str] = []
    per_category: dict[str, list[tuple[str, float]]] = defaultdict(list)
    normalized_by_id = {}
    counts = Counter()
    brands = Counter()
    seen_names: dict[tuple[str, str], str] = {}

    for file_name, raw in records:
        rid = raw.get("source_record_id", "?")
        try:
            normalized = normalize_record(CatalogRecord.model_validate(raw))
        except Exception as error:  # noqa: BLE001 — report every bad record
            hard.append(f"{rid} ({file_name}): invalid record: {str(error).splitlines()[0]}")
            continue
        record = normalized.record
        normalized_by_id[rid] = normalized
        counts[record.category] += 1
        brands[record.brand] += 1
        key = (slugify(record.brand), normalized.product_slug)
        if key in seen_names:
            hard.append(f"{rid}: duplicate of {seen_names[key]} (same brand and name)")
        seen_names[key] = rid
        if record.category not in slots:
            hard.append(f"{rid}: category '{record.category}' has no Gear-mat slot")
        weights = weights_of(normalized)
        if not weights:
            # Allowed (the importer stores unknown as NULL, never a guess), but
            # listed: such items count as "unknown weight" on the mat.
            weightless.append(f"{rid}: no published weight on the product or any variant")
        for label, grams in weights:
            low, high = WEIGHT_BOUNDS_G[record.category]
            if not low <= grams <= high:
                outliers.append(
                    f"{rid} {label}: {grams:g} g is outside the {low:g}-{high:g} g range for {record.category}"
                )
            per_category[record.category].append((f"{rid} {label}", grams))
        for label, litres in capacities_of(normalized):
            bounds = CAPACITY_BOUNDS_L.get(record.category)
            if bounds and not bounds[0] <= litres <= bounds[1]:
                capacity_flags.append(
                    f"{rid} {label}: {litres:g} L is outside {bounds[0]:g}-{bounds[1]:g} L for {record.category}"
                )

    # Robust outliers: far from the category's typical weight on a log scale.
    for category, rows in per_category.items():
        if len(rows) < 6:
            continue
        logs = [math.log(grams) for _, grams in rows]
        median = statistics.median(logs)
        mad = statistics.median(abs(value - median) for value in logs) or 1e-9
        for (label, grams), value in zip(rows, logs):
            score = 0.6745 * (value - median) / mad
            if abs(score) > OUTLIER_LOG_MAD:
                typical = math.exp(median)
                outliers.append(
                    f"{label}: {grams:g} g is unusually {'heavy' if score > 0 else 'light'} for {category} "
                    f"(typical {typical:.0f} g, robust z {score:+.1f})"
                )

    links: dict[str, str] = {}
    if args.links:
        urls = sorted({raw["source_url"] for _, raw in records})
        links = link_status(urls)
    bad_links = {url: status for url, status in links.items() if status != "200"}

    lines = ["# Gear catalogue validation report", ""]
    lines.append(f"- Records: **{len(records)}** in {len(CURATED_FILES)} files; brands: {len(brands)}")
    lines.append(f"- Hard failures: **{len(hard)}**; weight flags: **{len(outliers)}**; capacity flags: **{len(capacity_flags)}**")
    if args.links:
        lines.append(f"- source_url checked: {len(links)}; not 200: **{len(bad_links)}**")
    lines.append(f"- Taxonomy subcategories without a slot: {', '.join(unmapped_taxonomy) or 'none'}")
    lines.append("- Units: weights are stored in grams and capacities in millilitres (shown as litres); "
                 "every record passes the importer's unit conversion")
    sections = [
        ("Hard failures", hard),
        ("Weight flags (review)", sorted(set(outliers))),
        ("Capacity flags (review)", capacity_flags),
        ("No published weight (review)", weightless),
        ("source_url not 200", [f"{status} — {url}" for url, status in sorted(bad_links.items())]),
    ]
    for title, items in sections:
        lines += ["", f"## {title}", ""]
        lines += [f"- {item}" for item in items] or ["- none"]
    lines += ["", "## Products per category", ""]
    for top_category in dict.fromkeys(SUBCATEGORY_TO_TOP.values()):
        subs = [sub for sub, top in SUBCATEGORY_TO_TOP.items() if top == top_category]
        total = sum(counts[sub] for sub in subs)
        detail = ", ".join(f"{sub} {counts[sub]}" for sub in subs if counts[sub])
        lines.append(f"- **{top_category}** {total}: {detail}")
    lines += ["", "## Products per brand", "", ", ".join(f"{b} {n}" for b, n in sorted(brands.items(), key=lambda x: (-x[1], x[0])))]
    report = "\n".join(lines) + "\n"
    if args.markdown:
        Path(args.markdown).write_text(report, encoding="utf-8")
    print(report)
    return 1 if hard or unmapped_taxonomy else 0


if __name__ == "__main__":
    raise SystemExit(main())
