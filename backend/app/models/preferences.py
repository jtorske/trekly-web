"""Private trail preferences and /welcome progress, one row per user.

Never shown to visitors: the API returns them only to their owner, and
row-level security (migration 6d1a8f3b2c57) lets a signed-in client read
only its own row and nobody write. A missing row means nothing answered yet
and the setup flow not finished.
"""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Text, Uuid
from sqlalchemy.sql import false, func, true

from app.database import Base
from app.models.catalog import JsonType


class ProfilePreferences(Base):
    __tablename__ = "profile_preferences"
    __table_args__ = (
        CheckConstraint(
            "hiking_style is null or hiking_style in ('day', 'overnight', 'both')",
            name="profile_preferences_hiking_style_check",
        ),
        CheckConstraint(
            "experience is null or experience in ('new', 'few_seasons', 'seasoned')",
            name="profile_preferences_experience_check",
        ),
        CheckConstraint(
            "onboarding_status is null or onboarding_status in ('completed', 'skipped')",
            name="profile_preferences_onboarding_status_check",
        ),
        CheckConstraint(
            "season_mode is null or season_mode in ('summer', 'winter')",
            name="profile_preferences_season_mode_check",
        ),
    )

    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, primary_key=True)
    hiking_style = Column(Text)
    experience = Column(Text)
    # Unused since the interests step was removed (migration c7e3a9f1d5b2); kept for now.
    interests = Column(JsonType, nullable=False, default=list, server_default="[]")
    favourite_regions = Column(JsonType, nullable=False, default=list, server_default="[]")
    # Trekly Guide (migration e1a7c4b9d2f6). "Use my history to personalize
    # Trekly Guide": off means the Guide ignores their hikes, saved trails and
    # gear and works from what they enter in the planner alone.
    guide_use_history = Column(Boolean, nullable=False, default=True, server_default=true())
    # "I usually hike with a dog": the planner's dog question starts on yes.
    hikes_with_dog = Column(Boolean, nullable=False, default=False, server_default=false())
    # Scenery they like (app/guide/estimate.py SCENERY_KEYS); nudges the ranking only.
    scenery = Column(JsonType, nullable=False, default=list, server_default="[]")
    # Explore's Summer / Winter toggle (migration f3b8d2a6c4e1): null follows
    # the season (app/season.py); 'summer' or 'winter' is their own choice.
    season_mode = Column(Text)
    # The /welcome screen to resume at (ONBOARDING_STEPS).
    onboarding_step = Column(Text)
    # Null until they finish ("completed") or leave with "Skip for now" ("skipped").
    onboarding_status = Column(Text)
    onboarding_finished_at = Column(DateTime(timezone=True))
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
