from functools import lru_cache
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.backcountry.parks_canada import PROVIDER as PARKS_CANADA
from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.database import get_db
from app.models.backcountry import BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailBookingSystem, TrailCampground
from app.models.trail_seasonal_condition import TrailSeasonalCondition
from app.schemas.trail import (
    CampgroundParkOut,
    SeasonalConditionOut,
    Terrain,
    TrailBookingLinkOut,
    TrailBookingOut,
    TrailCampgroundOut,
    TrailCampgroundsOut,
    TrailDetailOut,
    TrailListItemOut,
)
from app.trail_campgrounds import MAPPING_PATH, load_mapping

router = APIRouter(prefix="/api/trails", tags=["trails"])

SEASON_ORDER = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}


@router.get("", response_model=list[TrailListItemOut])
def search_trails(
    q: str = "",
    terrain: Terrain | None = None,
    limit: int = Query(10, ge=1, le=TRAIL_CATALOG_LIMIT),
    db: Session = Depends(get_db),
):
    """Live catalogue only (configured countries, not retired), most popular first."""
    query = db.query(Trail).filter(
        Trail.retired_at.is_(None),
        Trail.country_code.in_(TRAIL_CATALOG_COUNTRIES),
        Trail.popularity_rank.is_not(None),
        Trail.popularity_rank <= TRAIL_CATALOG_LIMIT,
    )
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Trail.name.ilike(like), Trail.region.ilike(like)))
    if terrain:
        query = query.filter(Trail.terrain_difficulty == terrain)
    return query.order_by(Trail.popularity_rank, Trail.name).limit(limit).all()


@router.get("/{trail_id}", response_model=TrailDetailOut)
def get_trail(trail_id: UUID, db: Session = Depends(get_db)):
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")

    conditions = (
        db.query(TrailSeasonalCondition)
        .filter(TrailSeasonalCondition.trail_id == trail_id)
        .all()
    )
    detail = TrailDetailOut.model_validate(trail)
    detail.seasonal_conditions = [
        SeasonalConditionOut.model_validate(condition)
        for condition in sorted(conditions, key=lambda c: SEASON_ORDER.get(c.season, 99))
    ]
    return detail


PARKS_CANADA_RESULTS_URL = "https://reservation.pc.gc.ca/create-booking/results"


@lru_cache
def booking_system_names() -> dict[str, dict]:
    """Display names and URLs per booking system slug, from the mapping file."""
    return load_mapping(MAPPING_PATH)["booking_systems"]


def booking_links(links: list[TrailCampground]) -> list[TrailBookingLinkOut]:
    """One Parks Canada booking form per (booking location, booking category).

    Verified 2026-10-15: results?resourceLocationId=&mapId=&bookingCategoryId=
    opens the Backcountry tab with that park and booking type selected (any of
    the location's maps works; without mapId it falls back to "All
    Locations"). It never selects a campground.
    """
    out: dict[tuple[str, str], TrailBookingLinkOut] = {}
    for link in links:
        site = link.site
        if site.provider != PARKS_CANADA or site.retired_at or not site.provider_map_id:
            continue
        key = (site.provider_location_id, site.provider_booking_category_id or "")
        if key in out:
            continue
        params = {
            "resourceLocationId": site.provider_location_id,
            "mapId": site.provider_map_id,
            "bookingCategoryId": site.provider_booking_category_id,
        }
        if site.kind == "trail_permit":
            label = "Book the trail permit on Parks Canada"
        elif site.park:
            label = f"Book {site.park.name} backcountry on Parks Canada"
        else:
            label = "Book on Parks Canada"
        out[key] = TrailBookingLinkOut(
            label=label,
            url=f"{PARKS_CANADA_RESULTS_URL}?{urlencode({k: v for k, v in params.items() if v})}",
        )
    return list(out.values())


@router.get("/{trail_id}/campgrounds", response_model=TrailCampgroundsOut)
def get_trail_campgrounds(trail_id: UUID, db: Session = Depends(get_db)):
    """The trail's campgrounds in route order, and how its camping is booked.

    Sites the provider doesn't publish (is_publicly_listed = false) are left
    out; retired sites stay in, flagged, so the route still reads correctly.
    """
    trail = db.get(Trail, trail_id)
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")

    links = db.scalars(
        select(TrailCampground)
        .join(BackcountrySite, TrailCampground.site_id == BackcountrySite.id)
        .where(TrailCampground.trail_id == trail_id, BackcountrySite.is_publicly_listed.is_(True))
        .options(selectinload(TrailCampground.site).selectinload(BackcountrySite.park))
    ).all()
    links.sort(key=lambda l: (l.route_order, l.stop_name or "", l.site.site_code or "", l.site.name))

    systems = booking_system_names()
    booking = []
    for row in db.scalars(
        select(TrailBookingSystem)
        .where(TrailBookingSystem.trail_id == trail_id)
        .order_by(TrailBookingSystem.position)
    ):
        known = systems.get(row.system, {})
        booking.append(
            TrailBookingOut(
                system=row.system,
                name=known.get("name") if row.confirmed else None,
                url=known.get("url") if row.confirmed else None,
                covers=row.covers,
                confirmed=row.confirmed,
                note=row.note,
            )
        )

    campgrounds = [
        TrailCampgroundOut(
            site_id=link.site_id,
            route_order=link.route_order,
            stop_name=link.stop_name,
            notes=link.notes,
            confidence=link.confidence,
            retired=link.site.retired_at is not None,
            name=link.site.name,
            site_code=link.site.site_code,
            kind=link.site.kind,
            area=link.site.area,
            park=CampgroundParkOut(name=link.site.park.name, province_code=link.site.park.province_code)
            if link.site.park
            else None,
            reservable_capacity=link.site.reservable_capacity,
            max_capacity=link.site.max_capacity,
            max_group_size=link.site.max_group_size,
            provider=link.site.provider,
        )
        for link in links
    ]
    overnight = (trail.typical_duration_nights or 0) >= 1
    return TrailCampgroundsOut(
        trail_id=trail.id,
        trip_type="overnight" if overnight else "day",
        overnight_option=not overnight and bool(campgrounds),
        route_order_approximate=any(c.confidence == "likely" for c in campgrounds),
        booking=booking,
        booking_links=booking_links(links),
        campgrounds=campgrounds,
    )
