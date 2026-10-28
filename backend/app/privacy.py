"""Who may see which part of a profile: the API's copy of the database rule.

Row-level security (private.section_visible, migration 214aa07bf743) guards
direct Supabase access; this guards the API, which connects as postgres and
so bypasses RLS. Both use the same rows and the same rule:

    a section is visible to visitors when the owner has a username, isn't
    hidden by an admin, isn't private, and has that section switched on.

Community features ("Hiked by" on trail pages) count as one more section:
the Trail Journal switch and "Show me in community features" must both be
on (migration 9d4f2a6c8e13).

Missing settings count as private. Nothing here is cached, so a change to a
setting applies to the very next request.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Profile
from app.models.privacy import SECTION_COLUMNS, ProfileModeration, ProfileSettings


@dataclass(frozen=True)
class Visibility:
    listed: bool
    """The profile exists for visitors at all (has a username, not hidden)."""
    public: bool
    """Listed and not private: bio and the switched-on sections show."""
    settings: ProfileSettings | None

    def shows(self, section: str) -> bool:
        if not self.public or self.settings is None:
            return False
        return bool(getattr(self.settings, SECTION_COLUMNS[section]))

    @property
    def hide_dates(self) -> bool:
        # Fail closed: without settings, never show dates.
        return self.settings is None or bool(self.settings.hide_hike_dates)

    @property
    def indexable(self) -> bool:
        return self.public and bool(self.settings.allow_search_indexing)

    @property
    def in_community(self) -> bool:
        return self.shows("journal") and bool(self.settings.show_in_community)


def visibility(db: Session, profile: Profile) -> Visibility:
    hidden = db.get(ProfileModeration, profile.id) is not None
    listed = profile.username is not None and not hidden
    settings = db.get(ProfileSettings, profile.id)
    public = listed and settings is not None and not settings.is_private
    return Visibility(listed=listed, public=public, settings=settings)


def in_community(user_id: ColumnElement) -> ColumnElement[bool]:
    """SQL for Visibility.in_community, for listing many users at once."""
    return exists(
        select(Profile.id)
        .join(ProfileSettings, ProfileSettings.user_id == Profile.id)
        .where(
            Profile.id == user_id,
            Profile.username.is_not(None),
            ~ProfileSettings.is_private,
            and_(ProfileSettings.show_journal, ProfileSettings.show_in_community),
            ~exists().where(ProfileModeration.user_id == Profile.id),
        )
    )


def ensure_settings(db: Session, user_id: UUID) -> ProfileSettings:
    """The signup trigger creates settings; this self-heals a missing row with
    the new-user defaults (the only users without one are new)."""
    settings = db.get(ProfileSettings, user_id)
    if settings is not None:
        return settings
    db.add(ProfileSettings(user_id=user_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # created concurrently by the trigger or another request
    return db.get(ProfileSettings, user_id)
