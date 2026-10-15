"""Sync the backcountry campground / zone catalogue from reservation providers.

Run from backend/:

    python scripts/sync_backcountry.py                  # Parks Canada, using the response cache
    python scripts/sync_backcountry.py --dry-run        # fetch + report, roll back all writes
    python scripts/sync_backcountry.py --refresh-cache  # re-download every response
    python scripts/sync_backcountry.py --no-cache       # live requests, nothing written to disk

Only catalogue endpoints are called (about 55 requests, 1s apart), never
availability. Raw responses are cached in backend/.cache/parks_canada/ so
development reruns don't hit the server; pass --refresh-cache for fresh data.

Re-runnable: sites are upserted by provider resource id; sites that vanish are
retired (retired_at), not deleted. Exit code is 1 if the run was incomplete.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.append(str(BACKEND))

from app.backcountry import parks_canada  # noqa: E402
from app.backcountry.sync import coverage, sync_catalog  # noqa: E402
from app.database import SessionLocal  # noqa: E402

DEFAULT_CACHE = BACKEND / ".cache" / "parks_canada"
DEFAULT_OVERRIDES = BACKEND / "catalog_data" / "backcountry_park_overrides.json"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="roll back instead of committing")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--refresh-cache", action="store_true", help="ignore cached responses (still re-caches)")
    parser.add_argument("--no-cache", action="store_true", help="don't read or write the response cache")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between live requests (default 1)")
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--allow-mass-retire", action="store_true")
    args = parser.parse_args(argv)

    client = parks_canada.ParksCanadaClient(
        None if args.no_cache else args.cache_dir, refresh=args.refresh_cache, delay_s=args.delay
    )
    print(f"Fetching Parks Canada catalogue ({'no cache' if args.no_cache else args.cache_dir}) ...")
    catalog = parks_canada.build_catalog(client.get, park_overrides=parks_canada.load_overrides(args.overrides))
    print(f"  {client.live_requests} live request(s), {client.cache_hits} from cache")
    print(f"  {len(catalog.locations)} backcountry booking locations, {len(catalog.sites)} sites; "
          f"excluded: {dict(catalog.excluded)}")

    db = SessionLocal()
    try:
        report = sync_catalog(
            db, parks_canada.PROVIDER, catalog, datetime.now(timezone.utc),
            allow_mass_retire=args.allow_mass_retire,
        )
        stats = coverage(db, parks_canada.PROVIDER)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    print_report(report, stats, dry_run=args.dry_run)
    return 0 if catalog.complete else 1


def print_report(report, stats, *, dry_run: bool) -> None:
    print(f"\n{'DRY RUN - nothing committed. ' if dry_run else ''}Sync result:")
    print(f"  sites: {report.created} new, {report.updated} updated, {report.unchanged} unchanged, "
          f"{report.restored} restored, {report.retired} retired")
    print(f"  parks: {report.parks_created} new, {report.parks_retired} retired")

    print(f"\nActive sites per park ({stats['total']} total):")
    for park, count in sorted(stats["per_park"].items()):
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(stats["per_kind"][park].items()))
        hidden = stats["gaps"]["not_publicly_listed"].get(park)
        print(f"  {park:42} {count:4}   {kinds}" + (f"   [{hidden} not publicly listed]" if hidden else ""))

    gaps = stats["gaps"]
    print("\nData gaps:")
    print(f"  missing coordinates: {gaps['no_coordinates']} of {stats['total']} (provider exposes none)")
    by_park = {}
    for park, _ in gaps["no_code"]:
        by_park[park] = by_park.get(park, 0) + 1
    print(f"  missing site code: {len(gaps['no_code'])}" +
          "".join(f"\n    {park}: {n}" for park, n in sorted(by_park.items())))
    print(f"  missing province: {len(gaps['no_province'])}")
    print(f"  no park (provider gives no park; add to catalog_data/backcountry_park_overrides.json "
          f"only with evidence): {len(gaps['no_park'])}")
    for unit, name, resource_id in gaps["no_park"]:
        print(f"    [{resource_id}] {name}  ({unit})")
    if report.warnings:
        print("\nWarnings:")
        for warning in report.warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
