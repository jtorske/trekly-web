import math
from functools import lru_cache
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.backcountry.parks_canada import PROVIDER as PARKS_CANADA
from app.catalog.search import escape_like
from app.config import TRAIL_CATALOG_COUNTRIES, TRAIL_CATALOG_LIMIT
from app.database import get_db
from app.models.backcountry import BackcountrySite
from app.models.trail import Trail
from app.models.trail_campground import TrailBookingSystem, TrailCampground
from app.models.trail_seasonal_condition import TrailSeasonalCondition
from app.schemas.trail import (
    CampgroundParkOut,
    NearIn,
    ParkFacetOut,
    ParkTypeFacetOut,
    ParkTypeFilter,
    ProvinceFacetOut,
    SeasonalConditionOut,
    Terrain,
    TrailBookingLinkOut,
    TrailBookingOut,
    TrailCampgroundOut,
    TrailCampgroundsOut,
    TrailDetailOut,
    TrailFacetsOut,
    TrailListItemOut,
    TrailSearchIn,
    TrailSearchItemOut,
    TrailSearchOut,
    TripType,
)
from app.trail_campgrounds import MAPPING_PATH, load_mapping

router = APIRouter(prefix="/api/trails", tags=["trails"])

SEASON_ORDER = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}


def live_trails():
    """Live catalogue only: configured countries, not retired, within the cap."""
    return (
        Trail.retired_at.is_(None),
        Trail.country_code.in_(TRAIL_CATALOG_COUNTRIES),
        Trail.popularity_rank.is_not(None),
        Trail.popularity_rank <= TRAIL_CATALOG_LIMIT,
    )


# Explore's three park-type options; "other" is regional parks and no park.
PARK_TYPE_BUCKET = case(
    (Trail.park_type == "national", "national"),
    (Trail.park_type == "provincial", "provincial"),
    else_="other",
)
PARK_TYPE_FILTERS: tuple[ParkTypeFilter, ...] = ("national", "provincial", "other")
EARTH_RADIUS_KM = 6371.0


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle (haversine) distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def distances_from(db: Session, near: NearIn) -> dict[UUID, float]:
    """Km from `near` to each live trail that has coordinates. The catalogue
    is capped at TRAIL_CATALOG_LIMIT rows, so this is one small read."""
    rows = db.execute(
        select(Trail.id, Trail.latitude, Trail.longitude).where(
            *live_trails(), Trail.latitude.is_not(None), Trail.longitude.is_not(None)
        )
    )
    return {
        trail_id: distance_km(near.lat, near.lng, float(lat), float(lng))
        for trail_id, lat, lng in rows
    }


def filter_conditions(
    q: str = "",
    terrain: Terrain | None = None,
    trip: TripType | None = None,
    provinces: list[str] = (),
    park_types: list[ParkTypeFilter] = (),
    parks: list[str] = (),
    within_ids: set[UUID] | None = None,
) -> dict[str, list]:
    """WHERE clauses keyed by filter, so a facet can leave out its own."""
    conditions: dict[str, list] = {}
    if q:
        # Escaped so "%" or "_" in the search box match literally, not everything.
        like = f"%{escape_like(q)}%"
        conditions["q"] = [or_(
            Trail.name.ilike(like, escape="\\"),
            Trail.region.ilike(like, escape="\\"),
            Trail.park_name.ilike(like, escape="\\"),
        )]
    if terrain:
        conditions["terrain"] = [Trail.terrain_difficulty == terrain]
    if trip == "overnight":
        conditions["trip"] = [Trail.typical_duration_nights >= 1]
    elif trip == "day":
        conditions["trip"] = [Trail.typical_duration_nights == 0]
    if provinces:
        conditions["province"] = [Trail.province_code.in_([p.upper() for p in provinces])]
    if park_types:
        options = [Trail.park_type == t for t in ("national", "provincial") if t in park_types]
        if "other" in park_types:
            options.append(or_(Trail.park_type.is_(None), Trail.park_type.in_(("regional", "none"))))
        conditions["park_type"] = [or_(*options)]
    if parks:
        conditions["park"] = [Trail.park_name.in_(parks)]
    if within_ids is not None:
        conditions["near"] = [Trail.id.in_(within_ids)]
    return conditions


