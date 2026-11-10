"""Nudges toward the two community settings, "Share my activity in the feed"
(share_activity) and "Show me in community features" (show_in_community).

Both settings stay off until the user turns them on themselves; a nudge
only offers the switch. Each nudge shows only while:

- the setting it points at is off,
- turning it on would take effect (a public profile with a username, not
  hidden by an admin, the Trail Journal shown: Visibility.shows("journal")),
- and the user hasn't put it away. Tapping ✕, deciding once in the Mark as
  hiked dialog, or turning the setting on (anywhere, through the privacy
  API) puts it away for good, on every device.

    hike_share     Mark as hiked dialog, under "Share to Activity"
    activity_card  the card at the top of the Activity feed
    hiked_by       the line in "Hiked by" on trails they've hiked
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Profile
from app.models.nudge import NUDGES, NudgeDismissal
from app.privacy import visibility

# The setting each nudge points at.
SETTING = {"hike_share": "share_activity", "activity_card": "share_activity", "hiked_by": "show_in_community"}
assert set(SETTING) == set(NUDGES)


def dismissed(db: Session, user_id: UUID) -> set[str]:
    return set(db.scalars(select(NudgeDismissal.nudge).where(NudgeDismissal.user_id == user_id)))


def dismiss(db: Session, user_id: UUID, *nudges: str) -> None:
    """Puts nudges away for good. Repeats change nothing. Doesn't commit."""
    already = dismissed(db, user_id)
    for nudge in nudges:
        if nudge not in already:
            db.add(NudgeDismissal(user_id=user_id, nudge=nudge))
            already.add(nudge)


def dismiss_for_settings(db: Session, user_id: UUID, turned_on: set[str]) -> None:
    """A setting turned on puts away every nudge pointing at it."""
    dismiss(db, user_id, *(nudge for nudge in NUDGES if SETTING[nudge] in turned_on))


def active(db: Session, user_id: UUID) -> list[str]:
    """The nudges this user may see now, in NUDGES order."""
    profile = db.get(Profile, user_id)
    if profile is None:
        return []
    seen = visibility(db, profile)
    if not seen.shows("journal"):
        return []
    put_away = dismissed(db, user_id)
    return [n for n in NUDGES if n not in put_away and not getattr(seen.settings, SETTING[n])]


def commit_quietly(db: Session) -> None:
    """Two tabs dismissing the same nudge at once: the second insert loses, harmlessly."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
