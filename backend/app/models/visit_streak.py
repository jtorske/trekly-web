"""Each user's visit streak (rules in app/streaks.py).

One row per user: the date of their last visit and two counts. No visit
history and no time zone are kept. Only the API writes it (POST
/api/me/visit); clients have no grants on the table at all (migration
f9c2d4e6a8b1), so the counts can't be set from the browser.
"""

from sqlalchemy import CheckConstraint, Column, Date, Integer, Uuid

from app.database import Base


class VisitStreak(Base):
    __tablename__ = "visit_streaks"
    __table_args__ = (
        CheckConstraint("current_streak >= 1", name="visit_streaks_current_check"),
        CheckConstraint("longest_streak >= current_streak", name="visit_streaks_longest_check"),
    )

    # Same value as auth.users.id; the FK to auth.users is added in the migration.
    user_id = Column(Uuid, primary_key=True)
    current_streak = Column(Integer, nullable=False)
    longest_streak = Column(Integer, nullable=False)
    last_visit_date = Column(Date, nullable=False)
