"""Setting up and removing the labeled accounts (app/account_labels.py).

The database work lives here so tests can run it; the scripts
(scripts/official_account.py, scripts/demo_accounts.py) add the two
outside services through small interfaces:

- AuthAdmin: create and delete Supabase auth users (app/supabase_admin.py).
  Accounts get a long random password nobody keeps, so nobody can sign in
  as them; admins post as @trekly through /admin/posts instead.
- Avatars: upload and delete files in the public avatars bucket.

Removing demo accounts deletes every row that names them in any table
(`sweep`), their avatars, then the auth users. The admin audit log keeps
its rows by design, as it does for every deleted account.
"""

import io
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Uuid, delete, func, select
from sqlalchemy.orm import Session

from app.account_labels import OFFICIAL_USERNAME, official_id
from app.activity import after_hike_saved, standing
from app.database import Base
from app.demo_data import DEMO_HIKERS, DemoHiker
from app.milestones import evaluate, gather
from app.milestones_config import ACTIVE
from app.models.account import Profile, SavedTrail
from app.models.account_label import AccountLabel
from app.models.activity import ActivityPost, ActivityReaction
from app.models.catalog import CatalogCategory, CatalogProduct
from app.models.featured_badge import MAX_FEATURED, FeaturedBadge
from app.models.hike_log import HikeLog
from app.models.preferences import ProfilePreferences
from app.models.privacy import ProfileSettings
from app.models.trail import Trail
from app.models.trip_plan import TripPlan
from app.models.user_gear import UserGearItem
from app.privacy import ensure_settings

AVATAR_BUCKET = "avatars"
OFFICIAL_AVATAR = Path(__file__).resolve().parents[1] / "scripts" / "assets" / "trekly-avatar.webp"
OFFICIAL_EMAIL = "official@trekly.invalid"
DEMO_EMAIL = "{username}@demo.trekly.invalid"
# Columns that hold a user's id, in any table (`profiles.id` too).
USER_COLUMNS = {"user_id", "follower_id", "followee_id", "actor_id", "reporter_id", "profile_id"}
# Rows that outlive the accounts they mention, on purpose.
KEPT_TABLES = {"admin_audit_log"}


class AuthAdmin(Protocol):
    def create_user(self, email: str, password: str, display_name: str) -> UUID: ...
    def delete_user(self, user_id: UUID) -> None: ...


class AvatarStore(Protocol):
    def upload(self, path: str, data: bytes) -> None: ...
    def delete(self, paths: list[str]) -> None: ...


def _password() -> str:
    return secrets.token_urlsafe(32)


def _label(db: Session, user_id: UUID, label: str) -> None:
    if db.get(AccountLabel, user_id) is None:
        db.add(AccountLabel(user_id=user_id, label=label))
        db.flush()


def _profile(db: Session, user_id: UUID) -> Profile:
    profile = db.get(Profile, user_id)
    if profile is None:  # the signup trigger makes it in Postgres; tests have no trigger
        profile = Profile(id=user_id)
        db.add(profile)
        db.flush()
    return profile


def _avatar(store: AvatarStore | None, user_id: UUID, data: bytes) -> str | None:
    if store is None:
        return None
    path = f"{user_id}/{uuid4()}.webp"
    store.upload(path, data)
    return path


# ------------------------------------------------------------------ official


def ensure_official(db: Session, auth: AuthAdmin, store: AvatarStore | None) -> tuple[UUID, bool]:
    """The @trekly account, made if missing. Returns (id, made now)."""
    existing = official_id(db)
    if existing is not None:
        return existing, False
    user_id = auth.create_user(OFFICIAL_EMAIL, _password(), "Trekly")
    _label(db, user_id, "official")  # first: it lets the account hold the reserved name
    profile = _profile(db, user_id)
    profile.username = OFFICIAL_USERNAME
    profile.display_name = "Trekly"
    profile.bio = "The Trekly team. New trails, features and trail tips."
    profile.avatar_path = _avatar(store, user_id, OFFICIAL_AVATAR.read_bytes())
    settings = ensure_settings(db, user_id)
    _official_settings(settings)
    _finished_onboarding(db, user_id)
    db.commit()
    return user_id, True


def _official_settings(settings: ProfileSettings) -> None:
    settings.is_private = False
    settings.share_activity = True
    # Its profile is its posts: no journal, rank, gear or community listings.
    settings.show_journal = False
    settings.show_rank = False
    settings.show_gear = False
    settings.show_saved_trails = False
    settings.show_trip_plans = False
    settings.show_in_community = False
    settings.show_home_province = False
    settings.show_visit_streak = False
    settings.allow_search_indexing = True
    settings.visibility_chosen_at = datetime.now(timezone.utc)


def _finished_onboarding(db: Session, user_id: UUID, experience: str | None = None, style: str | None = None) -> None:
    prefs = db.get(ProfilePreferences, user_id)
    if prefs is None:
        prefs = ProfilePreferences(user_id=user_id)
        db.add(prefs)
    prefs.onboarding_status = "completed"
    prefs.onboarding_finished_at = datetime.now(timezone.utc)
    if experience:
        prefs.experience = experience
    if style:
        prefs.hiking_style = style


