"""one active availability alert per user, campground and stay

The API checks for a duplicate before inserting, but simultaneous requests
all passed that check and created identical active alerts (beta bug B-004).
A partial unique index now enforces the rule in the database; the API also
takes a per-user advisory lock so the active-alert cap holds under the same
race.

Existing duplicates are resolved first: the oldest active alert in each group
is kept and the rest are cancelled, so no alert is deleted.

Revision ID: f3a4b5c6d7e8
Revises: e7f8a9b0c1d2
Create Date: 2026-10-24 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE public.availability_alerts AS alert
        SET status = 'cancelled', cancelled_at = now(), updated_at = now()
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY user_id, site_id, start_date, nights
                ORDER BY created_at, id
            ) AS position
            FROM public.availability_alerts
            WHERE status = 'active'
        ) AS ranked
        WHERE alert.id = ranked.id AND ranked.position > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX availability_alerts_active_unique "
        "ON public.availability_alerts (user_id, site_id, start_date, nights) "
        "WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.availability_alerts_active_unique")
