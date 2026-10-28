from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.trail_photos import public_photo_url

Terrain = Literal["easy", "moderate", "difficult", "extreme"]
Season = Literal["spring", "summer", "fall", "winter"]
ParkType = Literal["national", "provincial", "regional", "none"]
# Explore's park-type filter: "other" is regional parks and trails in no park.
ParkTypeFilter = Literal["national", "provincial", "other"]
TripType = Literal["overnight", "day"]


class TrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    region: str
    terrain: Terrain = Field(
        validation_alias=AliasChoices("terrain_difficulty", "terrain")
    )


class TrailPhotoOut(BaseModel):
    """What the page needs to show a trail photo and its credit line."""

    hero_url: str
    thumb_url: str
    width: int
    height: int
    photographer: str
    # Null for the site owner's own photos, credited by name only.
    license: str | None = None
    license_url: str | None = None
    source_url: str | None = None
    # Where it was first published ("Flickr", "Wikimedia Commons"); null for the owner's photos.
    origin: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, value):
        if hasattr(value, "hero_path"):
            return {
                "hero_url": public_photo_url(value.hero_path),
                "thumb_url": public_photo_url(value.thumb_path),
                "width": value.hero_width,
                "height": value.hero_height,
                "photographer": value.photographer,
                "license": value.license,
                "license_url": value.license_url,
                "source_url": value.source_url,
                "origin": value.origin,
            }
        return value


class TrailListItemOut(TrailOut):
    country_code: str
    province_code: str | None = None
    park_name: str | None = None
    park_type: ParkType | None = None
    typical_duration_nights: int | None = None
    route_type: Literal["out_and_back", "loop", "point_to_point"] | None = None
    # Round trip for out-and-backs, the loop, or the full one-way length.
    distance_km: float | None = None
    elevation_gain_m: int | None = None
    popularity_rank: int | None = None
    # Set when the trail has left the catalogue; it still resolves for
    # bookmarks but no longer appears in search.
    retired_at: datetime | None = None
    # The approved hero photo; null means show the topo fallback.
    photo: TrailPhotoOut | None = None


class NearIn(BaseModel):
    """The searcher's position, used for this request only and never stored."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    # Null ranks by distance without cutting anything off.
    radius_km: float | None = Field(default=None, gt=0, le=1000)


class TrailSearchIn(BaseModel):
    q: str = ""
    terrain: Terrain | None = None
    trip: TripType | None = None
    # Each list matches any of its values; the lists combine with AND.
    provinces: list[str] = Field(default=[], max_length=20)
    park_types: list[ParkTypeFilter] = Field(default=[], max_length=3)
    parks: list[str] = Field(default=[], max_length=50)
    near: NearIn | None = None
    limit: int = Field(default=10, ge=1)


class TrailSearchItemOut(TrailListItemOut):
    # Straight-line km from `near`; null without it or without coordinates.
    distance_away_km: float | None = None


class ProvinceFacetOut(BaseModel):
    code: str
    count: int


class ParkTypeFacetOut(BaseModel):
    type: ParkTypeFilter
    count: int


class ParkFacetOut(BaseModel):
    name: str
    park_type: ParkType
    province_codes: list[str]
    count: int


class TrailFacetsOut(BaseModel):
    """Every option, each counted under all the other active filters (its own
    dimension left out), so a count says what picking that option adds."""

    provinces: list[ProvinceFacetOut]
    park_types: list[ParkTypeFacetOut]
    parks: list[ParkFacetOut]


class TrailSearchOut(BaseModel):
    trails: list[TrailSearchItemOut]
    # All matches, before `limit`.
    total: int
    facets: TrailFacetsOut


class SeasonalConditionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    season: Season
    avg_low_c: float
    avg_high_c: float
    precip_likelihood: Literal["low", "moderate", "high"] | None = None
    high_wind: bool | None = None
    notes: str | None = None


class TrailDetailOut(TrailListItemOut):
    max_elevation_m: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    climate_zone: str | None = None
    description: str | None = None
    seasonal_conditions: list[SeasonalConditionOut] = []


class CampgroundParkOut(BaseModel):
    name: str
    province_code: str | None = None


class TrailCampgroundOut(BaseModel):
    site_id: UUID
    route_order: int
    # Groups individually booked pads at one place ("Fish Harbour").
    stop_name: str | None = None
    notes: str | None = None
    confidence: Literal["exact", "likely"]
    # The provider no longer lists the site; the link is kept so the route
    # still reads correctly.
    retired: bool
    name: str
    site_code: str | None = None
    kind: str
    area: str | None = None
    park: CampgroundParkOut | None = None
    reservable_capacity: int | None = None
    max_capacity: int | None = None
    max_group_size: int | None = None
    provider: str


class TrailBookingOut(BaseModel):
    system: str
    # Null until the system is confirmed: the UI then says "Booked outside Trekly".
    name: str | None = None
    url: str | None = None
    covers: Literal["all", "partial"]
    confirmed: bool
    note: str | None = None


class TrailBookingLinkOut(BaseModel):
    """A provider booking form preset to a park and booking type. Parks Canada
    builds backcountry trips as an itinerary inside that form, so there is no
    link to an individual campground."""

    label: str
    url: str


class TrailCampgroundsOut(BaseModel):
    trail_id: UUID
    trip_type: Literal["overnight", "day"]
    # A day hike that has campgrounds on it ("Also doable as an overnight").
    overnight_option: bool
    # Some stops' order or placement is curated rather than confirmed.
    route_order_approximate: bool
    booking: list[TrailBookingOut]
    booking_links: list[TrailBookingLinkOut]
    campgrounds: list[TrailCampgroundOut]
