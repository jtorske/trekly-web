"""The Activity feed's rules: when a post is made, and who sees it.

Posting (only from real activity, see app/models/activity.py):
- Saving a hike in the journal dialog with "Share to Activity" ticked
  posts it, along with any milestone or rank that hike earned. Unticking
  it later removes the hike's post. Undated past hikes added in bulk
  (onboarding, "Add past hikes") never post, and nothing posts while the
  owner can't share (see can_share), so a post never waits, unseen, to
  appear when a setting changes.
- Planning and gear milestones are never posted: they'd say something
  about trip plans, alerts or gear rather than a hike.

Reading: a post shows while all of these hold (row-level security has the
same rule, private.activity_post_visible in migration a8c3f1d5e7b2):
- the owner has a username, isn't hidden by an admin, isn't private, and
  has "Share my activity in the feed" on;
- a hike or milestone post: their Trail Journal is shown; a rank post:
  their rank is shown;
- a seasonal milestone: they don't hide their hike dates;
- a hike post: the hike isn't dated in the future (a browser can edit its
  own hike_logs row, so this is checked on every read);
- no admin has hidden the post.
Nothing is cached, so turning a setting off hides the posts at once.

The owner also sees their own posts while others can't (sharing turned off
later, say), marked "only you" by the API, so the page can say so. Admin-hidden
posts and future-dated hikes stay hidden from them too.

A milestone or rank earned by a hike folds into that hike's post (its
`earned` list) whenever the reader can see the hike post; it stands alone
only when they can't, e.g. after the hike post was deleted or unshared.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, exists, false, or_, select
from sqlalchemy.orm import Session, aliased

from app.milestones import earned_ids, gather
from app.milestones_config import ACTIVE
from app.models.account import Profile
from app.models.activity import ActivityPost
from app.models.hike_log import HikeLog
from app.models.privacy import ProfileModeration, ProfileSettings
from app.points import rank_for, score
from app.privacy import Visibility, visibility

# A hike dated up to a day ahead is allowed (time zones), as in app/routers/me_hike_logs.py.
FUTURE_SLACK = timedelta(days=1)
# Milestone categories that never post: they're about plans, alerts and gear.
UNPOSTED_CATEGORIES = {"planning", "gear"}
MILESTONES = {milestone.id: milestone for milestone in ACTIVE}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def can_share(db: Session, user_id: UUID) -> bool:
    """Whether a new post of theirs would show (ignoring admin post hides)."""
    profile = db.get(Profile, user_id)
    if profile is None:
        return False
    seen = visibility(db, profile)
    return seen.shows("journal") and bool(seen.settings.share_activity)


# ------------------------------------------------------------------ posting


@dataclass(frozen=True)
class Standing:
    """What a user has earned, to tell what a hike just added."""

    milestones: frozenset[str]
    rank_level: int


def standing(db: Session, user_id: UUID) -> Standing:
    facts = gather(db, user_id)
    return Standing(milestones=frozenset(earned_ids(facts)), rank_level=rank_for(score(facts).total).level)


def _has(db: Session, *where) -> bool:
    return db.scalar(select(exists().where(*where))) or False


def hike_post(db: Session, log_id: UUID) -> ActivityPost | None:
    return db.scalar(select(ActivityPost).where(ActivityPost.kind == "hike", ActivityPost.hike_log_id == log_id))


def after_hike_saved(
    db: Session, user_id: UUID, log: HikeLog, share: bool | None, before: Standing | None, today: date
) -> None:
    """Post (or unpost) a hike that was just saved. `share` None leaves things as they are.
    `before` is the standing from before the save, when share is True."""
    if share is None:
        return
    existing = hike_post(db, log.id)
    if not share:
        if existing is not None:
            db.delete(existing)
            db.commit()
        return
    if not can_share(db, user_id):
        return
    if log.hiked_on is not None and log.hiked_on > today + FUTURE_SLACK:
        return
    now = _now()
    if existing is None:
        db.add(ActivityPost(user_id=user_id, kind="hike", hike_log_id=log.id, created_at=now))
    if before is not None:
        after = standing(db, user_id)
        # Milestones first, then the rank, a moment later, so the rank leads the feed.
        for milestone_id in sorted(after.milestones - before.milestones):
            milestone = MILESTONES.get(milestone_id)
            if milestone is None or milestone.category in UNPOSTED_CATEGORIES:
                continue
            if _has(db, ActivityPost.user_id == user_id, ActivityPost.kind == "milestone",
                    ActivityPost.milestone == milestone_id):
                continue
            db.add(ActivityPost(
                user_id=user_id, kind="milestone", hike_log_id=log.id, milestone=milestone_id,
                reveals_date=milestone.category == "seasons", created_at=now + timedelta(microseconds=1),
            ))
        if after.rank_level > before.rank_level and not _has(
            db, ActivityPost.user_id == user_id, ActivityPost.kind == "rank", ActivityPost.rank_level == after.rank_level
        ):
            db.add(ActivityPost(user_id=user_id, kind="rank", hike_log_id=log.id, rank_level=after.rank_level,
                                created_at=now + timedelta(microseconds=2)))
    db.commit()


# ------------------------------------------------------------------ reading


def _not_future(today: date):
    return or_(
        ActivityPost.kind != "hike",
        HikeLog.hiked_on.is_(None),
        HikeLog.hiked_on <= today + FUTURE_SLACK,
    )


def visible_where(today: date):
    """The read rule as SQL, for a query joining ActivityPost, Profile,
    ProfileSettings and (outer) HikeLog on the post's hike."""
    settings = ProfileSettings
    return and_(
        ActivityPost.hidden_at.is_(None),
        Profile.username.is_not(None),
        ~settings.is_private,
        settings.share_activity,
        ~exists().where(ProfileModeration.user_id == ActivityPost.user_id),
        case((ActivityPost.kind == "rank", settings.show_rank), else_=settings.show_journal),
        or_(~ActivityPost.reveals_date, ~settings.hide_hike_dates),
        _not_future(today),
    )


