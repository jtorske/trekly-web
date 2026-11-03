"""Which campgrounds, and so which trails, an availability alert can watch.

A campground is watchable when it's listed and not retired, it's on Parks
Canada's online booking map (the poller reads availability from that map; see
availability.group_of), and it's a campground rather than a trail permit.
Trail permits (West Coast Trail, Long Range Traverse) are booked as one quota
for the whole route, which alerts don't watch.

A trail is watchable when at least one of its linked campgrounds is. The
trail search, Explore and trail pages get the answer from here, so the
browser never fetches campgrounds per trail to find out.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from uuid import UUID

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.backcountry.parks_canada import PROVIDER as PARKS_CANADA
from app.models.backcountry import BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailBookingSystem, TrailCampground
from app.schemas.trail import BookedThroughOut, TrailAlertsOut
from app.trail_campgrounds import MAPPING_PATH, load_mapping

TRAIL_PERMIT = "trail_permit"

# The SQL form of is_watchable, for one backcountry_sites row.
WATCHABLE_SITE = and_(
    BackcountrySite.provider == PARKS_CANADA,
    BackcountrySite.is_publicly_listed.is_(True),
    BackcountrySite.retired_at.is_(None),
    BackcountrySite.provider_map_id.is_not(None),
    BackcountrySite.provider_booking_category_id.is_not(None),
    BackcountrySite.kind != TRAIL_PERMIT,
)

# True for a trail with at least one watchable campground; correlates to Trail.
TRAIL_IS_WATCHABLE = (
    exists()
    .where(
        TrailCampground.trail_id == Trail.id,
        TrailCampground.site_id == BackcountrySite.id,
        WATCHABLE_SITE,
    )
    .correlate(Trail)
)


def is_watchable(site: BackcountrySite) -> bool:
    return bool(
        site.provider == PARKS_CANADA
        and site.is_publicly_listed
        and site.retired_at is None
        and site.provider_map_id
        and site.provider_booking_category_id
        and site.kind != TRAIL_PERMIT
    )


@lru_cache
def _system_names() -> dict[str, str]:
    return {slug: info["name"] for slug, info in load_mapping(MAPPING_PATH)["booking_systems"].items()}


def trail_alerts(db: Session, trail_ids: Iterable[UUID]) -> dict[UUID, TrailAlertsOut]:
    """Alert facts for each trail, in three queries however many trails."""
    ids = list(dict.fromkeys(trail_ids))
    if not ids:
        return {}
    watchable = set(
        db.scalars(
            select(TrailCampground.trail_id)
            .join(BackcountrySite, TrailCampground.site_id == BackcountrySite.id)
            .where(TrailCampground.trail_id.in_(ids), WATCHABLE_SITE)
            .distinct()
        )
    )
    permits = set(
        db.scalars(
            select(TrailCampground.trail_id)
            .join(BackcountrySite, TrailCampground.site_id == BackcountrySite.id)
            .where(
                TrailCampground.trail_id.in_(ids),
                BackcountrySite.provider == PARKS_CANADA,
                BackcountrySite.kind == TRAIL_PERMIT,
                BackcountrySite.is_publicly_listed.is_(True),
                BackcountrySite.retired_at.is_(None),
            )
            .distinct()
        )
    )
    names = _system_names()
    booked: dict[UUID, BookedThroughOut] = {}
    for row in db.scalars(
        select(TrailBookingSystem)
        # Only a system that books the whole route is named: a hut that
        # books one night (Kokanee Glacier) isn't how the trail is booked.
        .where(
            TrailBookingSystem.trail_id.in_(ids),
            TrailBookingSystem.confirmed.is_(True),
            TrailBookingSystem.covers == "all",
        )
        .order_by(TrailBookingSystem.trail_id, TrailBookingSystem.position)
    ):
        if row.trail_id not in booked and row.system in names:
            booked[row.trail_id] = BookedThroughOut(system=row.system, name=names[row.system])
    return {
        trail_id: TrailAlertsOut(
            has_watchable_campgrounds=trail_id in watchable,
            trail_permit=trail_id in permits,
            booked_through=booked.get(trail_id),
        )
        for trail_id in ids
    }
