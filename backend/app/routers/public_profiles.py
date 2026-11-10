"""Public profiles: what anyone, signed in or not, can see at /u/{username}.

Every response is built from explicit *Public* models, so a field only
leaves the API if it's declared here: never an email, home region, alert,
home province (unless its switch is on),
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
from app.milestones import MilestoneBadgeOut, badge_out, evaluate, gather
from app.activity import is_visible
from app.models.account import Profile, SavedTrail
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.models.privacy import MAX_REPORT_DETAILS, ProfileReport
from app.models.setup import GearSetup
from app.models.trip_plan import TripPlan
from app.models.user_gear import UserGearItem
from app.models.visit_streak import VisitStreak
from app.notify import Email, EmailSender, email_sender_from_env
from app.points import user_rank
from app.privacy import Visibility, visibility
from app.routers.activity import profile_activity_count
from app.routers.availability import get_today
from app.routers.me_gear import _item_query
from app.schemas.gear import CapacityOut, CategoryRef, ProductSummaryOut, VariantOut, WeightOut
from app.schemas.trail import TrailListItemOut
from app.streaks import Streak, current_on, earliest_today

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
    # None when the owner hides dates, or for a hike from before they joined.
    hiked_on: date | None
    note: str | None
    photo_path: str | None
    # Matched against a GPS track.
    verified: bool


class PublicJournal(BaseModel):
    hide_dates: bool
    entries: list[PublicJournalEntry]
    # Earned milestones only, in journal order. Seasonal ones would hint at
    # when, so they're left out while dates are hidden.
    milestones: list[MilestoneBadgeOut] = []


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


class PublicStreak(BaseModel):
    # 0 once it has lapsed in every time zone (the owner's isn't known).
    current: int
    longest: int


def _visit_streak(db: Session, user_id: UUID) -> PublicStreak:
    row = db.get(VisitStreak, user_id)
    if row is None:
        return PublicStreak(current=0, longest=0)
    streak = Streak(row.current_streak, row.longest_streak, row.last_visit_date)
    return PublicStreak(current=current_on(streak, earliest_today(datetime.now(timezone.utc))), longest=streak.longest)


class PublicProfileOut(BaseModel):
    username: str
    display_name: str | None
    avatar_path: str | None
    is_private: bool
    allow_indexing: bool
    # Everything below is None when private, or when that section is hidden.
    bio: str | None = None
    # Two-letter code; only with "Home province" switched on (off by default).
    home_province: str | None = None
    rank: PublicRank | None = None
    # Only with "Visit streak" switched on (off by default).
    visit_streak: PublicStreak | None = None
    journal: PublicJournal | None = None
    # Shown with the Trail Journal: same switch, and no dates either way.
    featured_badges: list[FeaturedBadgeOut] | None = None
    gear: PublicGear | None = None
    saved_trails: list[TrailListItemOut] | None = None
    trip_plans: list[PublicTripPlan] | None = None
    # How many Activity posts visitors can see; None when there's no Activity
    # tab (private, or "Share my activity in the feed" off).
    activity_count: int | None = None


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
        # Newest first; undated hikes (from before they joined) after every dated one.
        logs = sorted(
            logs, key=lambda log: (log.hiked_on is not None, log.hiked_on or date.min, log.created_at), reverse=True
        )
    earned = [
        badge_out(milestone)
        for milestone, result in evaluate(gather(db, owner))
        if result.earned and not (hide_dates and milestone.category == "seasons")
    ]
    return PublicJournal(
        hide_dates=hide_dates,
        milestones=earned,
        entries=[
            PublicJournalEntry(
                trail=TrailListItemOut.model_validate(log.trail),
                hiked_on=None if hide_dates else log.hiked_on,
                note=log.note,
                photo_path=log.photo_path,
                verified=bool(log.verified),
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


def build_public_profile(db: Session, profile: Profile, seen: Visibility, today: date) -> PublicProfileOut:
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
    province = profile.home_province if seen.shows("home_province") else None
    out.home_province = province
    if seen.shows("rank"):
        # The name and level only: points are the owner's business (app/routers/me_rank.py).
        _, rank = user_rank(db, profile.id)
        out.rank = PublicRank(level=rank.level, title=rank.title)
    if seen.shows("visit_streak"):
        out.visit_streak = _visit_streak(db, profile.id)
    if seen.shows("journal"):
        out.journal = _journal(db, profile.id, seen.hide_dates)
        _, out.featured_badges = featured_badges(db, profile.id, hide_dates=seen.hide_dates, province=province)
    if seen.shows("gear"):
        out.gear = _gear(db, profile.id)
    if seen.shows("saved_trails"):
        out.saved_trails = _saved_trails(db, profile.id)
    if seen.shows("trip_plans"):
        out.trip_plans = _trip_plans(db, profile.id)
    out.activity_count = profile_activity_count(db, profile, seen, today)
    return out


@router.get("/{username}", response_model=PublicProfileOut)
def get_public_profile(
    username: str, response: Response, db: Session = Depends(get_db), today: date = Depends(get_today)
):
    response.headers.update(NO_STORE)
    profile, seen = find_listed(db, username)
    return build_public_profile(db, profile, seen, today)


# ----------------------------------------------------------------- reports


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal[REPORT_REASONS]  # type: ignore[valid-type]
    details: str | None = Field(default=None, max_length=MAX_REPORT_DETAILS)
    # Set when reporting their trip note on this trail's "Hiked by" section.
    trail_id: UUID | None = None
    # Set when reporting one of their posts on the Activity page.
    post_id: UUID | None = None

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


def report_email(
    profile: Profile,
    reporter: CurrentUser,
    reporter_profile: Profile | None,
    payload: ReportIn,
    trip_note: HikeLog | None = None,
    post: ActivityPost | None = None,
) -> Email:
    app_url = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
    reporter_name = (reporter_profile.username if reporter_profile else None) or "(no username)"
    note_lines = (
        [
            f"Trip note on: {trip_note.trail.name} ({app_url}/trails?id={trip_note.trail_id})",
            f"Note: {trip_note.note}",
        ]
        if trip_note
        else []
    )
    if post is not None:
        hike = post.hike_log if post.kind == "hike" else None
        note_lines = [
            f"Activity post: {post.kind} post {post.id}",
            *([f"Trail: {hike.trail.name}", f"Note: {hike.note or '(none)'}"] if hike else []),
        ]
    subject = "An Activity post" if post else "A trip note" if trip_note else "A profile"
    text = "\n".join(
        [
            f"{subject} was reported on Trekly.",
            "",
            f"Profile: @{profile.username} ({app_url}/u/{profile.username})",
            f"Profile user id: {profile.id}",
            *note_lines,
            f"Reason: {payload.reason}",
            f"Details: {payload.details or '(none)'}",
            "",
            # The reporter's account, not their email address (see the Privacy Policy).
            f"Reported by: @{reporter_name}, user id {reporter.id}",
            "",
            f"Review it in the admin area: {app_url}/admin/reports",
        ]
    )
    kind = "Activity post report" if post else "Trip note report" if trip_note else "Profile report"
    return Email(to=REPORTS_TO, subject=f"{kind}: @{profile.username} ({payload.reason})", text=text)


@router.post("/{username}/report", status_code=status.HTTP_202_ACCEPTED)
def report_profile(
    username: str,
    payload: ReportIn,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
    today: date = Depends(get_today),
):
    """Email support about a profile. Signed-in users only, and rate-limited:
    REPORTS_PER_DAY reports a day, and one per profile a day. A trip note or
    an Activity post counts as its owner's profile; a trip note can only be
    reported while it shows in "Hiked by", a post while it shows in the
    feed."""
    profile, seen = find_listed(db, username)
    if profile.id == user.id:
        raise HTTPException(status_code=422, detail="You can't report your own profile.")
    trip_note = None
    if payload.trail_id is not None:
        trip_note = db.scalar(
            select(HikeLog)
            .where(HikeLog.user_id == profile.id, HikeLog.trail_id == payload.trail_id, HikeLog.note.is_not(None))
            .options(joinedload(HikeLog.trail))
        )
        if trip_note is None or not seen.in_community:
            raise HTTPException(status_code=404, detail="Trip note not found")
    post = None
    if payload.post_id is not None:
        if trip_note is not None:
            raise HTTPException(status_code=422, detail="Report a trip note or a post, not both.")
        post = db.scalar(
            select(ActivityPost)
            .where(ActivityPost.id == payload.post_id, ActivityPost.user_id == profile.id)
            .options(joinedload(ActivityPost.hike_log).joinedload(HikeLog.trail))
        )
        if post is None or not is_visible(db, post.id, today):
            raise HTTPException(status_code=404, detail="Post not found")
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
                         details=payload.details, created_at=_now(),
                         trail_id=trip_note.trail_id if trip_note else None,
                         post_id=post.id if post else None))
    db.flush()
    try:
        sender.send(report_email(profile, user, db.get(Profile, user.id), payload, trip_note, post))
    except Exception as error:
        db.rollback()  # not sent, so it doesn't count against the limit
        raise HTTPException(
            status_code=503, detail="We couldn't send your report. Try again in a moment."
        ) from error
    db.commit()
    return {"status": "sent"}
