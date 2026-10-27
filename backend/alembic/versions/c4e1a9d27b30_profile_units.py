"""profile display units

profiles.units holds the account's display units for the whole app:
'metric' or 'imperial'. Null means the user never chose, which the app reads
as metric. Data is always stored in metric; this only changes display.

Users who picked imperial before this setting existed picked it per browser
(localStorage). The app copies that choice up the first time it sees a
signed-in profile with no setting, so it isn't backfilled here.

The column isn't added to any client column grants: the app reads and
writes it through the API only.

Revision ID: c4e1a9d27b30
Revises: dfc16ffa2de3
Create Date: 2026-10-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4e1a9d27b30"
down_revision: Union[str, Sequence[str], None] = "dfc16ffa2de3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent, so it's safe on a database that already has the column.
    op.execute("ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS units text")
    op.execute("ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_units_check")
    op.execute(
        """
        ALTER TABLE public.profiles
        ADD CONSTRAINT profiles_units_check
        CHECK (units IS NULL OR units IN ('metric', 'imperial'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_units_check")
    op.execute("ALTER TABLE public.profiles DROP COLUMN IF EXISTS units")
