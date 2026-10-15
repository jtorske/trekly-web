"""baseline: trails table (created in Supabase before Alembic)

Matches the live public.trails table exactly as inspected on 2026-10-15
(columns, types, defaults, CHECK, RLS and its public-read policy). Every
statement is guarded, so on the existing database this is a no-op; on a fresh
database it creates the table the later migrations reference.

Inserted as the new root below 2cacb5e7696d. Databases already at a later
revision treat it as applied and never run it.

Revision ID: 0a9b8c7d6e5f
Revises:
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0a9b8c7d6e5f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.trails (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            region text NOT NULL,
            latitude numeric(9, 6),
            longitude numeric(9, 6),
            elevation_gain_m integer,
            max_elevation_m integer,
            terrain_difficulty text NOT NULL,
            typical_duration_nights integer,
            climate_zone text,
            description text,
            created_at timestamptz DEFAULT now(),
            CONSTRAINT trails_terrain_difficulty_check
                CHECK (terrain_difficulty = ANY (ARRAY['easy', 'moderate', 'difficult', 'extreme']))
        )
        """
    )
    op.execute("ALTER TABLE public.trails ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'trails'
                  AND policyname = 'Trails are publicly readable'
            ) THEN
                CREATE POLICY "Trails are publicly readable" ON public.trails
                    FOR SELECT TO public USING (true);
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    # The table predates Alembic and holds the trail catalogue; a downgrade
    # past the baseline deliberately leaves it in place.
    pass
