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
