"""add trail ↔ campground links and trail booking systems

trail_campgrounds links trails to backcountry_sites in route order, and
trail_booking_systems records which reservation system(s) book each trail's
camping (for "Booked through BC Parks" notes). Both are seeded from
catalog_data/trail_campgrounds.json by scripts/seed_trail_campgrounds.py.
FKs are RESTRICT: trails and sites are retired, never deleted.

The DDL was generated from app/models/trail_campground.py when this migration
was written and is frozen here on purpose.

Security model (same as the backcountry catalogue): RLS on, public read-only
policies and no write policies, so only the backend/seed role (which bypasses
RLS) writes. A link to a site the provider doesn't publish is hidden along
with the site. Everything is revoked before SELECT is granted back, because
Supabase's default privileges grant all on new public tables and RLS doesn't
cover TRUNCATE.

Revision ID: f1afb297138e
Revises: 9a769eeb0dae
Create Date: 2026-10-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1afb297138e"
down_revision: Union[str, Sequence[str], None] = "9a769eeb0dae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["trail_campgrounds", "trail_booking_systems"]

CREATE_TABLES = [
    """
    CREATE TABLE public.trail_campgrounds (
    	trail_id UUID NOT NULL,
    	site_id UUID NOT NULL,
    	route_order INTEGER NOT NULL,
    	stop_name TEXT,
    	notes TEXT,
    	confidence TEXT NOT NULL,
    	source TEXT NOT NULL,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (trail_id, site_id),
    	CONSTRAINT trail_campgrounds_route_order_check CHECK (route_order >= 1),
    	CONSTRAINT trail_campgrounds_confidence_check CHECK (confidence in ('exact','likely')),
    	FOREIGN KEY(trail_id) REFERENCES public.trails (id) ON DELETE RESTRICT,
    	FOREIGN KEY(site_id) REFERENCES public.backcountry_sites (id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX trail_campgrounds_site_idx ON public.trail_campgrounds (site_id)",
    """
    CREATE TABLE public.trail_booking_systems (
    	trail_id UUID NOT NULL,
    	system TEXT NOT NULL,
    	covers TEXT NOT NULL,
    	confirmed BOOLEAN NOT NULL DEFAULT true,
    	note TEXT,
    	position INTEGER NOT NULL DEFAULT 0,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (trail_id, system),
    	CONSTRAINT trail_booking_systems_covers_check CHECK (covers in ('all','partial')),
    	FOREIGN KEY(trail_id) REFERENCES public.trails (id) ON DELETE RESTRICT
    )
    """,
]


def upgrade() -> None:
    for statement in CREATE_TABLES:
        op.execute(statement)

    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")
        op.execute(f"GRANT SELECT ON public.{table} TO anon, authenticated")

    op.execute(
        'CREATE POLICY "trail_campgrounds_public_read" ON public.trail_campgrounds '
        "FOR SELECT TO anon, authenticated USING ("
        "EXISTS (SELECT 1 FROM public.backcountry_sites s WHERE s.id = site_id AND s.is_publicly_listed))"
    )
    op.execute(
        'CREATE POLICY "trail_booking_systems_public_read" ON public.trail_booking_systems '
        "FOR SELECT TO anon, authenticated USING (true)"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
