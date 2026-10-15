"""add backcountry campground / zone catalogue

backcountry_parks and backcountry_sites hold the backcountry campgrounds,
zones, shelters and trail permits synced from reservation providers by
scripts/sync_backcountry.py (Parks Canada for now; `provider` leaves room for
BC Parks / Alberta Parks / Ontario Parks). Provider IDs are stored verbatim
next to our UUIDs; sites that disappear are retired (retired_at), never
deleted, so a later trail_campgrounds(trail_id, site_id) link table can point
at backcountry_sites.id safely. The trails table is not touched.

The DDL was generated from app/models/backcountry.py when this migration was
written and is frozen here on purpose.

Security model (same as the gear catalogue): RLS on, public read-only
policies and no write policies, so only the backend/sync role (which bypasses
RLS) writes. Sites the provider doesn't publish (is_publicly_listed = false)
are hidden from anon/authenticated. Supabase's default privileges grant every
privilege on new public tables to anon/authenticated, and RLS doesn't cover
TRUNCATE, so everything is revoked before SELECT is granted back.

Revision ID: f270bc5e799a
Revises: b8c9d0e1f2a3
Create Date: 2026-10-15 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f270bc5e799a"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["backcountry_parks", "backcountry_sites"]

CREATE_TABLES = [
    """
    CREATE TABLE public.backcountry_parks (
    	id UUID NOT NULL DEFAULT gen_random_uuid(),
    	provider TEXT NOT NULL,
    	provider_park_id TEXT NOT NULL,
    	name TEXT NOT NULL,
    	province_code TEXT,
    	region TEXT,
    	last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL,
    	retired_at TIMESTAMP WITH TIME ZONE,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (id),
    	CONSTRAINT backcountry_parks_provider_park_key UNIQUE (provider, provider_park_id),
    	CONSTRAINT backcountry_parks_province_code_check CHECK (province_code is null or length(province_code) = 2)
    )
    """,
    """
    CREATE TABLE public.backcountry_sites (
    	id UUID NOT NULL DEFAULT gen_random_uuid(),
    	provider TEXT NOT NULL,
    	provider_resource_id TEXT NOT NULL,
    	provider_location_id TEXT NOT NULL,
    	provider_map_id TEXT,
    	provider_category_id TEXT,
    	provider_booking_category_id TEXT,
    	resource_model INTEGER,
    	park_id UUID,
    	province_code TEXT,
    	booking_unit TEXT NOT NULL,
    	area TEXT,
    	name TEXT NOT NULL,
    	raw_name TEXT NOT NULL,
    	site_code TEXT,
    	kind TEXT NOT NULL,
    	reservable_capacity INTEGER,
    	max_capacity INTEGER,
    	max_group_size INTEGER,
    	latitude NUMERIC(9, 6),
    	longitude NUMERIC(9, 6),
    	is_publicly_listed BOOLEAN NOT NULL DEFAULT true,
    	description TEXT,
    	raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    	last_synced_at TIMESTAMP WITH TIME ZONE NOT NULL,
    	retired_at TIMESTAMP WITH TIME ZONE,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (id),
    	CONSTRAINT backcountry_sites_provider_resource_key UNIQUE (provider, provider_resource_id),
    	CONSTRAINT backcountry_sites_kind_check CHECK (kind in ('zone','site','shelter','cabin','yurt','random_zone','horse_camp','backpacking_campground','trail_permit','other')),
    	CONSTRAINT backcountry_sites_province_code_check CHECK (province_code is null or length(province_code) = 2),
    	CONSTRAINT backcountry_sites_latitude_check CHECK (latitude is null or (latitude between -90 and 90)),
    	CONSTRAINT backcountry_sites_longitude_check CHECK (longitude is null or (longitude between -180 and 180)),
    	FOREIGN KEY(park_id) REFERENCES public.backcountry_parks (id) ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX backcountry_sites_park_idx ON public.backcountry_sites (park_id)",
]


def upgrade() -> None:
    for statement in CREATE_TABLES:
        op.execute(statement)

    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")
        op.execute(f"GRANT SELECT ON public.{table} TO anon, authenticated")

    op.execute(
        'CREATE POLICY "backcountry_parks_public_read" ON public.backcountry_parks '
        "FOR SELECT TO anon, authenticated USING (true)"
    )
    op.execute(
        'CREATE POLICY "backcountry_sites_public_read" ON public.backcountry_sites '
        "FOR SELECT TO anon, authenticated USING (is_publicly_listed)"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