@dataclass(frozen=True)
class OfficialDraft:
    body: str
    # Trail name and province, linked (its photo shows when it has one).
    trail: tuple[str, str] | None = None
    days_ago: int = 0


def find_trail(db: Session, name: str, province: str) -> Trail | None:
    return db.scalar(
        select(Trail).where(Trail.name == name, Trail.province_code == province, Trail.retired_at.is_(None))
        .order_by(Trail.popularity_rank).limit(1)
    )


def post_drafts(db: Session, drafts: list[OfficialDraft], now: datetime | None = None) -> list[ActivityPost]:
    """Posts each draft from @trekly unless the same text is already posted."""
    user_id = official_id(db)
    if user_id is None:
        raise RuntimeError("Make the Trekly account first.")
    now = now or datetime.now(timezone.utc)
    made = []
    for draft in drafts:
        if db.scalar(select(ActivityPost.id).where(ActivityPost.user_id == user_id, ActivityPost.body == draft.body)):
            continue
        trail = find_trail(db, *draft.trail) if draft.trail else None
        if draft.trail and trail is None:
            raise RuntimeError(f"Trail not found: {draft.trail[0]} ({draft.trail[1]})")
        post = ActivityPost(user_id=user_id, kind="announcement", body=draft.body,
                            trail_id=trail.id if trail else None,
                            created_at=now - timedelta(days=draft.days_ago))
        db.add(post)
        made.append(post)
    db.commit()
    return made


# ------------------------------------------------------------------ demo


def demo_ids(db: Session) -> list[UUID]:
    return list(db.scalars(select(AccountLabel.user_id).where(AccountLabel.label == "demo")))


def avatar_image(username: str, colours: tuple[str, str]) -> bytes:
    """A simple drawn avatar (a mountain on a colour), never a real face."""
    from PIL import Image, ImageDraw

    size = 512
    image = Image.new("RGB", (size, size), colours[0])
    draw = ImageDraw.Draw(image)
    seed = sum(map(ord, username))
    peak = 190 + seed % 130
    draw.polygon([(40, 420), (peak, 150), (peak + 70, 230), (380, 120), (500, 420)], fill=colours[1])
    draw.polygon([(peak - 34, 200), (peak, 150), (peak + 34, 200), (peak + 10, 190), (peak - 8, 206)], fill="#ffffff")
    draw.rectangle([0, 420, size, size], fill=colours[1])
    out = io.BytesIO()
    image.save(out, "WEBP", quality=88)
    return out.getvalue()


def _evening(day: date) -> datetime:
    return datetime.combine(day, time(19, 30), tzinfo=timezone.utc)


def _gear(db: Session, user_id: UUID, slugs: tuple[str, ...], offset: int) -> int:
    added = 0
    for slug in slugs:
        category = db.scalar(select(CatalogCategory).where(CatalogCategory.slug == slug))
        if category is None:
            continue
        products = db.scalars(
            select(CatalogProduct).where(CatalogProduct.category_id == category.id, CatalogProduct.status == "active")
            .order_by(CatalogProduct.name)
        ).all()
        if not products:
            continue
        product = products[offset % len(products)]
        db.add(UserGearItem(user_id=user_id, product_id=product.id, category_id=category.id, quantity=1,
                            condition="good"))
        added += 1
    return added


def _featured(db: Session, user_id: UUID) -> None:
    earned = [m for m, result in evaluate(gather(db, user_id), ACTIVE)
              if result.earned and m.category not in ("planning", "gear", "seasons")]
    # The config lists harder milestones later in each group; feature the last few.
    for position, milestone in enumerate(earned[-MAX_FEATURED:][::-1]):
        db.add(FeaturedBadge(user_id=user_id, position=position, milestone=milestone.id))


