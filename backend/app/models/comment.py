"""Comments on Activity posts (migration f2c8a4e6b1d9).

Plain text, up to MAX_COMMENT characters, with one level of replies: a
reply's parent is always a top-level comment (app/comments.py attaches a
reply to a reply to that reply's parent). Deleting a post deletes its
comments, deleting a comment deletes its replies, and deleting an account
deletes the comments it wrote (ON DELETE CASCADE all round).

`body` is null while moderation withholds it (app/moderation.py moves it to
the comment's moderation item): only its author sees it then, as "Being
reviewed". Who sees a comment is decided on every read (app/comments.py);
the table is closed to clients (RLS on, no grants), so only the API reads
and writes it.
"""

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.sql import func

from app.database import Base

MAX_COMMENT = 500


class ActivityComment(Base):
    __tablename__ = "activity_comments"
    __table_args__ = (
        CheckConstraint(f"body is null or length(body) between 1 and {MAX_COMMENT}",
                        name="activity_comments_body_length_check"),
        CheckConstraint("parent_id is null or parent_id <> id", name="activity_comments_not_own_parent_check"),
        Index("activity_comments_post_idx", "post_id", "created_at"),
        Index("activity_comments_user_idx", "user_id", "created_at"),
        Index("activity_comments_parent_idx", "parent_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("activity_posts.id", ondelete="CASCADE"), nullable=False)
    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, nullable=False)
    # A reply: the top-level comment it's under.
    parent_id = Column(Uuid, ForeignKey("activity_comments.id", ondelete="CASCADE"))
    body = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Set when its author changes the text.
    edited_at = Column(DateTime(timezone=True))
