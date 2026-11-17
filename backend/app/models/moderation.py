"""Content moderation: one row per piece of user content under watch, and
account restrictions (suspensions and locks).

A ModerationItem is a piece of content an automated check or a report has
something to say about: an Activity post, a hike's note or photo, a bio, a
profile photo, a whole profile (when a profile itself is reported), or a
comment. It's keyed by (kind, target_id), so one item follows its content
through edits, and it's the admin moderation queue (/admin/moderation)
while `in_queue` is set.

Withheld content lives here, not in the content's own column. While an item
is "held" (pending review) or "hidden" (an admin decided), the note, bio or
photo path is moved out of hike_logs / profiles into `text` / `photo_path`,
so nothing that reads those columns (the API, row-level security, the
photo-visibility function behind signed URLs) can show it to anyone else.
The author's own views overlay it back with "Your post is being reviewed"
(app/moderation.py). Approving puts it back; nothing is ever deleted here.
An Activity post itself is held through activity_posts.hidden_at instead.

Neither table is readable by clients (RLS on, no grants); only the API
writes them.
"""

import uuid

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, DateTime, Index, Integer, Text, UniqueConstraint, Uuid, false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import text as sql_text
from sqlalchemy.sql import func

from app.database import Base

ITEM_KINDS = ("post", "hike_note", "hike_photo", "bio", "avatar", "profile", "comment")
# visible: in its column, shown as usual. held: withheld pending review.
# hidden: withheld by an admin's decision.
ITEM_STATES = ("visible", "held", "hidden")
# Why it's in the queue.
QUEUE_REASONS = ("flagged", "unscreened", "reported", "child_safety", "edited_after_hide")
SCREENINGS = ("passed", "flagged", "unavailable")
DECISIONS = ("approved", "hidden")
MAX_DECISION_REASON = 500

_JSON = JSON().with_variant(JSONB(), "postgresql")


def _in(name: str, values: tuple[str, ...]) -> str:
    return f"{name} in (" + ", ".join(f"'{v}'" for v in values) + ")"


class ModerationItem(Base):
    __tablename__ = "moderation_items"
    __table_args__ = (
        UniqueConstraint("kind", "target_id", name="moderation_items_target_key"),
        CheckConstraint(_in("kind", ITEM_KINDS), name="moderation_items_kind_check"),
        CheckConstraint(_in("state", ITEM_STATES), name="moderation_items_state_check"),
        CheckConstraint(
            "queue_reason is null or " + _in("queue_reason", QUEUE_REASONS), name="moderation_items_queue_reason_check"
        ),
        CheckConstraint(
            "screening is null or " + _in("screening", SCREENINGS), name="moderation_items_screening_check"
        ),
        CheckConstraint("decision is null or " + _in("decision", DECISIONS), name="moderation_items_decision_check"),
        CheckConstraint(
            f"decision_reason is null or length(decision_reason) <= {MAX_DECISION_REASON}",
            name="moderation_items_decision_reason_length_check",
        ),
        Index("moderation_items_queue_idx", "in_queue", "activity_at"),
        Index("moderation_items_author_idx", "author_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    kind = Column(Text, nullable=False)
    # The post, hike log, comment or user (bio, avatar, profile) it's about.
    target_id = Column(Uuid, nullable=False)
    author_id = Column(Uuid, nullable=False)
    state = Column(Text, nullable=False, default="visible", server_default="visible")
    in_queue = Column(Boolean, nullable=False, default=False, server_default=false())
    queue_reason = Column(Text)
    # What was screened or reported. While held or hidden, the withheld value
    # itself (its column is empty): a note, bio or comment, or a photo path.
    text = Column(Text)
    photo_path = Column(Text)
    # A copy of a child-safety photo in the private moderation-quarantine
    # bucket, where the author can't delete it.
    quarantine_path = Column(Text)
    # The automated check: its verdict, every category score, and the
    # categories it flagged (OpenAI's moderation API).
    screening = Column(Text)
    scores = Column(_JSON)
    flagged_categories = Column(_JSON)
    screened_at = Column(DateTime(timezone=True))
    screening_model = Column(Text)
    child_safety = Column(Boolean, nullable=False, default=False, server_default=false())
    # Distinct reporters on open reports whose report counts toward the
    # auto-hide (confirmed email, account old enough, not blocked), and all of them.
    qualifying_reports = Column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    open_reports = Column(Integer, nullable=False, default=0, server_default=sql_text("0"))
    last_reported_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # When it last needed attention (held, edited, reported): the queue's order.
    activity_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decision = Column(Text)
    decision_reason = Column(Text)
    decided_at = Column(DateTime(timezone=True))
    decided_by = Column(Uuid)
    # Mentioned in an admin digest email (app/moderation_emails.py).
    digest_sent_at = Column(DateTime(timezone=True))


class AccountRestriction(Base):
    """An account an admin suspended, or that was locked (child-safety flag
    or a ban). The API refuses new content while one is in force; Supabase's
    own ban stops sign-ins (app/supabase_admin.py)."""

    __tablename__ = "account_restrictions"
    __table_args__ = (
        CheckConstraint("lock_reason is null or length(lock_reason) <= 500", name="account_restrictions_reason_check"),
    )

    # Same value as auth.users.id; no FK, so the record outlives a deleted account.
    user_id = Column(Uuid, primary_key=True)
    suspended_until = Column(DateTime(timezone=True))
    locked_at = Column(DateTime(timezone=True))
    lock_reason = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
