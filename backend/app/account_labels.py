"""The rules for labeled accounts: the official @trekly account and demo hikers.

- Every author the API returns carries its label ("official" / "demo" / None),
  and the frontend shows the "Trekly team" or "Demo account" badge for it.
- Demo hikers exist so the app can be explored with real-looking data, never
  to pose as real people. They:
  * never interact with real users: they can't high-five (comment on, follow)
    anyone but another demo account (`may_interact`), whoever asks;
  * aren't counted anywhere numbers stand for real people: admin stats,
    trending trails, "Trekly picks" sparseness, "Hiked by" on trail pages
    (`real_user`);
  * never show in people search or "Hikers you might know" (`real_user`
    again; the social features must apply it to every people listing).
  Real users can still open their profiles and high-five their posts.
- The official account posts announcements (admins write them through
  /api/admin/official-posts) and, like demo accounts, isn't a hiker in stats.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.orm import Session

from app.models.account_label import AccountLabel

OFFICIAL_USERNAME = "trekly"
AccountLabelName = Literal["official", "demo"]


def label_of(db: Session, user_id: UUID | None) -> str | None:
    if user_id is None:
        return None
    row = db.get(AccountLabel, user_id)
    return row.label if row else None


def labels_for(db: Session, user_ids) -> dict[UUID, str]:
    ids = list({uid for uid in user_ids if uid is not None})
    if not ids:
        return {}
    return dict(db.execute(select(AccountLabel.user_id, AccountLabel.label).where(AccountLabel.user_id.in_(ids))).all())


def is_demo(db: Session, user_id: UUID | None) -> bool:
    return label_of(db, user_id) == "demo"


def real_user(user_id: ColumnElement) -> ColumnElement[bool]:
    """SQL: this user is an ordinary hiker (neither official nor demo)."""
    return ~exists().where(AccountLabel.user_id == user_id)


def is_label(user_id: ColumnElement, label: str) -> ColumnElement[bool]:
    return exists().where(AccountLabel.user_id == user_id, AccountLabel.label == label)


def may_interact(db: Session, actor_id: UUID, target_owner_id: UUID) -> bool:
    """Whether `actor` may high-five (comment on, follow) something of
    `target_owner`'s. Anyone may reach a demo account; a demo account reaches
    only other demo accounts."""
    if not is_demo(db, actor_id):
        return True
    return is_demo(db, target_owner_id)


def official_id(db: Session) -> UUID | None:
    return db.scalar(select(AccountLabel.user_id).where(AccountLabel.label == "official"))
