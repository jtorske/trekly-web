"""Trail ↔ backcountry campground links, and how each trail's camping is booked.

Both tables are shared reference data written only by the seed
(app/trail_campgrounds.py, from catalog_data/trail_campgrounds.json): the
backcountry catalogue has no coordinates, so links are curated by hand.

A link keeps pointing at its site after the provider retires it (sites are
never deleted), so the trail page can show it as no longer listed instead of
silently dropping a stop.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.catalog import _timestamps

LINK_CONFIDENCES = ("exact", "likely")
BOOKING_COVERAGE = ("all", "partial")


class TrailCampground(Base):
    __tablename__ = "trail_campgrounds"
    __table_args__ = (
        CheckConstraint("route_order >= 1", name="trail_campgrounds_route_order_check"),
        CheckConstraint(
            "confidence in (" + ",".join(f"'{c}'" for c in LINK_CONFIDENCES) + ")",
            name="trail_campgrounds_confidence_check",
        ),
        Index("trail_campgrounds_site_idx", "site_id"),
    )

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    site_id = Column(Uuid, ForeignKey("backcountry_sites.id", ondelete="RESTRICT"), primary_key=True)
    # Position along the route in the mapping's stated direction. Not unique:
    # individually booked pads at one place share an order (and a stop_name).
    route_order = Column(Integer, nullable=False)
    stop_name = Column(Text)
    notes = Column(Text)
    # 'exact': the provider's own data ties the site to the route;
    # 'likely': curated from route knowledge, still to be verified.
    confidence = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    created_at, updated_at = _timestamps()

    site = relationship("BackcountrySite")


class TrailBookingSystem(Base):
    __tablename__ = "trail_booking_systems"
    __table_args__ = (
        CheckConstraint(
            "covers in (" + ",".join(f"'{c}'" for c in BOOKING_COVERAGE) + ")",
            name="trail_booking_systems_covers_check",
        ),
    )

    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), primary_key=True)
    # Slug from the mapping file's booking_systems ('parks_canada', 'bc_parks', ...).
    # Display names and URLs live in the mapping file, not here.
    system = Column(Text, primary_key=True)
    # 'all' when this system books every night on the route, 'partial' when
    # the route spans systems (e.g. Banff + BC Parks for Mount Assiniboine).
    covers = Column(Text, nullable=False)
    # False until we've verified the system; the UI then says "Booked
    # outside Trekly" rather than naming it.
    confirmed = Column(Boolean, nullable=False, default=True)
    note = Column(Text)
    position = Column(Integer, nullable=False, default=0)
    created_at, updated_at = _timestamps()