def readable_where(today: date, viewer_id: UUID | None):
    """visible_where, plus the viewer's own posts that only they can see."""
    if viewer_id is None:
        return visible_where(today)
    return or_(
        visible_where(today),
        and_(ActivityPost.user_id == viewer_id, ActivityPost.hidden_at.is_(None), _not_future(today)),
    )


def folded_where(today: date, viewer_id: UUID | None):
    """A milestone or rank post this reader sees inside its hike's post instead.
    The hike post shares the author (so their settings) and the hike log, so it's
    readable when it isn't admin-hidden, the journal shows (or it's the reader's
    own), and the hike isn't future-dated."""
    hike = aliased(ActivityPost)
    journal = ProfileSettings.show_journal
    if viewer_id is not None:
        journal = or_(journal, ActivityPost.user_id == viewer_id)
    return and_(
        ActivityPost.kind != "hike",
        ActivityPost.hike_log_id.is_not(None),
        exists().where(hike.kind == "hike", hike.hike_log_id == ActivityPost.hike_log_id, hike.hidden_at.is_(None)),
        journal,
        or_(HikeLog.hiked_on.is_(None), HikeLog.hiked_on <= today + FUTURE_SLACK),
    )


def _joined(*columns):
    return (
        select(ActivityPost, Profile, ProfileSettings, HikeLog, *columns)
        .join(Profile, Profile.id == ActivityPost.user_id)
        .join(ProfileSettings, ProfileSettings.user_id == ActivityPost.user_id)
        .outerjoin(HikeLog, HikeLog.id == ActivityPost.hike_log_id)
    )


def visible_query(today: date):
    """Rows of (post, author profile, author settings, hike log or None) that may show."""
    return _joined().where(visible_where(today))


def readable_query(today: date, viewer_id: UUID | None):
    """visible_query plus the viewer's own posts, with a last column saying
    whether everyone can see the post (False: only the viewer can)."""
    return _joined(visible_where(today).label("public")).where(readable_where(today, viewer_id))


def is_visible(db: Session, post_id: UUID, today: date) -> bool:
    return db.scalar(select(exists(visible_query(today).where(ActivityPost.id == post_id)))) or False


def province_where(province: str | None):
    """Authors from this province who show it on their profile; nothing without one."""
    if not province:
        return false()
    return and_(Profile.home_province == province, ProfileSettings.show_home_province)


def activity_open(seen: Visibility) -> bool:
    """Whether visitors get a profile's Activity tab: the profile is public
    (approved followers will count too once follows exist) and its owner
    shares their activity. Each post on it still follows visible_where."""
    return seen.public and seen.settings is not None and bool(seen.settings.share_activity)
