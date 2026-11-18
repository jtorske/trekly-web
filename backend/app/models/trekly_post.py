"""Automatic @trekly posts: generated drafts, their review, and the fact bank.

The daily run (scripts/trekly_posts.py, app/trekly_posts/) turns real
catalogue and activity data into drafts. Nothing reaches the Activity feed
until an admin approves it on /admin/trekly-posts, unless that post type's
auto-publish toggle is on (off for every type by default). Publishing makes an
ordinary "announcement" ActivityPost from the official account.

- trekly_post_drafts: one row per generated post. `dedupe_key` is unique, so
  running the generator twice never makes a second draft for the same thing.
  `data` keeps the facts the post was written from, and `writer` says whether
  the text came from the template or the Claude API (which is only kept when it
  passed the fact check in app/trekly_posts/writer.py).
- trekly_post_type_settings: the per-type auto-publish toggle. Which types run
  and when lives in config/trekly_posts.toml.
- trekly_facts: the curated fact bank. Only approved facts are ever posted,
  each with its source link.

Only the API (admins) and the daily run touch these tables; clients have no
access at all (migration d7a2f9c4e6b1).
"""

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Text, Uuid, false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from app.database import Base

POST_TYPES = ("trending", "spotlight", "new_on_trekly", "roundup", "fun_fact", "conditions")
DRAFT_STATUSES = ("draft", "scheduled", "published", "rejected", "expired")
WRITERS = ("template", "ai", "admin")
MAX_FACT_TEXT = 400
MAX_SOURCE_URL = 500

JsonColumn = JSON().with_variant(JSONB(), "postgresql")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class TreklyPostDraft(Base):
    __tablename__ = "trekly_post_drafts"
    __table_args__ = (
        CheckConstraint(f"post_type in ({_in(POST_TYPES)})", name="trekly_post_drafts_type_check"),
        CheckConstraint(f"status in ({_in(DRAFT_STATUSES)})", name="trekly_post_drafts_status_check"),
        CheckConstraint(f"writer in ({_in(WRITERS)})", name="trekly_post_drafts_writer_check"),
        CheckConstraint("length(body) between 1 and 500", name="trekly_post_drafts_body_length_check"),
        CheckConstraint("status <> 'scheduled' or publish_on is not null", name="trekly_post_drafts_schedule_check"),
        # Deleting the published post clears post_id (SET NULL) but keeps published_at.
        CheckConstraint("status <> 'published' or post_id is not null or published_at is not null",
                        name="trekly_post_drafts_published_check"),
        Index("trekly_post_drafts_dedupe_key", "dedupe_key", unique=True),
        Index("trekly_post_drafts_status_idx", "status", "created_at"),
        Index("trekly_post_drafts_trail_idx", "trail_id", "created_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    post_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")
    # e.g. "trending:2026-W47", "new_trail:<id>", "conditions:<bulletin url>".
    dedupe_key = Column(Text, nullable=False)
    # The local date of the run that made it.
    run_date = Column(Date, nullable=False)
    body = Column(Text, nullable=False)
    # The template's text, kept so an AI or edited version can be compared.
    template_body = Column(Text, nullable=False)
    writer = Column(Text, nullable=False, default="template")
    # Why the AI text wasn't used, when it was tried.
    ai_note = Column(Text)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="SET NULL"))
    fact_id = Column(Uuid, ForeignKey("trekly_facts.id", ondelete="SET NULL"))
    source_url = Column(Text)
    source_label = Column(Text)
    source_date = Column(Date)
    # The facts the post was written from.
    data = Column(JsonColumn, nullable=False, default=dict)
    # Set when an admin schedules it; the daily run publishes it that day.
    publish_on = Column(Date)
    post_id = Column(Uuid, ForeignKey("activity_posts.id", ondelete="SET NULL"))
    published_at = Column(DateTime(timezone=True))
    decided_by = Column(Uuid)
    decided_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trail = relationship("Trail")
    fact = relationship("TreklyFact")


class TreklyPostTypeSetting(Base):
    __tablename__ = "trekly_post_type_settings"
    __table_args__ = (
        CheckConstraint(f"post_type in ({_in(POST_TYPES)})", name="trekly_post_type_settings_type_check"),
    )

    post_type = Column(Text, primary_key=True)
    auto_publish = Column(Boolean, nullable=False, default=False, server_default=false())
    updated_by = Column(Uuid)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TreklyFact(Base):
    __tablename__ = "trekly_facts"
    __table_args__ = (
        CheckConstraint(f"length(text) between 1 and {MAX_FACT_TEXT}", name="trekly_facts_text_length_check"),
        CheckConstraint(
            f"length(source_url) between 1 and {MAX_SOURCE_URL} and source_url like 'https://%'",
            name="trekly_facts_source_url_check",
        ),
        Index("trekly_facts_seed_key", "seed_key", unique=True),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    text = Column(Text, nullable=False)
    trail_id = Column(Uuid, ForeignKey("trails.id", ondelete="SET NULL"))
    park_name = Column(Text)
    source_url = Column(Text, nullable=False)
    approved = Column(Boolean, nullable=False, default=False, server_default=false())
    # Set for facts loaded by the seed script, so reseeding never duplicates them.
    seed_key = Column(Text)
    updated_by = Column(Uuid)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trail = relationship("Trail")
