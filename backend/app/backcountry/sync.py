"""Upsert a provider's backcountry catalogue into backcountry_parks / backcountry_sites.

Idempotent: rows are matched on (provider, provider id); re-running with the
same catalogue changes nothing. Sites (and parks) missing from a run are
retired, never deleted, and are un-retired if they come back. Retiring is
skipped when the run was incomplete or would retire more than
MAX_RETIRE_FRACTION of the active rows, so a provider outage or a parsing
regression can't wipe the catalogue.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backcountry.parks_canada import Catalog, SiteRecord
from app.models.backcountry import BackcountryPark, BackcountrySite

MAX_RETIRE_FRACTION = 0.2

SITE_FIELDS = [
    f.name for f in fields(SiteRecord) if f.name not in ("provider_resource_id", "park_id")
]


@dataclass
class SyncReport:
    provider: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    restored: int = 0
    retired: int = 0
    parks_created: int = 0
    parks_retired: int = 0
    retire_skipped_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def _same(current, new) -> bool:
    if isinstance(current, Decimal) and new is not None:
        return current == Decimal(str(new))
    return current == new


def sync_catalog(
    db: Session,
    provider: str,
    catalog: Catalog,
    now: datetime,
    *,
    allow_mass_retire: bool = False,
) -> SyncReport:
    report = SyncReport(provider=provider, warnings=list(catalog.warnings))

    parks = {
        p.provider_park_id: p
        for p in db.scalars(select(BackcountryPark).where(BackcountryPark.provider == provider))
    }
    for record in catalog.parks.values():
        park = parks.get(record.provider_park_id)
        if park is None:
            park = BackcountryPark(provider=provider, provider_park_id=record.provider_park_id)
            db.add(park)
            parks[record.provider_park_id] = park
            report.parks_created += 1
        park.name = record.name
        park.province_code = record.province_code
        park.region = record.region
        park.last_synced_at = now
        park.retired_at = None
    db.flush()

    existing = {
        s.provider_resource_id: s
        for s in db.scalars(select(BackcountrySite).where(BackcountrySite.provider == provider))
    }
    seen: set[str] = set()
    for record in catalog.sites:
        if record.provider_resource_id in seen:
            report.warnings.append(f"duplicate resource {record.provider_resource_id} ({record.raw_name}) skipped")
            continue
        seen.add(record.provider_resource_id)

        values = {name: getattr(record, name) for name in SITE_FIELDS}
        values["park_id"] = parks[record.park_id].id if record.park_id else None

        site = existing.get(record.provider_resource_id)
        if site is None:
            db.add(
                BackcountrySite(
                    provider=provider,
                    provider_resource_id=record.provider_resource_id,
                    last_synced_at=now,
                    **values,
                )
            )
            report.created += 1
            continue

        changed = any(not _same(getattr(site, name), value) for name, value in values.items())
        if site.retired_at is not None:
            site.retired_at = None
            report.restored += 1
        elif changed:
            report.updated += 1
        else:
            report.unchanged += 1
        if changed:
            for name, value in values.items():
                setattr(site, name, value)
        site.last_synced_at = now

    missing = [s for rid, s in existing.items() if rid not in seen and s.retired_at is None]
    active = sum(1 for s in existing.values() if s.retired_at is None)
    if not catalog.complete:
        report.retire_skipped_reason = (
            "incomplete run (failed: " + ", ".join(catalog.failed_locations) + ")"
        )
    elif missing and not allow_mass_retire and len(missing) > MAX_RETIRE_FRACTION * active:
        report.retire_skipped_reason = (
            f"{len(missing)} of {active} active sites would be retired "
            f"(> {MAX_RETIRE_FRACTION:.0%}); rerun with --allow-mass-retire if that is real"
        )
    else:
        for site in missing:
            site.retired_at = now
        report.retired = len(missing)
        for park_id, park in parks.items():
            if park_id not in catalog.parks and park.retired_at is None:
                park.retired_at = now
                report.parks_retired += 1
    if report.retire_skipped_reason and missing:
        report.warnings.append(f"retiring {len(missing)} missing site(s) skipped: {report.retire_skipped_reason}")

    db.flush()
    return report


def coverage(db: Session, provider: str) -> dict:
    """Active-site counts per park and data-quality gaps, for the sync report."""
    rows = db.execute(
        select(BackcountrySite, BackcountryPark.name)
        .outerjoin(BackcountryPark, BackcountrySite.park_id == BackcountryPark.id)
        .where(BackcountrySite.provider == provider, BackcountrySite.retired_at.is_(None))
    ).all()
    per_park: Counter = Counter()
    per_kind: dict[str, Counter] = {}
    gaps = {"no_code": [], "no_coordinates": 0, "no_province": [], "no_park": [], "not_publicly_listed": Counter()}
    for site, park_name in rows:
        park = park_name or f"(no park) {site.booking_unit}"
        per_park[park] += 1
        per_kind.setdefault(park, Counter())[site.kind] += 1
        if not site.site_code:
            gaps["no_code"].append((park, site.name))
        if site.latitude is None or site.longitude is None:
            gaps["no_coordinates"] += 1
        if not site.province_code:
            gaps["no_province"].append((park, site.name))
        if site.park_id is None:
            gaps["no_park"].append((site.booking_unit, site.raw_name, site.provider_resource_id))
        if not site.is_publicly_listed:
            gaps["not_publicly_listed"][park] += 1
    return {"total": len(rows), "per_park": per_park, "per_kind": per_kind, "gaps": gaps}
