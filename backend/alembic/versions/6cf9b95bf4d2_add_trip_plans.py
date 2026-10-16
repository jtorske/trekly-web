"""add trip plans

- trip_plans: a user's plan for one trail (start date, nights, party size,
  optional gear setup, title and notes). user_id references auth.users and
  cascades, so deleting an account deletes its plans. Deleting a setup keeps
  the plan (setup_id set null); trails can't be deleted out from under one.
- trip_plan_nights: one row per night (campground / undecided / outside),
  the user's "booked by me" flag and the last availability check of that
  night.

Owners can read their own plans and nights. All writes go through the API,
which checks that each campground is on the plan's trail and that the setup
is the user's own, so there are no write policies (as for alerts).

The DDL was generated from app/models/trip_plan.py when this migration was
written and is frozen here on purpose.

Revision ID: 6cf9b95bf4d2
Revises: bcc7f8e1333b
Create Date: 2026-10-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6cf9b95bf4d2"
down_revision: Union[str, Sequence[str], None] = "bcc7f8e1333b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE = [
    """
    CREATE TABLE public.trip_plans (
    	id UUID NOT NULL DEFAULT gen_random_uuid(),
    	user_id UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    	trail_id UUID NOT NULL,
    	setup_id UUID,
    	title TEXT,
    	start_date DATE NOT NULL,
    	nights INTEGER NOT NULL,
    	party_size INTEGER NOT NULL,
    	notes TEXT,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (id),
    	CONSTRAINT trip_plans_nights_check CHECK (nights between 1 and 14),
    	CONSTRAINT trip_plans_party_check CHECK (party_size between 1 and 12),
    	CONSTRAINT trip_plans_title_length_check CHECK (title is null or length(title) <= 80),
    	CONSTRAINT trip_plans_notes_length_check CHECK (notes is null or length(notes) <= 2000),
    	FOREIGN KEY(trail_id) REFERENCES public.trails (id) ON DELETE RESTRICT,
    	FOREIGN KEY(setup_id) REFERENCES public.gear_setups (id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX ix_trip_plans_user_id ON public.trip_plans (user_id)",
    """
    CREATE TABLE public.trip_plan_nights (
    	trip_plan_id UUID NOT NULL,
    	night_index INTEGER NOT NULL,
    	choice TEXT NOT NULL DEFAULT 'undecided',
    	site_id UUID,
    	booked_by_me BOOLEAN NOT NULL DEFAULT false,
    	last_status TEXT,
    	last_checked_at TIMESTAMP WITH TIME ZONE,
    	PRIMARY KEY (trip_plan_id, night_index),
    	CONSTRAINT trip_plan_nights_index_check CHECK (night_index between 0 and 13),
    	CONSTRAINT trip_plan_nights_choice_check CHECK (choice in ('campground','undecided','outside')),
    	CONSTRAINT trip_plan_nights_site_check CHECK ((choice = 'campground') = (site_id is not null)),
    	CONSTRAINT trip_plan_nights_last_status_check CHECK (last_status is null or last_status in ('available','full','closed','not_released','unknown')),
    	FOREIGN KEY(trip_plan_id) REFERENCES public.trip_plans (id) ON DELETE CASCADE,
    	FOREIGN KEY(site_id) REFERENCES public.backcountry_sites (id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX ix_trip_plan_nights_site_id ON public.trip_plan_nights (site_id)",
]


def upgrade() -> None:
    for statement in CREATE:
        op.execute(statement)

    for table in ("trip_plans", "trip_plan_nights"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")
        op.execute(f"GRANT SELECT ON public.{table} TO authenticated")

    op.execute(
        'CREATE POLICY "trip_plans_select_own" ON public.trip_plans '
        "FOR SELECT TO authenticated USING (user_id = (select auth.uid()))"
    )
    op.execute(
        'CREATE POLICY "trip_plan_nights_select_own" ON public.trip_plan_nights '
        "FOR SELECT TO authenticated USING (exists ("
        "select 1 from public.trip_plans p "
        "where p.id = trip_plan_id and p.user_id = (select auth.uid())))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.trip_plan_nights")
    op.execute("DROP TABLE IF EXISTS public.trip_plans")
