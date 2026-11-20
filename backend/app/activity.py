"""The Activity feed's rules: when a post is made, and who sees it.

Posting (only from real activity, see app/models/activity.py):
- Saving a hike in the journal dialog with "Share to Activity" ticked
  posts it, along with any milestone or rank that hike earned. Unticking
  it later makes its post owner-only and marks the hike unshared.
- Every other hike gets an owner-only post when its owner next opens their
  profile's Activity tab (backfill_posts): hikes logged while sharing was
  off, onboarding picks and "Add past hikes". So the owner always sees all
  their hikes there, but nobody else sees one they never shared, whatever
  their settings. The posts are dated when the hike was and carry the
  milestones and ranks it earned, found by replaying the journal.
- The owner may share that backlog once, from the "Share your past hikes?"
  prompt (share_past_hikes); hikes they unshared stay owner-only.
- Deleting a hike's post marks the hike unshared: it's gone from their
  Activity tab for good, unless they tick "Share to Activity" again.
- Planning and gear milestones are never posted: they'd say something
  about trip plans, alerts or gear rather than a hike.

Reading: a post shows while all of these hold (row-level security has the
same rule, private.activity_post_visible, last in migration e3c7a9d5f1b2):
- it isn't owner-only;
- the owner has a username, isn't hidden by an admin, isn't private, and
  has "Share my activity in the feed" on;
- a hike or milestone post: their Trail Journal is shown; a rank post:
  their rank is shown;
- a seasonal milestone: they don't hide their hike dates;
- a hike post: the hike isn't dated in the future (a browser can edit its
  own hike_logs row, so this is checked on every read);
- no admin has hidden the post;
- an announcement: its author is the official @trekly account
  (app/account_labels.py); nobody else's would ever show.
Nothing is cached, so turning a setting off hides the posts at once.

The owner also sees their own posts while others can't (sharing turned off
later, say), marked "only you" by the API, so the page can say so. Admin-hidden
posts and future-dated hikes stay hidden from them too.

A milestone or rank earned by a hike folds into that hike's post (its
`earned` list) whenever the reader can see the hike post; it stands alone
only when they can't, e.g. after the hike post was deleted or unshared.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload

from app.account_labels import is_label
from app.milestone_dates import facts_on, other_dates
from app.milestones import Facts, earned_ids, gather, hike_fact
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
    return seen.public and seen.shows("journal") and bool(seen.settings.share_activity)


# ------------------------------------------------------------------ posting


@dataclass(frozen=True)
class Standing:
    """What a user has earned, to tell what a hike just added."""

    milestones: frozenset[str]
    rank_level: int


def standing(db: Session, user_id: UUID) -> Standing:
    return _standing(gather(db, user_id))


def standing_from(facts: Facts) -> Standing:
    return _standing(facts)


def _standing(facts: Facts) -> Standing:
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
    log.unshared = not share
    if not share:
        # Off the feed, still in the owner's own Activity tab.
        if existing is None:
            db.add(ActivityPost(user_id=user_id, kind="hike", hike_log_id=log.id, created_at=_posted_at(log),
                                owner_only=True))
        else:
            existing.owner_only = True
        db.commit()
        return
    if not can_share(db, user_id) or _future(log, today):
        # An owner-only post comes later, from backfill_posts.
        db.commit()
        return
    now = _now()
    if existing is None:
        db.add(ActivityPost(user_id=user_id, kind="hike", hike_log_id=log.id, created_at=now))
    elif existing.owner_only:
        # Sharing a hike that only its owner saw shares what it earned too.
        for post in db.scalars(select(ActivityPost).where(
            ActivityPost.user_id == user_id, ActivityPost.hike_log_id == log.id, ActivityPost.owner_only,
        )):
            post.owner_only = False
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


def after_hike_edited(db: Session, user_id: UUID, log: HikeLog, before: Standing) -> None:
    """Keeps a posted hike's badges true after its date changed: what the new
    date earns is posted with it (as shared as the hike's post is), and
    milestones or ranks the journal no longer earns lose their posts. Nothing
    for a hike that was never posted."""
    post = hike_post(db, log.id)
    if post is None:
        return
    after = standing(db, user_id)
    lost = before.milestones - after.milestones
    if lost:
        for stale in db.scalars(select(ActivityPost).where(
            ActivityPost.user_id == user_id, ActivityPost.kind == "milestone", ActivityPost.milestone.in_(lost),
        )):
            db.delete(stale)
    for stale in db.scalars(select(ActivityPost).where(
        ActivityPost.user_id == user_id, ActivityPost.kind == "rank", ActivityPost.rank_level > after.rank_level,
    )):
        db.delete(stale)
    db.flush()
    # Folded into the hike's post, right after it.
    when = post.created_at
    for milestone_id in sorted(after.milestones - before.milestones):
        milestone = MILESTONES.get(milestone_id)
        if milestone is None or milestone.category in UNPOSTED_CATEGORIES:
            continue
        if _has(db, ActivityPost.user_id == user_id, ActivityPost.kind == "milestone",
                ActivityPost.milestone == milestone_id):
            continue
        db.add(ActivityPost(
            user_id=user_id, kind="milestone", hike_log_id=log.id, milestone=milestone_id,
            reveals_date=milestone.category == "seasons", created_at=when + timedelta(microseconds=1),
            owner_only=post.owner_only,
        ))
    if after.rank_level > before.rank_level and not _has(
        db, ActivityPost.user_id == user_id, ActivityPost.kind == "rank", ActivityPost.rank_level == after.rank_level
    ):
        db.add(ActivityPost(user_id=user_id, kind="rank", hike_log_id=log.id, rank_level=after.rank_level,
                            created_at=when + timedelta(microseconds=2), owner_only=post.owner_only))
    db.commit()


def _future(log: HikeLog, today: date) -> bool:
    return log.hiked_on is not None and log.hiked_on > today + FUTURE_SLACK


def _hike_day(log: HikeLog) -> date:
    return log.hiked_on or log.created_at.date()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _posted_at(log: HikeLog) -> datetime:
    """A backfilled hike post's time: the evening of the hike (as the demo
    accounts' are), but never after it was logged; an undated past hike, when
    it was logged."""
    logged = _aware(log.created_at)
    if log.hiked_on is None:
        return logged
    return min(datetime.combine(log.hiked_on, time(19, 30), tzinfo=timezone.utc), logged)


def unposted_hikes(user_id: UUID, today: date):
    """Their hikes that backfill_posts would post: no post, not unshared, not future-dated."""
    return select(HikeLog.id).where(
        HikeLog.user_id == user_id,
        ~HikeLog.unshared,
        or_(HikeLog.hiked_on.is_(None), HikeLog.hiked_on <= today + FUTURE_SLACK),
        ~exists().where(ActivityPost.kind == "hike", ActivityPost.hike_log_id == HikeLog.id),
    )


def backfill_posts(db: Session, user_id: UUID, today: date) -> int:
    """Give every hike of theirs that has no post and wasn't unshared an
    owner-only post, with the milestones and ranks it earned (owner-only too),
    as if each had been posted when it was hiked. Returns how many hikes it
    posted; cheap once there are none.

    The journal is replayed in hike order (undated past hikes first, as they
    were logged): the facts as they stood on each hike's day, with only the
    hikes up to it, tell what that hike added. A milestone or rank that
    already has a post isn't posted again."""
    todo = set(db.scalars(unposted_hikes(user_id, today)))
    if not todo:
        return 0
    facts = gather(db, user_id)
    others = other_dates(db, user_id)
    logs = sorted(
        db.scalars(select(HikeLog).where(HikeLog.user_id == user_id).options(joinedload(HikeLog.trail))).all(),
        # Undated past hikes came before any dated one.
        key=lambda log: (log.hiked_on or date.min, _aware(log.created_at), log.id),
    )
    posted_milestones = set(db.scalars(select(ActivityPost.milestone).where(
        ActivityPost.user_id == user_id, ActivityPost.kind == "milestone")))
    posted_ranks = set(db.scalars(select(ActivityPost.rank_level).where(
        ActivityPost.user_id == user_id, ActivityPost.kind == "rank")))

    def upto(count: int, day: date) -> Standing:
        return _standing(replace(facts_on(facts, day, **others), hikes=[hike_fact(log) for log in logs[:count]]))

    posted = 0
    for index, log in enumerate(logs):
        if log.id not in todo:
            continue
        day = _hike_day(log)
        before, after = upto(index, day), upto(index + 1, day)
        when = _posted_at(log)
        db.add(ActivityPost(user_id=user_id, kind="hike", hike_log_id=log.id, created_at=when, owner_only=True))
        for milestone_id in sorted(after.milestones - before.milestones - posted_milestones):
            milestone = MILESTONES.get(milestone_id)
            if milestone is None or milestone.category in UNPOSTED_CATEGORIES:
                continue
            posted_milestones.add(milestone_id)
            db.add(ActivityPost(
                user_id=user_id, kind="milestone", hike_log_id=log.id, milestone=milestone_id,
                reveals_date=milestone.category == "seasons", created_at=when + timedelta(microseconds=1),
                owner_only=True,
            ))
        if after.rank_level > before.rank_level and after.rank_level not in posted_ranks:
            posted_ranks.add(after.rank_level)
            db.add(ActivityPost(user_id=user_id, kind="rank", hike_log_id=log.id, rank_level=after.rank_level,
                                created_at=when + timedelta(microseconds=2), owner_only=True))
        posted += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # a concurrent request posted them first
        return 0
    return posted


def _past_hike_posts(user_id: UUID):
    """Their owner-only posts the "Share your past hikes?" prompt would share:
    all but those of hikes they unshared."""
    return select(ActivityPost).where(
        ActivityPost.user_id == user_id,
        ActivityPost.owner_only,
        ~exists().where(HikeLog.id == ActivityPost.hike_log_id, HikeLog.unshared),
    )


def past_hikes_waiting(db: Session, user_id: UUID) -> int:
    """How many hikes the prompt would share."""
    return len(db.scalars(_past_hike_posts(user_id).where(ActivityPost.kind == "hike")).all())


def share_past_hikes(db: Session, user_id: UUID) -> int:
    """Shares their past hikes (the prompt's yes); returns how many hikes."""
    posts = db.scalars(_past_hike_posts(user_id)).all()
    for post in posts:
        post.owner_only = False
    db.commit()
    return sum(1 for post in posts if post.kind == "hike")


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
        ~ActivityPost.owner_only,
        Profile.username.is_not(None),
        ~settings.is_private,
        settings.share_activity,
        ~exists().where(ProfileModeration.user_id == ActivityPost.user_id),
        case(
            (ActivityPost.kind == "rank", settings.show_rank),
            # Only the official account's announcements ever show.
            (ActivityPost.kind == "announcement", is_label(ActivityPost.user_id, "official")),
            else_=settings.show_journal,
        ),
        or_(~ActivityPost.reveals_date, ~settings.hide_hike_dates),
        _not_future(today),
    )


