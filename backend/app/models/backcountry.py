"""Backcountry campground / zone catalogue synced from reservation providers.

Rows are shared reference data written only by the sync
(app/backcountry/sync.py, run via scripts/sync_backcountry.py). Every row keeps
the provider's own IDs next to our UUID, so a later provider (BC Parks,
Alberta Parks, Ontario Parks) is just another `provider` value, and a later
trail_campgrounds(trail_id, site_id) link table only needs a FK to
backcountry_sites.id.

Sites that disappear from the provider are retired (retired_at), never
deleted, so anything linked to them keeps working.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.catalog import JsonType, _timestamps

SITE_KINDS = (
    "zone",  # quota-based backcountry campground (Banff "Br17", Jasper "70 - Blue Creek")
    "site",  # individually booked tent pad (Bruce "HD1", Pukaskwa "BC2")
    "shelter",
    "cabin",
    "yurt",
    "random_zone",  # random / wildland camping area
    "horse_camp",  # horse grazing campsite
    "backpacking_campground",  # trip-style booking per campground (Chilkoot)
    "trail_permit",  # trail entry quota rather than a campground (West Coast Trail, Long Range)
    "other",  # backcountry category the sync doesn't recognise yet (flagged in the report)
)


class BackcountryPark(Base):
    __tablename__ = "backcountry_parks"
    __table_args__ = (
        UniqueConstraint("provider", "provider_park_id", name="backcountry_parks_provider_park_key"),
        CheckConstraint(
            "province_code is null or length(province_code) = 2",
            name="backcountry_parks_province_code_check",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    provider = Column(Text, nullable=False)
    # Parks Canada: the park's map id in the organisation map tree.
    provider_park_id = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    province_code = Column(Text)
    # Provider's own grouping, e.g. Parks Canada "Western" / "Central" / "Eastern".
    region = Column(Text)
    last_synced_at = Column(DateTime(timezone=True), nullable=False)
    retired_at = Column(DateTime(timezone=True))
    created_at, updated_at = _timestamps()


class BackcountrySite(Base):
    __tablename__ = "backcountry_sites"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_resource_id", name="backcountry_sites_provider_resource_key"
        ),
        CheckConstraint(
            "kind in (" + ",".join(f"'{k}'" for k in SITE_KINDS) + ")",
            name="backcountry_sites_kind_check",
        ),
        CheckConstraint(
            "province_code is null or length(province_code) = 2",
            name="backcountry_sites_province_code_check",
        ),
        CheckConstraint(
            "latitude is null or (latitude between -90 and 90)",
            name="backcountry_sites_latitude_check",
        ),
        CheckConstraint(
            "longitude is null or (longitude between -180 and 180)",
            name="backcountry_sites_longitude_check",
        ),
        Index("backcountry_sites_park_idx", "park_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    provider = Column(Text, nullable=False)
    # Raw provider IDs, kept verbatim (Parks Canada's are negative int32s).
    provider_resource_id = Column(Text, nullable=False)
    provider_location_id = Column(Text, nullable=False)
    provider_map_id = Column(Text)
    provider_category_id = Column(Text)
    provider_booking_category_id = Column(Text)
    resource_model = Column(Integer)
    # NULL when the provider gives no way to tell which park a site is in
    # (reported by the sync rather than guessed).
    park_id = Column(Uuid, ForeignKey("backcountry_parks.id", ondelete="RESTRICT"))
    province_code = Column(Text)
    # The provider's bookable location, e.g. "Banff, Kootenay and Yoho - Backcountry".
    booking_unit = Column(Text, nullable=False)
    # Backcountry area within the park, e.g. "Tonquin Valley"; NULL when the
    # provider has no sub-area for the site.
    area = Column(Text)
    name = Column(Text, nullable=False)
    raw_name = Column(Text, nullable=False)
    site_code = Column(Text)
    kind = Column(Text, nullable=False)
    # Quota of parties/tents the zone takes per night (zone bookings only).
    reservable_capacity = Column(Integer)
    # Provider's per-booking maximum (Parks Canada maxCapacity).
    max_capacity = Column(Integer)
    max_group_size = Column(Integer)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    # False for resources the provider doesn't show on any published map
    # (staff / last-minute pseudo-zones, registration-only zones). Hidden from
    # clients by default.
    is_publicly_listed = Column(Boolean, nullable=False, default=True)
    description = Column(Text)
    raw = Column(JsonType, nullable=False, default=dict)
    last_synced_at = Column(DateTime(timezone=True), nullable=False)
    retired_at = Column(DateTime(timezone=True))
    created_at, updated_at = _timestamps()

    park = relationship("BackcountryPark")
