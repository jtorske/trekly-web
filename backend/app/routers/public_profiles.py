"""Public profiles: what anyone, signed in or not, can see at /u/{username}.

Every response is built from explicit *Public* models, so a field only
leaves the API if it's declared here: never an email, home region, alert,
gear or plan note, gear photo, party size, booking, or anything from a hidden section.
The answer is the same for every viewer, including the owner (whose page
adds its own controls on the client), so there's nothing a signed-in
visitor can see that a guest can't. Responses are never cached, so a
privacy change applies to the next request.

Direct Supabase access is guarded separately by row-level security with
the same rule (app/privacy.py, migration 214aa07bf743).
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import CurrentUser, get_current_user
from app.catalog.presenters import effective_weight, gear_item_out
from app.database import get_db
from app.featured import FeaturedBadgeOut, featured_badges
from app.models.account import Profile, SavedTrail
from app.models.hike_log import HikeLog
from app.models.privacy import MAX_REPORT_DETAILS, ProfileReport
from app.models.setup import GearSetup
from app.models.trip_plan import TripPlan
from app.models.user_gear import UserGearItem
from app.notify import Email, EmailSender, email_sender_from_env
from app.points import user_rank
from app.privacy import Visibility, visibility
from app.routers.me_gear import _item_query
from app.schemas.gear import CapacityOut, CategoryRef, ProductSummaryOut, VariantOut, WeightOut
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/profiles", tags=["public profiles"])

REPORTS_TO = os.getenv("PROFILE_REPORTS_EMAIL", "treklyusersupport@gmail.com")
REPORTS_PER_DAY = 5
REPORT_REASONS = ("spam", "harassment", "inappropriate", "impersonation", "privacy", "other")
NO_STORE = {"Cache-Control": "no-store"}


class PublicRank(BaseModel):
    level: int
    title: str


class PublicJournalEntry(BaseModel):
    trail: TrailListItemOut
    # None when the owner hides dates.
    hiked_on: date | None
    note: str | None
    photo_path: str | None


class PublicJournal(BaseModel):
    hide_dates: bool
    entries: list[PublicJournalEntry]


class PublicGearItem(BaseModel):
    id: UUID
    kind: Literal["catalog", "custom"]
    display_name: str
    brand_name: str | None
    category: CategoryRef
    product: ProductSummaryOut | None
    variant: VariantOut | None
    custom_brand: str | None
    custom_model: str | None
    quantity: int
    weight: WeightOut
    capacity: CapacityOut
    # No image_path: the owner's own gear photos are never shown to others
    # (migration 6e2f4b8d1a37); visitors see the catalogue photo or icon.


class PublicSetup(BaseModel):
    id: UUID
    name: str
    description: str | None
    items: list[PublicGearItem]
    item_count: int
    known_weight_g: float
    items_missing_weight: int


class PublicGear(BaseModel):
    items: list[PublicGearItem]
    setups: list[PublicSetup]


class PublicTripPlan(BaseModel):
    id: UUID
    trail: TrailListItemOut
    title: str | None
    start_date: date
    nights: int


class PublicProfileOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    is_private: bool
    allow_indexing: bool
    # Everything below is None when private, or when that section is hidden.
    bio: str | None = None
    rank: PublicRank | None = None
    journal: PublicJournal | None = None
    # Shown with the Trail Journal: same switch, and no dates either way.
    featured_badges: list[FeaturedBadgeOut] | None = None
    gear: PublicGear | None = None
    saved_trails: list[TrailListItemOut] | None = None
    trip_plans: list[PublicTripPlan] | None = None


def find_listed(db: Session, username: str) -> tuple[Profile, Visibility]:
    """The profile behind a username, or 404 if there's none or it's hidden."""
    profile = db.scalar(select(Profile).where(Profile.username == username.strip().lower()))
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    seen = visibility(db, profile)
    if not seen.listed:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile, seen


def _journal(db: Session, owner: UUID, hide_dates: bool) -> PublicJournal:
    logs = db.scalars(
        select(HikeLog).where(HikeLog.user_id == owner).options(joinedload(HikeLog.trail))
    ).all()
    # Without dates, even the order would hint at when; go by trail name.
    if hide_dates:
        logs = sorted(logs, key=lambda log: log.trail.name.lower())
    else:
        logs = sorted(logs, key=lambda log: (log.hiked_on, log.created_at), reverse=True)
    return PublicJournal(
        hide_dates=hide_dates,
        entries=[
            PublicJournalEntry(
                trail=TrailListItemOut.model_validate(log.trail),
                hiked_on=None if hide_dates else log.hiked_on,
                note=log.note,
                photo_path=log.photo_path,
            )
            for log in logs
        ],
    )


def _public_item(item: UserGearItem) -> PublicGearItem:
    # Validating from the full owner view keeps only the declared fields.
    return PublicGearItem.model_validate(gear_item_out(item).model_dump())


def _gear(db: Session, owner: UUID) -> PublicGear:
    items = db.scalars(_item_query(owner).order_by(UserGearItem.created_at)).unique().all()
    by_id = {item.id: item for item in items}
    setups = []
    for setup in db.scalars(
        select(GearSetup)
        .where(GearSetup.user_id == owner)
        .options(selectinload(GearSetup.entries))
        .order_by(GearSetup.created_at)
    ):
        # Only the owner's own items, in the setup's order.
        members = [by_id[e.gear_item_id] for e in setup.entries if e.gear_item_id in by_id]
        known, missing = Decimal(0), 0
        for item in members:
            grams, _ = effective_weight(item)
            if grams is None:
                missing += 1
            else:
                known += grams * item.quantity
        setups.append(
            PublicSetup(
                id=setup.id,
                name=setup.name,
                description=setup.description,
                items=[_public_item(item) for item in members],
                item_count=len(members),
                known_weight_g=float(known),
                items_missing_weight=missing,
            )
        )
    return PublicGear(items=[_public_item(item) for item in items], setups=setups)


def _saved_trails(db: Session, owner: UUID) -> list[TrailListItemOut]:
    rows = db.scalars(
        select(SavedTrail)
        .where(SavedTrail.user_id == owner)
        .options(joinedload(SavedTrail.trail))
        .order_by(SavedTrail.created_at.desc())
    ).all()
    return [TrailListItemOut.model_validate(row.trail) for row in rows]


def _trip_plans(db: Session, owner: UUID) -> list[PublicTripPlan]:
    plans = db.scalars(
        select(TripPlan)
        .where(TripPlan.user_id == owner)
        .options(joinedload(TripPlan.trail))
        .order_by(TripPlan.start_date, TripPlan.created_at)
    ).all()
    return [
        PublicTripPlan(
            id=plan.id,
            trail=TrailListItemOut.model_validate(plan.trail),
            title=plan.title,
            start_date=plan.start_date,
            nights=plan.nights,
        )
        for plan in plans
    ]


def build_public_profile(db: Session, profile: Profile, seen: Visibility) -> PublicProfileOut:
    out = PublicProfileOut(
        username=profile.username,
        display_name=profile.display_name,
        avatar_path=profile.avatar_path,
        is_private=not seen.public,
        allow_indexing=seen.indexable,
    )
    if not seen.public:
        return out
    out.bio = profile.bio
    if seen.shows("rank"):
        # The name and level only: points are the owner's business (app/routers/me_rank.py).
        _, rank = user_rank(db, profile.id)
        out.rank = PublicRank(level=rank.level, title=rank.title)
    if seen.shows("journal"):
        out.journal = _journal(db, profile.id, seen.hide_dates)
        _, out.featured_badges = featured_badges(db, profile.id, hide_dates=seen.hide_dates)
    if seen.shows("gear"):
        out.gear = _gear(db, profile.id)
    if seen.shows("saved_trails"):
        out.saved_trails = _saved_trails(db, profile.id)
    if seen.shows("trip_plans"):
        out.trip_plans = _trip_plans(db, profile.id)
    return out


@router.get("/{username}", response_model=PublicProfileOut)
def get_public_profile(username: str, response: Response, db: Session = Depends(get_db)):
    response.headers.update(NO_STORE)
    profile, seen = find_listed(db, username)
    return build_public_profile(db, profile, seen)


# ----------------------------------------------------------------- reports


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    details: str | None = Field(default=None, max_length=MAX_REPORT_DETAILS)

    @field_validator("details", mode="before")
    @classmethod
    def _clean(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


def get_email_sender() -> EmailSender:
    """Overridden in tests."""
    return email_sender_from_env()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def report_email(profile: Profile, reporter: CurrentUser, reporter_profile: Profile | None, payload: ReportIn) -> Email:
    app_url = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    reporter_name = (reporter_profile.username if reporter_profile else None) or "(no username)"
    text = "\n".join(
        [
            "A profile was reported on Trekly.",
            "",
            f"Profile: @{profile.username} ({app_url}/u/{profile.username})",
            f"Profile user id: {profile.id}",
            f"Reason: {payload.reason}",
            f"Details: {payload.details or '(none)'}",
            "",
            # The reporter's account, not their email address (see the Privacy Policy).
            f"Reported by: @{reporter_name}, user id {reporter.id}",
            "",
            "To hide the profile, use /admin/profiles on the site.",
        ]
    )
    return Email(to=REPORTS_TO, subject=f"Profile report: @{profile.username} ({payload.reason})", text=text)


@router.post("/{username}/report", status_code=status.HTTP_202_ACCEPTED)
def report_profile(
    username: str,
    payload: ReportIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    """Email support about a profile. Signed-in users only, and rate-limited:
    REPORTS_PER_DAY reports a day, and one per profile a day."""
    profile, _ = find_listed(db, username)
    if profile.id == user.id:
        raise HTTPException(status_code=422, detail="You can't report your own profile.")
    since = _now() - timedelta(days=1)
    recent = db.scalars(
        select(ProfileReport.profile_id).where(
            ProfileReport.reporter_id == user.id, ProfileReport.created_at >= since
        )
    ).all()
    if profile.id in recent:
        raise HTTPException(status_code=429, detail="You've already reported this profile. We'll take a look.")
    if len(recent) >= REPORTS_PER_DAY:
        raise HTTPException(status_code=429, detail="You've sent several reports today. Try again tomorrow.")

    db.add(ProfileReport(reporter_id=user.id, profile_id=profile.id, reason=payload.reason,
                         details=payload.details, created_at=_now()))
    db.flush()
    try:
        sender.send(report_email(profile, user, db.get(Profile, user.id), payload))
    except Exception as error:
        db.rollback()  # not sent, so it doesn't count against the limit
        raise HTTPException(
            status_code=503, detail="We couldn't send your report. Try again in a moment."
        ) from error
    db.commit()
    return {"status": "sent"}