def readable_where(today: date, viewer_id: UUID | None):
    """visible_where, plus the viewer's own posts that only they can see,
    including ones held or hidden by moderation (shown to them with a
    "being reviewed" or "removed" note; app/moderation.py)."""
    if viewer_id is None:
        return visible_where(today)
    return or_(
        visible_where(today),
        and_(ActivityPost.user_id == viewer_id, _not_future(today)),
    )


def folded_where(today: date, viewer_id: UUID | None):
    """A milestone or rank post this reader sees inside its hike's post instead.
    The hike post shares the author (so their settings) and the hike log, so it's
    readable when it isn't admin-hidden, the journal shows and it isn't
    owner-only (or it's the reader's own), and the hike isn't future-dated."""
    hike = aliased(ActivityPost)
    journal = ProfileSettings.show_journal
    # The owner still sees their own held or hidden hike post, and their own
    # owner-only one, so its badges stay folded into it.
    shown = hike.hidden_at.is_(None)
    shared = ~hike.owner_only
    if viewer_id is not None:
        journal = or_(journal, ActivityPost.user_id == viewer_id)
        shown = or_(shown, hike.user_id == viewer_id)
        shared = or_(shared, hike.user_id == viewer_id)
    return and_(
        ActivityPost.kind != "hike",
        ActivityPost.hike_log_id.is_not(None),
        exists().where(hike.kind == "hike", hike.hike_log_id == ActivityPost.hike_log_id, shown, shared),
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


def activity_open(seen: Visibility) -> bool:
    """Whether visitors get a profile's Activity tab: the profile is public
    (approved followers will count too once follows exist) and its owner
    shares their activity. Each post on it still follows visible_where."""
    return seen.public and seen.settings is not None and bool(seen.settings.share_activity)
