"""The admin area: overview, users, reports and account actions.

Every route depends on require_admin (app/admin_access.py), so a signed-in
non-admin gets 403 and a signed-out caller 401, whatever the frontend shows.

Account data is read from auth.users through the backend's own database
connection, and account changes (ban, unban, password reset) go through the
Supabase admin API with the service-role key (app/supabase_admin.py). Both
stay on the server: no response here ever carries a key or a token.

Every action writes an admin_audit_log row (who, what, when, on whom) in the
same transaction as the change it records. For Supabase actions the API call
runs first and the row is written only once it has succeeded, so the log
never claims a ban that didn't happen. Account deletion is deliberately not
here: users delete their own accounts (DELETE /api/me).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.activity import MILESTONES
from app.admin_access import audit, is_admin, require_admin
from app.alert_poller import JOB_NAME as POLLER_JOB
from app.auth import CurrentUser
from app.database import get_db
from app.account_labels import AccountLabelName, real_user
from app.models.account import Profile
from app.models.account_label import AccountLabel
from app.models.activity import ActivityPost
from app.models.admin import AUTH_USERS, AdminAuditLog
from app.models.availability import AvailabilityAlert, JobLock
from app.models.backcountry import BackcountrySite
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileReport, ProfileSettings
from app.models.trail import Trail
from app.models.user_gear import UserGearItem
from app.points_config import RANKS
from app.supabase_admin import SupabaseAdmin, SupabaseAdminError, reset_redirect, supabase_admin_from_env

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

SIGNUP_WEEKS = 12
PER_PAGE_MAX = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite (tests) hands back naive UTC datetimes; Postgres aware ones."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_supabase_admin() -> SupabaseAdmin:
    """Overridden in tests."""
    client = supabase_admin_from_env()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account actions aren't configured on this server (SUPABASE_SERVICE_ROLE_KEY).",
        )
    return client




# ----------------------------------------------------------------- shared SQL

hidden_expr = exists().where(ProfileModeration.user_id == AUTH_USERS.c.id)


def _count(model, *where) -> Any:
    return select(func.count()).select_from(model).where(*where).scalar_subquery()


hikes_expr = _count(HikeLog, HikeLog.user_id == AUTH_USERS.c.id)
gear_expr = _count(UserGearItem, UserGearItem.user_id == AUTH_USERS.c.id)
alerts_expr = _count(AvailabilityAlert, AvailabilityAlert.user_id == AUTH_USERS.c.id)
label_expr = select(AccountLabel.label).where(AccountLabel.user_id == AUTH_USERS.c.id).scalar_subquery()
visibility_expr = case(
    (hidden_expr, "hidden"),
    (Profile.username.is_(None), "no_username"),
    (and_(ProfileSettings.user_id.is_not(None), ProfileSettings.is_private.is_(False)), "public"),
    else_="private",
)

SORTS = {
    "joined": AUTH_USERS.c.created_at,
    "last_sign_in": AUTH_USERS.c.last_sign_in_at,
    "name": func.lower(Profile.display_name),
    "username": Profile.username,
    "email": func.lower(AUTH_USERS.c.email),
    "hikes": hikes_expr,
    "gear": gear_expr,
    "alerts": alerts_expr,
}
SortKey = Literal["joined", "last_sign_in", "name", "username", "email", "hikes", "gear", "alerts"]
UserFilter = Literal["all", "public", "private", "hidden", "banned", "no_username"]


def _users_query():
    return (
        select(
            AUTH_USERS.c.id,
            AUTH_USERS.c.email,
            AUTH_USERS.c.created_at,
            AUTH_USERS.c.last_sign_in_at,
            AUTH_USERS.c.banned_until,
            AUTH_USERS.c.raw_app_meta_data,
            Profile.display_name,
            Profile.username,
            Profile.avatar_path,
            hikes_expr.label("hikes"),
            gear_expr.label("gear"),
            alerts_expr.label("alerts"),
            visibility_expr.label("visibility"),
            label_expr.label("label"),
        )
        .select_from(AUTH_USERS)
        .outerjoin(Profile, Profile.id == AUTH_USERS.c.id)
        .outerjoin(ProfileSettings, ProfileSettings.user_id == AUTH_USERS.c.id)
    )


# ----------------------------------------------------------------- schemas


class UserRow(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    username: str | None
    avatar_path: str | None
    providers: list[str]
    joined_at: datetime | None
    last_sign_in_at: datetime | None
    hikes: int
    gear: int
    alerts: int
    visibility: Literal["public", "private", "hidden", "no_username"]
    banned: bool
    is_admin: bool
    # "official" (the Trekly account) or "demo"; left out of the overview's numbers.
    label: AccountLabelName | None = None


class UserPage(BaseModel):
    items: list[UserRow]
    total: int
    page: int
    per_page: int


def _providers(meta: Any) -> list[str]:
    if not isinstance(meta, dict):
        return []
    providers = meta.get("providers")
    if isinstance(providers, list):
        return [str(p) for p in providers]
    return [str(meta["provider"])] if meta.get("provider") else []


def _row(row, now: datetime) -> UserRow:
    banned_until = _aware(row.banned_until)
    return UserRow(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        username=row.username,
        avatar_path=row.avatar_path,
        providers=_providers(row.raw_app_meta_data),
        joined_at=_aware(row.created_at),
        last_sign_in_at=_aware(row.last_sign_in_at),
        hikes=row.hikes or 0,
        gear=row.gear or 0,
        alerts=row.alerts or 0,
        visibility=row.visibility,
        banned=banned_until is not None and banned_until > now,
        is_admin=is_admin(row.id),
        label=row.label,
    )


class PollerOut(BaseModel):
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_result: str | None
    running: bool


class WeekCount(BaseModel):
    week_start: date
    count: int


class OverviewOut(BaseModel):
    users_total: int
    signups_by_week: list[WeekCount]
    hikes_total: int
    active_alerts: int
    open_reports: int
    poller: PollerOut | None


class PersonRef(BaseModel):
    id: UUID
    username: str | None
    display_name: str | None


class AuditOut(BaseModel):
    id: UUID
    action: str
    admin: PersonRef
    target_user: PersonRef | None
    target_report_id: UUID | None
    details: dict
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    per_page: int


class TrailRef(BaseModel):
    id: UUID
    name: str


class ReportPost(BaseModel):
    """The reported Activity post as it reads now."""

    id: UUID
    kind: Literal["hike", "milestone", "rank"]
    # e.g. "Hiked Skyline Trail", "Earned Park hopper", "Reached Ridge Walker".
    summary: str
    trail: TrailRef | None
    note: str | None
    has_photo: bool
    hidden: bool
    hidden_reason: str | None


class ReportOut(BaseModel):
    id: UUID
    kind: Literal["profile", "trip_note", "post"]
    status: Literal["open", "resolved"]
    reason: str
    details: str | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: PersonRef | None
    reported: PersonRef
    reported_hidden: bool
    reporter: PersonRef
    trail: TrailRef | None
    # The trip note as it reads now (None once it's removed or edited away).
    note: str | None
    # A post report's post (None once the owner deleted it).
    post: ReportPost | None = None


class ReportPage(BaseModel):
    items: list[ReportOut]
    total: int
    page: int
    per_page: int


class HikeOut(BaseModel):
    id: UUID
    trail: TrailRef
    # None for a hike from before they joined.
    hiked_on: date | None
    note: str | None
    has_photo: bool
    verified: bool


class AlertOut(BaseModel):
    id: UUID
    site_name: str
    trail: TrailRef | None
    start_date: date
    nights: int
    party_size: int
    status: str
    created_at: datetime


class UserDetail(UserRow):
    bio: str | None
    home_region: str | None
    hidden_at: datetime | None
    hidden_reason: str | None
    banned_until: datetime | None
    hikes_list: list[HikeOut]
    alerts_list: list[AlertOut]
    reports_about: list[ReportOut]
    reports_filed: int
    audit: list[AuditOut]


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def _clean(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ReportStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "resolved"]


class ActionOut(BaseModel):
    ok: Literal[True] = True
    message: str


# ----------------------------------------------------------------- helpers


def _people(db: Session, ids: set[UUID | None]) -> dict[UUID, PersonRef]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(select(Profile.id, Profile.username, Profile.display_name).where(Profile.id.in_(ids))).all()
    found = {row.id: PersonRef(id=row.id, username=row.username, display_name=row.display_name) for row in rows}
    return {i: found.get(i, PersonRef(id=i, username=None, display_name=None)) for i in ids}


def _audit_out(db: Session, rows: list[AdminAuditLog]) -> list[AuditOut]:
    people = _people(db, {r.admin_id for r in rows} | {r.target_user_id for r in rows})
    return [
        AuditOut(
            id=r.id,
            action=r.action,
            admin=people[r.admin_id],
            target_user=people.get(r.target_user_id) if r.target_user_id else None,
            target_report_id=r.target_report_id,
            details=r.details or {},
            created_at=_aware(r.created_at),
        )
        for r in rows
    ]


def _post_summary(post: ActivityPost) -> str:
    if post.kind == "hike":
        return f"Hiked {post.hike_log.trail.name}" if post.hike_log else "Hike"
    if post.kind == "milestone":
        milestone = MILESTONES.get(post.milestone)
        return f"Earned {milestone.title if milestone else post.milestone}"
    title = RANKS[post.rank_level - 1][1] if 1 <= post.rank_level <= len(RANKS) else f"level {post.rank_level}"
    return f"Reached {title}"


def _post_out(post: ActivityPost) -> ReportPost:
    hike = post.hike_log if post.kind == "hike" else None
    return ReportPost(
        id=post.id,
        kind=post.kind,
        summary=_post_summary(post),
        trail=TrailRef(id=hike.trail.id, name=hike.trail.name) if hike else None,
        note=hike.note if hike else None,
        has_photo=bool(hike and hike.photo_path),
        hidden=post.hidden_at is not None,
        hidden_reason=post.hidden_reason,
    )


def _reports_out(db: Session, reports: list[ProfileReport]) -> list[ReportOut]:
    people = _people(
        db,
        {r.profile_id for r in reports} | {r.reporter_id for r in reports} | {r.resolved_by for r in reports},
    )
    hidden = set(db.scalars(select(ProfileModeration.user_id).where(
        ProfileModeration.user_id.in_({r.profile_id for r in reports})
    ))) if reports else set()
    trail_ids = {r.trail_id for r in reports if r.trail_id}
    trails = {t.id: t for t in db.scalars(select(Trail).where(Trail.id.in_(trail_ids)))} if trail_ids else {}
    notes = {}
    if trail_ids:
        for log in db.scalars(select(HikeLog).where(
            HikeLog.trail_id.in_(trail_ids), HikeLog.user_id.in_({r.profile_id for r in reports})
        )):
            notes[(log.user_id, log.trail_id)] = log.note
    post_ids = {r.post_id for r in reports if r.post_id}
    posts = {p.id: p for p in db.scalars(select(ActivityPost).where(ActivityPost.id.in_(post_ids)))} if post_ids else {}
    out = []
    for r in reports:
        trail = trails.get(r.trail_id) if r.trail_id else None
        post = posts.get(r.post_id) if r.post_id else None
        out.append(ReportOut(
            id=r.id,
            kind="post" if post else "trip_note" if r.trail_id else "profile",
            status=r.status,
            reason=r.reason,
            details=r.details,
            created_at=_aware(r.created_at),
            resolved_at=_aware(r.resolved_at),
            resolved_by=people.get(r.resolved_by) if r.resolved_by else None,
            reported=people[r.profile_id],
            reported_hidden=r.profile_id in hidden,
            reporter=people[r.reporter_id],
            trail=TrailRef(id=trail.id, name=trail.name) if trail else None,
            note=notes.get((r.profile_id, r.trail_id)) if r.trail_id else None,
            post=_post_out(post) if post else None,
        ))
    return out


def _user_row(db: Session, user_id: UUID):
    row = db.execute(_users_query().where(AUTH_USERS.c.id == user_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _profile(db: Session, user_id: UUID) -> Profile:
    _user_row(db, user_id)
    profile = db.get(Profile, user_id)
    if profile is None:
        raise HTTPException(status_code=409, detail="This account has no profile yet.")
    return profile


# ----------------------------------------------------------------- reads


@router.get("/me")
def whoami():
    """200 for admins (the dependency 403s everyone else); the frontend uses it to show the admin nav."""
    return {"admin": True}


@router.get("/overview", response_model=OverviewOut)
def overview(db: Session = Depends(get_db)):
    now = _now()
    this_week = (now - timedelta(days=now.weekday())).date()
    first_week = this_week - timedelta(weeks=SIGNUP_WEEKS - 1)
    joined = db.scalars(
        select(AUTH_USERS.c.created_at).where(
            real_user(AUTH_USERS.c.id),
            AUTH_USERS.c.created_at >= datetime.combine(first_week, datetime.min.time(), tzinfo=timezone.utc)
        )
    ).all()
    weeks = {first_week + timedelta(weeks=i): 0 for i in range(SIGNUP_WEEKS)}
    for created in joined:
        day = _aware(created).date()
        monday = day - timedelta(days=day.weekday())
        if monday in weeks:
            weeks[monday] += 1

    lock = db.get(JobLock, POLLER_JOB)
    poller = None
    if lock is not None:
        locked_until = _aware(lock.locked_until)
        poller = PollerOut(
            last_started_at=_aware(lock.last_started_at),
            last_finished_at=_aware(lock.last_finished_at),
            last_result=lock.last_result,
            running=locked_until is not None and locked_until > now,
        )
    return OverviewOut(
        users_total=db.scalar(select(func.count()).select_from(AUTH_USERS).where(real_user(AUTH_USERS.c.id))) or 0,
        signups_by_week=[WeekCount(week_start=w, count=c) for w, c in sorted(weeks.items())],
        hikes_total=db.scalar(select(func.count()).select_from(HikeLog).where(real_user(HikeLog.user_id))) or 0,
        active_alerts=db.scalar(
            select(func.count()).select_from(AvailabilityAlert).where(
                AvailabilityAlert.status == "active", real_user(AvailabilityAlert.user_id)
            )
        ) or 0,
        open_reports=db.scalar(
            select(func.count()).select_from(ProfileReport).where(ProfileReport.status == "open")
        ) or 0,
        poller=poller,
    )


@router.get("/users", response_model=UserPage)
def list_users(
    db: Session = Depends(get_db),
    q: str = Query(default="", max_length=100),
    sort: SortKey = "joined",
    direction: Literal["asc", "desc"] = Query(default="desc", alias="dir"),
    filter: UserFilter = "all",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=PER_PAGE_MAX),
):
    query = _users_query()
    term = q.strip().lstrip("@").lower()
    if term:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        conditions = [
            func.lower(AUTH_USERS.c.email).like(like, escape="\\"),
            func.lower(Profile.username).like(like, escape="\\"),
            func.lower(Profile.display_name).like(like, escape="\\"),
        ]
        try:
            conditions.append(AUTH_USERS.c.id == UUID(term))
        except ValueError:
            pass
        query = query.where(or_(*conditions))
    now = _now()
    if filter == "banned":
        query = query.where(AUTH_USERS.c.banned_until > now)
    elif filter != "all":
        query = query.where(visibility_expr == filter)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    column = SORTS[sort]
    order = column.asc() if direction == "asc" else column.desc()
    rows = db.execute(
        query.order_by(order.nulls_last(), AUTH_USERS.c.id).offset((page - 1) * per_page).limit(per_page)
    ).all()
    return UserPage(items=[_row(row, now) for row in rows], total=total, page=page, per_page=per_page)


@router.get("/users/{user_id}", response_model=UserDetail)
def user_detail(user_id: UUID, db: Session = Depends(get_db)):
    now = _now()
    row = _user_row(db, user_id)
    profile = db.get(Profile, user_id)
    moderation = db.get(ProfileModeration, user_id)

    hikes = db.execute(
        select(HikeLog, Trail.name)
        .join(Trail, Trail.id == HikeLog.trail_id)
        .where(HikeLog.user_id == user_id)
        .order_by(HikeLog.hiked_on.desc().nulls_last(), HikeLog.created_at.desc())
    ).all()
    alert_trail = aliased(Trail)
    alerts = db.execute(
        select(AvailabilityAlert, BackcountrySite.name, alert_trail.name)
        .join(BackcountrySite, BackcountrySite.id == AvailabilityAlert.site_id)
        .outerjoin(alert_trail, alert_trail.id == AvailabilityAlert.trail_id)
        .where(AvailabilityAlert.user_id == user_id)
        .order_by(AvailabilityAlert.created_at.desc())
    ).all()
    reports = db.scalars(
        select(ProfileReport).where(ProfileReport.profile_id == user_id).order_by(ProfileReport.created_at.desc())
    ).all()
    audit_rows = db.scalars(
        select(AdminAuditLog)
        .where(AdminAuditLog.target_user_id == user_id)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(50)
    ).all()

    base = _row(row, now).model_dump()
    return UserDetail(
        **base,
        bio=profile.bio if profile else None,
        home_region=profile.home_region if profile else None,
        hidden_at=_aware(moderation.hidden_at) if moderation else None,
        hidden_reason=moderation.reason if moderation else None,
        banned_until=_aware(row.banned_until) if base["banned"] else None,
        hikes_list=[
            HikeOut(id=log.id, trail=TrailRef(id=log.trail_id, name=name), hiked_on=log.hiked_on,
                    note=log.note, has_photo=bool(log.photo_path), verified=bool(log.verified))
            for log, name in hikes
        ],
        alerts_list=[
            AlertOut(
                id=alert.id, site_name=site_name,
                trail=TrailRef(id=alert.trail_id, name=trail_name) if alert.trail_id and trail_name else None,
                start_date=alert.start_date, nights=alert.nights, party_size=alert.party_size,
                status=alert.status, created_at=_aware(alert.created_at),
            )
            for alert, site_name, trail_name in alerts
        ],
        reports_about=_reports_out(db, list(reports)),
        reports_filed=db.scalar(
            select(func.count()).select_from(ProfileReport).where(ProfileReport.reporter_id == user_id)
        ) or 0,
        audit=_audit_out(db, list(audit_rows)),
    )


@router.get("/reports", response_model=ReportPage)
def list_reports(
    db: Session = Depends(get_db),
    status_filter: Literal["open", "resolved", "all"] = Query(default="open", alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=PER_PAGE_MAX),
):
    query = select(ProfileReport)
    if status_filter != "all":
        query = query.where(ProfileReport.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(ProfileReport.created_at.desc(), ProfileReport.id).offset((page - 1) * per_page).limit(per_page)
    ).all()
    return ReportPage(items=_reports_out(db, list(rows)), total=total, page=page, per_page=per_page)


@router.get("/audit", response_model=AuditPage)
def list_audit(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=PER_PAGE_MAX),
):
    total = db.scalar(select(func.count()).select_from(AdminAuditLog)) or 0
    rows = db.scalars(
        select(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return AuditPage(items=_audit_out(db, list(rows)), total=total, page=page, per_page=per_page)


# ----------------------------------------------------------------- actions


@router.post("/users/{user_id}/hide", response_model=ActionOut)
def hide_user(
    user_id: UUID, payload: ReasonIn, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)
):
    profile = _profile(db, user_id)
    if db.get(ProfileModeration, user_id) is not None:
        raise HTTPException(status_code=409, detail="This profile is already hidden.")
    db.add(ProfileModeration(user_id=user_id, hidden_by=admin.id, hidden_at=_now(), reason=payload.reason))
    audit(db, admin, "hide_profile", user_id=user_id, reason=payload.reason, username=profile.username)
    db.commit()
    return ActionOut(message="Profile hidden.")


@router.post("/users/{user_id}/unhide", response_model=ActionOut)
def unhide_user(user_id: UUID, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    profile = _profile(db, user_id)
    row = db.get(ProfileModeration, user_id)
    if row is None:
        raise HTTPException(status_code=409, detail="This profile isn't hidden.")
    db.delete(row)
    audit(db, admin, "unhide_profile", user_id=user_id, username=profile.username)
    db.commit()
    return ActionOut(message="Profile visible again.")


@router.post("/users/{user_id}/clear-username", response_model=ActionOut)
def clear_username(
    user_id: UUID, payload: ReasonIn, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)
):
    """Remove the username. The app then asks the user to choose a new one
    before anything else (the username gate); the database lets only the
    server, never a client, clear one (migration 5d1c0e7a9b42)."""
    profile = _profile(db, user_id)
    if profile.username is None:
        raise HTTPException(status_code=409, detail="This account has no username.")
    old = profile.username
    profile.username = None
    audit(db, admin, "clear_username", user_id=user_id, username=old, reason=payload.reason)
    db.commit()
    return ActionOut(message=f"Cleared @{old}. They'll be asked to choose a new username.")


def _account_target(db: Session, admin: CurrentUser, user_id: UUID, verb: str):
    row = _user_row(db, user_id)
    if user_id == admin.id:
        raise HTTPException(status_code=422, detail=f"You can't {verb} your own account.")
    if is_admin(user_id):
        raise HTTPException(status_code=422, detail=f"You can't {verb} another admin here.")
    return row


def _supabase(call, *args) -> None:
    try:
        call(*args)
    except SupabaseAdminError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from None


@router.post("/users/{user_id}/ban", response_model=ActionOut)
def ban_user(
    user_id: UUID,
    payload: ReasonIn,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    supabase: SupabaseAdmin = Depends(get_supabase_admin),
):
    """Block sign-in and session refresh (Supabase ban). A session already
    open keeps working until its access token expires (an hour at most)."""
    _account_target(db, admin, user_id, "ban")
    _supabase(supabase.ban, user_id)
    audit(db, admin, "ban_user", user_id=user_id, reason=payload.reason)
    db.commit()
    return ActionOut(message="Banned. They can't sign in.")


@router.post("/users/{user_id}/unban", response_model=ActionOut)
def unban_user(
    user_id: UUID,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    supabase: SupabaseAdmin = Depends(get_supabase_admin),
):
    _account_target(db, admin, user_id, "unban")
    _supabase(supabase.unban, user_id)
    audit(db, admin, "unban_user", user_id=user_id)
    db.commit()
    return ActionOut(message="Unbanned. They can sign in again.")


@router.post("/users/{user_id}/password-reset", response_model=ActionOut)
def send_password_reset(
    user_id: UUID,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    supabase: SupabaseAdmin = Depends(get_supabase_admin),
):
    row = _user_row(db, user_id)
    if not row.email:
        raise HTTPException(status_code=422, detail="This account has no email address.")
    _supabase(supabase.send_password_reset, row.email, reset_redirect())
    audit(db, admin, "send_password_reset", user_id=user_id)
    db.commit()
    return ActionOut(message="Password reset email sent.")


@router.patch("/reports/{report_id}", response_model=ReportOut)
def set_report_status(
    report_id: UUID,
    payload: ReportStatusIn,
    admin: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = db.get(ProfileReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != payload.status:
        report.status = payload.status
        report.resolved_at = _now() if payload.status == "resolved" else None
        report.resolved_by = admin.id if payload.status == "resolved" else None
        audit(
            db, admin, "resolve_report" if payload.status == "resolved" else "reopen_report",
            user_id=report.profile_id, report_id=report.id,
        )
        db.commit()
    return _reports_out(db, [report])[0]


# ----------------------------------------------------------------- Activity posts


def _post(db: Session, post_id: UUID) -> ActivityPost:
    post = db.get(ActivityPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post("/activity/{post_id}/hide", response_model=ActionOut)
def hide_post(
    post_id: UUID, payload: ReasonIn, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)
):
    """Hide one Activity post from everyone (its owner keeps the hike itself)."""
    post = _post(db, post_id)
    if post.hidden_at is not None:
        raise HTTPException(status_code=409, detail="This post is already hidden.")
    post.hidden_at, post.hidden_by, post.hidden_reason = _now(), admin.id, payload.reason
    audit(db, admin, "hide_post", user_id=post.user_id, post_id=str(post.id), post=_post_summary(post),
          reason=payload.reason)
    db.commit()
    return ActionOut(message="Post hidden.")


@router.post("/activity/{post_id}/unhide", response_model=ActionOut)
def unhide_post(post_id: UUID, admin: CurrentUser = Depends(require_admin), db: Session = Depends(get_db)):
    post = _post(db, post_id)
    if post.hidden_at is None:
        raise HTTPException(status_code=409, detail="This post isn't hidden.")
    post.hidden_at = post.hidden_by = post.hidden_reason = None
    audit(db, admin, "unhide_post", user_id=post.user_id, post_id=str(post.id), post=_post_summary(post))
    db.commit()
    return ActionOut(message="Post visible again.")
