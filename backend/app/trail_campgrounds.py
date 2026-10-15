"""Seed trail_campgrounds / trail_booking_systems from catalog_data/trail_campgrounds.json.

The mapping file is the source of truth and the seed is idempotent:

- Links and booking rows are upserted on (trail, site) / (trail, system);
  re-running with an unchanged file changes nothing.
- A link whose site the provider has since retired is kept (and reported),
  so the trail page can show it as no longer listed.
- A link or booking row that was taken out of the file is removed: that's an
  editorial decision. Rows of a trail that couldn't be resolved this run are
  never touched.
- The whole file is validated before anything is written.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backcountry import BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import (
    BOOKING_COVERAGE,
    LINK_CONFIDENCES,
    TrailBookingSystem,
    TrailCampground,
)

MAPPING_PATH = Path(__file__).resolve().parents[1] / "catalog_data" / "trail_campgrounds.json"
SOURCE = "catalog_data/trail_campgrounds.json"
DEFAULT_PROVIDER = "parks_canada"

LINK_FIELDS = ("route_order", "stop_name", "notes", "confidence", "source")
BOOKING_FIELDS = ("covers", "confirmed", "note", "position")


class MappingError(ValueError):
    pass


@dataclass
class SeedReport:
    links_created: int = 0
    links_updated: int = 0
    links_unchanged: int = 0
    links_removed: list[str] = field(default_factory=list)
    booking_created: int = 0
    booking_updated: int = 0
    booking_unchanged: int = 0
    booking_removed: list[str] = field(default_factory=list)
    retired_links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        mapping = json.load(f)
    validate_mapping(mapping)
    return mapping


def validate_mapping(mapping: dict) -> None:
    systems = mapping.get("booking_systems") or {}
    seen_trails = set()
    errors = []
    for entry in mapping.get("trails", []):
        key = (entry.get("name"), entry.get("province_code"))
        label = f"{key[0]} ({key[1]})"
        if not key[0] or not key[1]:
            errors.append(f"trail entry without name/province_code: {entry}")
        if key in seen_trails:
            errors.append(f"{label}: listed twice")
        seen_trails.add(key)
        if not entry.get("booking"):
            errors.append(f"{label}: no booking systems")
        seen_systems = set()
        for booking in entry.get("booking", []):
            if booking.get("system") not in systems:
                errors.append(f"{label}: unknown booking system {booking.get('system')!r}")
            if booking.get("covers") not in BOOKING_COVERAGE:
                errors.append(f"{label}: covers must be one of {BOOKING_COVERAGE}")
            if booking.get("system") in seen_systems:
                errors.append(f"{label}: booking system {booking['system']} listed twice")
            seen_systems.add(booking.get("system"))
        seen_sites = set()
        for link in entry.get("campgrounds", []):
            rid = link.get("resource_id")
            if not rid:
                errors.append(f"{label}: campground without resource_id")
            if (link.get("provider", DEFAULT_PROVIDER), rid) in seen_sites:
                errors.append(f"{label}: site {rid} listed twice")
            seen_sites.add((link.get("provider", DEFAULT_PROVIDER), rid))
            if link.get("confidence") not in LINK_CONFIDENCES:
                errors.append(f"{label}: {rid} confidence must be one of {LINK_CONFIDENCES}")
            order = link.get("order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 1:
                errors.append(f"{label}: {rid} order must be a positive integer")
    if errors:
        raise MappingError("invalid trail_campgrounds mapping:\n  " + "\n  ".join(errors))


def seed_trail_campgrounds(db: Session, mapping: dict, source: str = SOURCE) -> SeedReport:
    """Apply the mapping (caller commits)."""
    validate_mapping(mapping)
    report = SeedReport()

    trails = {(t.name, t.province_code): t for t in db.scalars(select(Trail))}
    sites = {
        (s.provider, s.provider_resource_id): s for s in db.scalars(select(BackcountrySite))
    }
    links = {(l.trail_id, l.site_id): l for l in db.scalars(select(TrailCampground))}
    bookings = {(b.trail_id, b.system): b for b in db.scalars(select(TrailBookingSystem))}

    resolved_trail_ids = set()
    unresolved_trail_ids = set()  # trails whose entry had an unresolvable site
    wanted_links = set()
    wanted_bookings = set()

    for entry in mapping["trails"]:
        label = f"{entry['name']} ({entry['province_code']})"
        trail = trails.get((entry["name"], entry["province_code"]))
        if trail is None:
            report.warnings.append(f"{label}: no such trail; skipped")
            continue
        resolved_trail_ids.add(trail.id)
        if trail.retired_at is not None:
            report.warnings.append(f"{label}: trail is retired; links kept")

        for position, booking in enumerate(entry["booking"]):
            values = {
                "covers": booking["covers"],
                "confirmed": booking.get("confirmed", True),
                "note": booking.get("note"),
                "position": position,
            }
            wanted_bookings.add((trail.id, booking["system"]))
            _upsert(
                db, bookings, (trail.id, booking["system"]),
                lambda: TrailBookingSystem(trail_id=trail.id, system=booking["system"]),
                values, BOOKING_FIELDS, report, "booking",
            )

        for link in entry["campgrounds"]:
            provider = link.get("provider", DEFAULT_PROVIDER)
            site = sites.get((provider, link["resource_id"]))
            if site is None:
                report.warnings.append(
                    f"{label}: site {provider}:{link['resource_id']} ({link.get('name')}) not in the catalogue; "
                    "skipped, and this trail's existing links are left alone"
                )
                unresolved_trail_ids.add(trail.id)
                continue
            if link.get("name") and link["name"] != site.name:
                report.warnings.append(
                    f"{label}: mapping expects '{link['name']}' for {link['resource_id']} but the catalogue says '{site.name}'"
                )
            if site.retired_at is not None:
                report.retired_links.append(f"{label}: {site.name} ({link['resource_id']})")
            if not site.is_publicly_listed:
                report.warnings.append(f"{label}: {site.name} is not publicly listed; the API hides it")
            values = {
                "route_order": link["order"],
                "stop_name": link.get("stop"),
                "notes": link.get("notes"),
                "confidence": link["confidence"],
                "source": source,
            }
            wanted_links.add((trail.id, site.id))
            _upsert(
                db, links, (trail.id, site.id),
                lambda: TrailCampground(trail_id=trail.id, site_id=site.id),
                values, LINK_FIELDS, report, "links",
            )

    trail_names = {t.id: f"{t.name} ({t.province_code})" for t in trails.values()}
    # Only prune trails we fully resolved this run (or that left the file
    # entirely and still exist).
    mapped_keys = {(e["name"], e["province_code"]) for e in mapping["trails"]}
    unmapped_trail_ids = {t.id for key, t in trails.items() if key not in mapped_keys}
    prunable = (resolved_trail_ids - unresolved_trail_ids) | unmapped_trail_ids
    site_names = {s.id: s.name for s in sites.values()}
    for key, link in links.items():
        if key not in wanted_links and link.trail_id in prunable:
            db.delete(link)
            report.links_removed.append(f"{trail_names.get(link.trail_id)}: {site_names.get(link.site_id)}")
    for key, booking in bookings.items():
        if key not in wanted_bookings and booking.trail_id in prunable:
            db.delete(booking)
            report.booking_removed.append(f"{trail_names.get(booking.trail_id)}: {booking.system}")

    db.flush()
    return report


def _upsert(db, existing, key, factory, values, fields, report, kind):
    row = existing.get(key)
    if row is None:
        row = factory()
        for name in fields:
            setattr(row, name, values[name])
        db.add(row)
        existing[key] = row
        setattr(report, f"{kind}_created", getattr(report, f"{kind}_created") + 1)
        return
    changed = [name for name in fields if getattr(row, name) != values[name]]
    for name in changed:
        setattr(row, name, values[name])
    counter = f"{kind}_updated" if changed else f"{kind}_unchanged"
    setattr(report, counter, getattr(report, counter) + 1)
