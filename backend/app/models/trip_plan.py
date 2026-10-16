"""Trip plans: a signed-in user's night-by-night plan for one trail.

Dates are plain calendar dates (no time or time zone): night N of a plan is
start_date + N, the same night for every user wherever they are.

Each night's status is worked out when it is read: "booked by me" (the flag
the user sets) wins, then an active alert covering that night, then the last
availability check of that night, then "not checked". Only the user's flag
and the last check's answer (with when it ran, so the UI can say how stale it
is) are stored.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.availability import MAX_ALERT_NIGHTS, MAX_PARTY_SIZE
from app.models.catalog import _timestamps

MAX_PLAN_NIGHTS = MAX_ALERT_NIGHTS
MAX_PLANS_PER_USER = 50
NIGHT_CHOICES = ("campground", "undecided", "outside")
CHECK_STATUSES = ("available", "full", "closed", "not_released", "unknown")


class TripPlan(Base):
    __tablename__ = "trip_plans"
    __table_args__ = (
        CheckConstraint(f"nights between 1 and {MAX_PLAN_NIGHTS}", name="trip_plans_nights_check"),
        CheckConstraint(f"party_size between 1 and {MAX_PARTY_SIZE}", name="trip_plans_party_check"),
        CheckConstraint("title is null or length(title) <= 80", name="trip_plans_title_length_check"),
        CheckConstraint("notes is null or length(notes) <= 2000", name="trip_plans_notes_length_check"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False, index=True)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="RESTRICT"), nullable=False)
    # Deleting a setup keeps the plan; it just has no gear attached.
    setup_id = Column(Uuid, ForeignKey("gear_setups.id", ondelete="SET NULL"))
    title = Column(Text)
    start_date = Column(Date, nullable=False)
    nights = Column(Integer, nullable=False)
    party_size = Column(Integer, nullable=False)
    notes = Column(Text)
    created_at, updated_at = _timestamps()

    trail = relationship("Trail")
    setup = relationship("GearSetup")
    plan_nights = relationship(
        "TripPlanNight",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="TripPlanNight.night_index",
    )


class TripPlanNight(Base):
    __tablename__ = "trip_plan_nights"
    __table_args__ = (
        CheckConstraint(f"night_index between 0 and {MAX_PLAN_NIGHTS - 1}", name="trip_plan_nights_index_check"),
        CheckConstraint(
            "choice in (" + ",".join(f"'{c}'" for c in NIGHT_CHOICES) + ")",
            name="trip_plan_nights_choice_check",
        ),
        # A campground night names its site; the other choices never do.
        CheckConstraint(
            "(choice = 'campground') = (site_id is not null)", name="trip_plan_nights_site_check"
        ),
        CheckConstraint(
            "last_status is null or last_status in (" + ",".join(f"'{s}'" for s in CHECK_STATUSES) + ")",
            name="trip_plan_nights_last_status_check",
        ),
    )

    trip_plan_id = Column(Uuid, ForeignKey("trip_plans.id", ondelete="CASCADE"), primary_key=True)
    night_index = Column(Integer, primary_key=True)
    # campground: a site on this trail. undecided: not chosen yet.
    # outside: camping somewhere Parks Canada doesn't book.
    choice = Column(Text, nullable=False, default="undecided")
    site_id = Column(Uuid, ForeignKey("backcountry_sites.id", ondelete="RESTRICT"), index=True)
    booked_by_me = Column(Boolean, nullable=False, default=False)
    # The last availability check of this night at this site; cleared when the
    # site or the date changes.
    last_status = Column(Text)
    last_checked_at = Column(DateTime(timezone=True))

    plan = relationship("TripPlan", back_populates="plan_nights")
    site = relationship("BackcountrySite")
