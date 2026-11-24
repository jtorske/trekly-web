import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.catalog import JsonType
import app.trail_slugs  # noqa: F401  (assigns slugs to new trails on flush)

TERRAIN_DIFFICULTIES = ("easy", "moderate", "difficult", "extreme")
DOG_POLICIES = ("on_leash", "not_allowed", "unknown")
PARK_TYPES = ("national", "provincial", "regional", "none")


class Trail(Base):
    __tablename__ = "trails"
    __table_args__ = (
        CheckConstraint(
            "terrain_difficulty in ('easy','moderate','difficult','extreme')",
            name="trails_terrain_difficulty_check",
        ),
        CheckConstraint("length(country_code) = 2", name="trails_country_code_check"),
        CheckConstraint("popularity_rank >= 1", name="trails_popularity_rank_check"),
        CheckConstraint(
            "(distance_km is null and route_type is null) or "
            "(distance_km > 0 and route_type in ('out_and_back','loop','point_to_point'))",
            name="trails_distance_check",
        ),
        CheckConstraint(
            "park_type in ('national','provincial','regional','none')",
            name="trails_park_type_check",
        ),
        CheckConstraint(
            "avalanche_exposure in ('none','simple','challenging','complex','unknown')",
            name="trails_avalanche_exposure_check",
        ),
        # A rating, 'none' included, needs the official source it came from.
        CheckConstraint(
            "avalanche_exposure = 'unknown' or avalanche_source_url is not null",
            name="trails_avalanche_source_check",
        ),
        CheckConstraint(
            "dog_policy in ('on_leash','not_allowed','unknown')", name="trails_dog_policy_check",
        ),
        # Like avalanche ratings: a dog rule needs the official page it came from.
        CheckConstraint(
            "dog_policy = 'unknown' or dog_policy_source_url is not null",
            name="trails_dog_policy_source_check",
        ),
        UniqueConstraint("name", "province_code", name="trails_name_province_key"),
        UniqueConstraint("slug", name="trails_slug_key"),
        Index("trails_country_rank_idx", "country_code", "popularity_rank"),
        Index("trails_province_code_idx", "province_code"),
        Index("trails_park_type_idx", "park_type"),
        Index("trails_park_name_idx", "park_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    # The trail page's URL, /trails/{slug}: set once on insert and never
    # changed (app/trail_slugs.py), so links keep working.
    slug = Column(Text, nullable=False)
    region = Column(Text, nullable=False)
    # ISO 3166-1 alpha-2 country and the ISO 3166-2 subdivision suffix
    # (e.g. "CA" / "AB").
    country_code = Column(Text, nullable=False)
    province_code = Column(Text)
    # The park the trail is in, from the catalogue. park_type is national
    # (Parks Canada), provincial (provincial and territorial parks, Quebec's
    # parcs nationaux, Kananaskis Country), regional (regional or municipal)
    # or none. A named place that isn't a park keeps its name with type none.
    # Both null for retired trails that were never classified.
    park_name = Column(Text)
    park_type = Column(Text)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    elevation_gain_m = Column(Integer)
    max_elevation_m = Column(Integer)
    # out_and_back, loop or point_to_point. distance_km is what a hiker
    # covers: the round trip, the loop, or the full one-way length.
    route_type = Column(Text)
    distance_km = Column(Numeric(5, 1))
    terrain_difficulty = Column(Text, nullable=False)
    typical_duration_nights = Column(Integer)
    climate_zone = Column(Text)
    # Free-form labels from the catalogue, e.g. "larch" for trails known for
    # their autumn larches (the Larch madness milestone).
    tags = Column(JsonType, nullable=False, default=list, server_default="[]")
    description = Column(Text)
    # Winter use, from catalog_data/trail_winter.json (app/trail_winter.py).
    # winter_activities: any of winter_hike, snowshoe, xc_ski; empty means
    # not recommended in winter. avalanche_exposure is the Avalanche Terrain
    # Exposure Scale class from an official rating (its URL in
    # avalanche_source_url); without one it stays 'unknown', never 'none'.
    winter_activities = Column(JsonType, nullable=False, default=list, server_default="[]")
    avalanche_exposure = Column(Text, nullable=False, default="unknown", server_default="unknown")
    avalanche_source_url = Column(Text)
    winter_access_note = Column(Text)
    winter_notes = Column(Text)
    # Set when only part of the trail is a winter route: where it ends. The
    # summer distance and gain then don't describe the winter outing.
    winter_route_ends = Column(Text)
    winter_source_url = Column(Text)
    # The official grooming / trail conditions report to check before going.
    winter_report_url = Column(Text)
    # Dogs, from catalog_data/trail_dogs.json (app/trail_dogs.py): on_leash
    # (allowed on a leash), not_allowed, or unknown when no official source
    # says. Trekly Guide's dog filter keeps on_leash trails only.
    dog_policy = Column(Text, nullable=False, default="unknown", server_default="unknown")
    dog_policy_source_url = Column(Text)
    dog_policy_note = Column(Text)
    # Catalogue ordering. popularity_source says where the score came from
    # ('editorial' today; a blend with saved_trails counts later), so ranks can
    # be recomputed without another schema change. Null for retired trails.
    popularity_rank = Column(Integer)
    popularity_score = Column(Numeric(6, 4))
    popularity_source = Column(Text)
    popularity_updated_at = Column(DateTime(timezone=True))
    # Set when a trail drops out of the catalogue. Retired trails are never
    # deleted, so bookmarks, seasonal conditions and campsites keep working.
    retired_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # The credited hero photo, if one has been approved (null means the topo
    # fallback). Loaded with each trail so lists don't query per row.
    photo = relationship("TrailPhoto", uselist=False, lazy="selectin", viewonly=True)
    # The generated route map, shown instead of the plain topo when there's no photo.
    route_map = relationship("TrailRouteMap", uselist=False, lazy="selectin", viewonly=True)
