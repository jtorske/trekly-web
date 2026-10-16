from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

Terrain = Literal["easy", "moderate", "difficult", "extreme"]
Season = Literal["spring", "summer", "fall", "winter"]


class TrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    region: str
    terrain: Terrain = Field(
        validation_alias=AliasChoices("terrain_difficulty", "terrain")
    )


class TrailListItemOut(TrailOut):
    country_code: str
    province_code: str | None = None
    typical_duration_nights: int | None = None
    route_type: Literal["out_and_back", "loop", "point_to_point"] | None = None
    # Round trip for out-and-backs, the loop, or the full one-way length.
    distance_km: float | None = None
    elevation_gain_m: int | None = None
    popularity_rank: int | None = None
    # Set when the trail has left the catalogue; it still resolves for
    # bookmarks but no longer appears in search.
    retired_at: datetime | None = None


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