def create_demo(db: Session, auth: AuthAdmin, store: AvatarStore | None, today: date,
                hikers: tuple[DemoHiker, ...] = DEMO_HIKERS, log: Callable[[str], None] = lambda _m: None) -> list[UUID]:
    """Makes every demo hiker that doesn't exist yet. Returns the new ids."""
    made: list[UUID] = []
    for index, hiker in enumerate(hikers):
        if db.scalar(select(Profile.id).where(Profile.username == hiker.username)):
            log(f"{hiker.username}: already there, skipped")
            continue
        user_id = auth.create_user(DEMO_EMAIL.format(username=hiker.username.replace("_", "-")), _password(),
                                   hiker.display_name)
        _label(db, user_id, "demo")
        made.append(user_id)
        profile = _profile(db, user_id)
        profile.username = hiker.username
        profile.display_name = hiker.display_name
        profile.bio = hiker.bio
        profile.home_province = hiker.province
        profile.avatar_path = _avatar(store, user_id, avatar_image(hiker.username, hiker.colours))
        settings = ensure_settings(db, user_id)
        settings.is_private = False
        settings.share_activity = True
        settings.show_journal = settings.show_rank = settings.show_gear = settings.show_saved_trails = True
        settings.show_trip_plans = True
        settings.show_home_province = True
        settings.hide_hike_dates = False
        # Not in "Hiked by" on trail pages, not in search engines.
        settings.show_in_community = False
        settings.allow_search_indexing = False
        settings.visibility_chosen_at = datetime.now(timezone.utc)
        _finished_onboarding(db, user_id, hiker.experience, hiker.style)
        db.commit()

        hikes = 0
        for hike in sorted(hiker.hikes, key=lambda h: -h.days_ago):
            trail = find_trail(db, hike.trail, hike.province)
            if trail is None:
                log(f"{hiker.username}: no trail {hike.trail} ({hike.province}), skipped")
                continue
            day = today - timedelta(days=hike.days_ago)
            before = standing(db, user_id) if hike.share else None
            entry = HikeLog(user_id=user_id, trail_id=trail.id, hiked_on=day, note=hike.note, nights=hike.nights,
                            created_at=_evening(day))
            db.add(entry)
            db.commit()
            after_hike_saved(db, user_id, entry, hike.share, before, today)
            # Posted the evening of the hike, so the feed reads in order.
            for post in db.scalars(select(ActivityPost).where(ActivityPost.hike_log_id == entry.id)):
                bump = {"hike": 0, "milestone": 1, "rank": 2}[post.kind]
                post.created_at = _evening(day) + timedelta(microseconds=bump)
            db.commit()
            hikes += 1

        for name, province in hiker.saved:
            trail = find_trail(db, name, province)
            if trail is not None:
                db.add(SavedTrail(user_id=user_id, trail_id=trail.id))
        if hiker.plan:
            name, province, days_ahead, nights, title = hiker.plan
            trail = find_trail(db, name, province)
            if trail is not None:
                db.add(TripPlan(user_id=user_id, trail_id=trail.id, title=title,
                                start_date=today + timedelta(days=days_ahead), nights=nights, party_size=2))
        gear = _gear(db, user_id, hiker.gear, index)
        db.commit()
        _featured(db, user_id)
        db.commit()
        log(f"{hiker.username}: {hikes} hikes, {gear} gear items")

    _demo_high_fives(db)
    return made


def _demo_high_fives(db: Session) -> None:
    """Demo hikers high-five each other's posts (only each other's)."""
    ids = demo_ids(db)
    posts = db.scalars(select(ActivityPost).where(ActivityPost.user_id.in_(ids))).all() if ids else []
    for n, post in enumerate(posts):
        for m, fan in enumerate(ids):
            # Not everyone high-fives everything (with only two, they always do).
            if fan == post.user_id or (len(ids) > 2 and (n + m) % 3 == 0):
                continue
            if db.get(ActivityReaction, (post.id, fan)) is None:
                db.add(ActivityReaction(post_id=post.id, user_id=fan, created_at=post.created_at + timedelta(hours=1 + m)))
    db.commit()


def _user_columns():
    for table in Base.metadata.sorted_tables:
        if table.name in KEPT_TABLES:
            continue
        for column in table.columns:
            if not isinstance(column.type, Uuid):
                continue
            if column.name in USER_COLUMNS or (table.name == "profiles" and column.name == "id"):
                yield table, column


def references(db: Session, ids: list[UUID]) -> dict[str, int]:
    """How many rows in each table still name one of these users."""
    found: dict[str, int] = {}
    if not ids:
        return found
    for table, column in _user_columns():
        count = db.scalar(select(func.count()).select_from(table).where(column.in_(ids))) or 0
        if count:
            found[f"{table.name}.{column.name}"] = count
    return found


def sweep(db: Session, ids: list[UUID]) -> None:
    """Deletes every row naming these users, children first. Posts go with
    their reactions (real users' high fives on demo posts too)."""
    if not ids:
        return
    posts = select(ActivityPost.id).where(ActivityPost.user_id.in_(ids))
    db.execute(delete(ActivityReaction).where(ActivityReaction.post_id.in_(posts)))
    for table, column in sorted(_user_columns(), key=lambda tc: Base.metadata.sorted_tables.index(tc[0]),
                                reverse=True):
        db.execute(delete(table).where(column.in_(ids)))
    db.commit()


def remove_demo(db: Session, auth: AuthAdmin, store: AvatarStore | None,
                log: Callable[[str], None] = lambda _m: None) -> list[UUID]:
    """Removes every demo account and everything that names it."""
    ids = demo_ids(db)
    avatars = [p for p in db.scalars(select(Profile.avatar_path).where(Profile.id.in_(ids))) if p] if ids else []
    sweep(db, ids)
    if store is not None and avatars:
        store.delete(avatars)
    for user_id in ids:
        auth.delete_user(user_id)
    left = references(db, ids)
    if left:
        raise RuntimeError(f"Rows still name demo accounts: {left}")
    log(f"removed {len(ids)} demo accounts")
    return ids
