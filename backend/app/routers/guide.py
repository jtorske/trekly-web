"""Trekly Guide's endpoints: thin wrappers over app/guide/.

- GET  /api/guide/profile                 the signed-in hiker's profile (owner only)
- POST /api/guide/recommend               ranked trails with reasons (guests too)
- GET  /api/guide/readiness/{slug}?date=  "Am I ready?" (signed in)
- GET/PATCH /api/me/guide-settings        "Use my history", dog, scenery

Nothing here is stored: profiles and answers are worked out per request.
A later AI chat layer calls the same functions, not these routes.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, get_current_user
from app.database import get_db
from app.guide.estimate import SCENERY_KEYS, TrailFacts, format_hours, this_weekend
from app.guide.profile import HikerProfile, StatedPreferences, build_profile, get_hiker_profile
from app.guide.readiness import LABELS, readiness
from app.guide.recommend import GuideRequest, recommend
from app.models.preferences import ProfilePreferences
from app.models.trail import Trail
from app.preferences import REGION_SLUGS
from app.provinces import PROVINCE_CODES
from app.routers.activity import optional_user
from app.routers.availability import get_today
from app.routers.trails import live_trails
from app.schemas.trail import TrailListItemOut

router = APIRouter(prefix="/api/guide", tags=["trekly guide"])
settings_router = APIRouter(prefix="/api/me/guide-settings", tags=["trekly guide"])

Difficulty = Literal["easier", "similar", "push"]
Length = Literal["short", "half_day", "full_day", "overnight"]
Activity = Literal["hike", "winter_hike", "snowshoe", "xc_ski"]
Experience = Literal["new", "few_seasons", "seasoned"]
Scenery = Literal[SCENERY_KEYS]  # type: ignore[valid-type]

MAX_EXCLUDE = 60


# ---- shared ---------------------------------------------------------------

def load_catalogue(db: Session) -> dict[UUID, Trail]:
    return {t.id: t for t in db.scalars(select(Trail).where(*live_trails()).order_by(Trail.popularity_rank))}


def facts_of(trails: dict[UUID, Trail], today: date) -> list[TrailFacts]:
    return [TrailFacts.from_trail(t, today) for t in trails.values()]


def resolve_date(value: str | None, today: date) -> date:
    if value in (None, "", "this_weekend"):
        return this_weekend(today)
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Use a date like 2026-12-05, or this_weekend.")
    if day < today:
        raise HTTPException(status_code=422, detail="Pick today or a later date.")
    if (day - today).days > 366:
        raise HTTPException(status_code=422, detail="Pick a date within the next year.")
    return day


# ---- profile --------------------------------------------------------------

class ExperienceOut(BaseModel):
    hike_count: int
    max_distance_km: float
    max_gain_m: float
    max_high_point_m: int | None
    typical_distance_km: float
    typical_gain_m: float
    overnight_count: int
    max_nights: int
    basis: Literal["history", "stated"]
    max_distance_trail: str | None
    max_gain_trail: str | None
    max_high_point_trail: str | None


class PaceOut(BaseModel):
    factor: float
    confidence: Literal["low", "medium", "high"]
    timed_hikes: int


class PreferencesOut(BaseModel):
    hiking_style: str | None
    experience_level: str | None
    favourite_regions: list[str]
    scenery: list[str]
    hikes_with_dog: bool
    use_history: bool


class WinterOut(BaseModel):
    winter_hikes: int
    winter_route_hikes: int


class HikerProfileOut(BaseModel):
    experience: ExperienceOut
    pace: PaceOut
    preferences: PreferencesOut
    home_province: str | None
    saved_trail_ids: list[UUID]
    hiked_trail_ids: list[UUID]
    gear_categories: list[str]
    winter: WinterOut


def profile_out(profile: HikerProfile) -> HikerProfileOut:
    p = profile.preferences
    return HikerProfileOut(
        experience=ExperienceOut(**profile.experience.__dict__),
        pace=PaceOut(**profile.pace.__dict__),
        preferences=PreferencesOut(
            hiking_style=p.hiking_style, experience_level=p.experience_level,
            favourite_regions=list(p.favourite_regions), scenery=list(p.scenery),
            hikes_with_dog=p.hikes_with_dog, use_history=p.use_history,
        ),
        home_province=profile.home_province,
        saved_trail_ids=sorted(profile.saved_trail_ids, key=str),
        hiked_trail_ids=sorted(profile.hiked_trail_ids, key=str),
        gear_categories=sorted(profile.gear_categories),
        winter=WinterOut(**profile.winter.__dict__),
    )


@router.get("/profile", response_model=HikerProfileOut)
def my_profile(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_out(get_hiker_profile(db, user.id))


# ---- recommend ------------------------------------------------------------

class RecommendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # An ISO date, or "this_weekend" (the default).
    date: str | None = Field(default=None, max_length=12)
    difficulty: Difficulty = "similar"
    length: Length | None = None
    province: str | None = None
    regions: list[str] = Field(default_factory=list, max_length=len(REGION_SLUGS))
    dog: bool = False
    activity: Activity = "hike"
    # Null: on in winter.
    avoid_avalanche: bool | None = None
    include_hiked: bool = False
    # "Show me more": trails already shown.
    exclude_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EXCLUDE)
    limit: int = Field(default=3, ge=1, le=6)
    # Asked in the planner when Trekly has no history to go on.
    experience: Experience | None = None

    @field_validator("province")
    @classmethod
    def _province(cls, value):
        if value is not None and value not in PROVINCE_CODES:
            raise ValueError("Unknown province code")
        return value

    @field_validator("regions")
    @classmethod
    def _regions(cls, values):
        unknown = [v for v in values if v not in REGION_SLUGS]
        if unknown:
            raise ValueError(f"Unknown region: {', '.join(unknown)}")
        return list(dict.fromkeys(values))


class RecommendationOut(BaseModel):
    trail: TrailListItemOut
    reasons: list[str]
    est_hours: float | None
    est_label: str | None
    score: float
    avalanche_exposure: str
    winter_activities: list[str]
    dog_policy: str
    # Bringing a dog: "Dogs allowed on a leash..." or "Check dog rules...".
    dog_note: str | None = None


class RecommendOut(BaseModel):
    date: date
    winter: bool
    avoid_avalanche: bool
    results: list[RecommendationOut]
    matching: int
    notes: list[str]
    # Whose numbers the picks are based on.
    basis: Literal["history", "stated"]


def request_profile(db: Session, user: CurrentUser | None, experience: str | None) -> HikerProfile:
    if user is None:
        return build_profile([], StatedPreferences(experience_level=experience))
    profile = get_hiker_profile(db, user.id)
    if experience and not profile.has_history:
        # They told the planner where they're at; that beats the stored answer.
        prefs = profile.preferences
        stated = StatedPreferences(**{**prefs.__dict__, "experience_level": experience})
        profile = build_profile(list(profile.hikes), stated, home_province=profile.home_province,
                                saved_trail_ids=profile.saved_trail_ids, gear_categories=profile.gear_categories)
    return profile


@router.post("/recommend", response_model=RecommendOut)
def recommend_trails(
    body: RecommendIn,
    user: CurrentUser | None = Depends(optional_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    on_date = resolve_date(body.date, today)
    profile = request_profile(db, user, body.experience)
    request = GuideRequest(
        on_date=on_date, difficulty=body.difficulty, length=body.length, province=body.province,
        regions=tuple(body.regions), dog=body.dog, activity=body.activity,
        avoid_avalanche=body.avoid_avalanche, include_hiked=body.include_hiked,
        exclude_ids=frozenset(body.exclude_ids), limit=body.limit,
    )
    catalogue = load_catalogue(db)
    result = recommend(profile, request, facts_of(catalogue, today))
    return RecommendOut(
        date=on_date,
        winter=request.winter,
        avoid_avalanche=request.avoids_avalanche,
        results=[
            RecommendationOut(
                trail=TrailListItemOut.model_validate(catalogue[r.trail.id]),
                reasons=list(r.reasons),
                est_hours=r.est_hours,
                est_label=format_hours(r.est_hours) if r.est_hours is not None else None,
                score=r.score,
                avalanche_exposure=r.trail.avalanche_exposure,
                winter_activities=list(r.trail.winter_activities),
                dog_policy=r.trail.dog_policy,
                dog_note=r.dog_note,
            )
            for r in result.results
        ],
        matching=result.matching,
        notes=result.notes,
        basis=profile.experience.basis,
    )


# ---- readiness ------------------------------------------------------------

class ReasonOut(BaseModel):
    kind: str
    level: Literal["ready", "stretch", "not_yet", "info"]
    text: str


class ReadinessOut(BaseModel):
    verdict: Literal["ready", "stretch", "not_yet"]
    label: str
    date: date
    reasons: list[ReasonOut]
    est_hours: float | None
    est_label: str | None
    gentle: bool
    build_up: list[TrailListItemOut]
    avalanche_link: str | None
    pace_factor: float
    pace_confidence: str


@router.get("/readiness/{slug}", response_model=ReadinessOut)
def check_readiness(
    slug: str,
    date_: str | None = Query(default=None, alias="date", max_length=12),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    trail = db.scalar(select(Trail).where(Trail.slug == slug.lower(), Trail.retired_at.is_(None)))
    if trail is None:
        raise HTTPException(status_code=404, detail="Trail not found")
    on_date = resolve_date(date_, today) if date_ else today
    profile = get_hiker_profile(db, user.id)
    catalogue = load_catalogue(db)
    result = readiness(profile, TrailFacts.from_trail(trail, today), on_date, facts_of(catalogue, today))
    return ReadinessOut(
        verdict=result.verdict,
        label=LABELS[result.verdict],
        date=on_date,
        reasons=[ReasonOut(kind=r.kind, level=r.level, text=r.text) for r in result.reasons],
        est_hours=result.est_hours,
        est_label=format_hours(result.est_hours) if result.est_hours is not None else None,
        gentle=result.gentle,
        build_up=[TrailListItemOut.model_validate(catalogue[t.id]) for t in result.build_up if t.id in catalogue],
        avalanche_link=result.avalanche_link,
        pace_factor=profile.pace.factor,
        pace_confidence=profile.pace.confidence,
    )


# ---- settings -------------------------------------------------------------

class GuideSettingsOut(BaseModel):
    use_history: bool
    hikes_with_dog: bool
    scenery: list[str]


class GuideSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_history: bool | None = None
    hikes_with_dog: bool | None = None
    scenery: list[Scenery] | None = Field(default=None, max_length=len(SCENERY_KEYS))


def _settings_out(row: ProfilePreferences | None) -> GuideSettingsOut:
    if row is None:
        return GuideSettingsOut(use_history=True, hikes_with_dog=False, scenery=[])
    return GuideSettingsOut(use_history=row.guide_use_history, hikes_with_dog=row.hikes_with_dog,
                            scenery=list(row.scenery or []))


@settings_router.get("", response_model=GuideSettingsOut)
def get_guide_settings(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return _settings_out(db.get(ProfilePreferences, user.id))


@settings_router.patch("", response_model=GuideSettingsOut)
def update_guide_settings(
    body: GuideSettingsIn, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = db.get(ProfilePreferences, user.id)
    if row is None:
        row = ProfilePreferences(user_id=user.id, favourite_regions=[])
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.get(ProfilePreferences, user.id)
    if body.use_history is not None:
        row.guide_use_history = body.use_history
    if body.hikes_with_dog is not None:
        row.hikes_with_dog = body.hikes_with_dog
    if body.scenery is not None:
        row.scenery = list(dict.fromkeys(body.scenery))
    db.commit()
    return _settings_out(row)