def where(conditions: dict[str, list], leave_out: str | None = None) -> list:
    return [*live_trails(), *(c for key, cs in conditions.items() if key != leave_out for c in cs)]


@router.get("", response_model=list[TrailListItemOut])
def search_trails(
    q: str = "",
    terrain: Terrain | None = None,
    trip: TripType | None = None,
    province: list[str] = Query([]),
    park_type: list[ParkTypeFilter] = Query([]),
    park: list[str] = Query([]),
    limit: int = Query(10, ge=1, le=TRAIL_CATALOG_LIMIT),
    db: Session = Depends(get_db),
):
    """Live catalogue only (configured countries, not retired), most popular first.

    `trip=overnight` keeps backpacking trips (one or more typical nights);
    `trip=day` keeps day hikes. Trails with an unknown length match neither.
    `province`, `park_type` and `park` repeat to match any of their values.
    """
    conditions = filter_conditions(q, terrain, trip, province, park_type, park)
    return db.scalars(
        select(Trail).where(*where(conditions)).order_by(Trail.popularity_rank, Trail.name).limit(limit)
    ).all()


def trail_facets(db: Session, conditions: dict[str, list]) -> TrailFacetsOut:
    """Each option counted under every other filter. Options with no matches
    stay in the lists (count 0) so the page can grey them out."""
    def counts(column, leave_out):
        return dict(db.execute(
            select(column, func.count()).where(*where(conditions, leave_out)).group_by(column)
        ).all())

    province_counts = counts(Trail.province_code, "province")
    provinces = db.scalars(
        select(Trail.province_code).where(*live_trails(), Trail.province_code.is_not(None)).distinct()
    ).all()

    type_counts = counts(PARK_TYPE_BUCKET, "park_type")

    park_counts = counts(Trail.park_name, "park")
    parks: dict[str, ParkFacetOut] = {}
    for name, kind, province in db.execute(
        select(Trail.park_name, Trail.park_type, Trail.province_code)
        .where(*live_trails(), Trail.park_name.is_not(None))
        .distinct()
    ):
        park = parks.setdefault(
            name, ParkFacetOut(name=name, park_type=kind or "none", province_codes=[], count=park_counts.get(name, 0))
        )
        if province and province not in park.province_codes:
            park.province_codes.append(province)

    return TrailFacetsOut(
        provinces=[ProvinceFacetOut(code=code, count=province_counts.get(code, 0)) for code in sorted(provinces)],
        park_types=[ParkTypeFacetOut(type=kind, count=type_counts.get(kind, 0)) for kind in PARK_TYPE_FILTERS],
        parks=sorted(parks.values(), key=lambda p: p.name.casefold()),
    )


@router.post("/search", response_model=TrailSearchOut)
def search_trails_with_facets(body: TrailSearchIn, db: Session = Depends(get_db)):
    """Explore's search: the trails, the total, and the filter counts.

    A POST so `near` travels in the body: request URLs land in access logs,
    and the searcher's position is used for this response only, never stored
    or logged.
    """
    limit = min(body.limit, TRAIL_CATALOG_LIMIT)
    distances = distances_from(db, body.near) if body.near else {}
    within = None
    if body.near and body.near.radius_km is not None:
        within = {trail_id for trail_id, km in distances.items() if km <= body.near.radius_km}
    conditions = filter_conditions(
        body.q.strip(), body.terrain, body.trip, body.provinces, body.park_types, body.parks, within
    )

    total = db.scalar(select(func.count()).select_from(Trail).where(*where(conditions)))
    rows = db.scalars(
        select(Trail).where(*where(conditions)).order_by(Trail.popularity_rank, Trail.name).limit(limit)
    ).all()
    trails = []
    for row in rows:
        item = TrailSearchItemOut.model_validate(row)
        km = distances.get(row.id)
        item.distance_away_km = round(km, 1) if km is not None else None
        trails.append(item)
    return TrailSearchOut(trails=trails, total=total, facets=trail_facets(db, conditions))


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
