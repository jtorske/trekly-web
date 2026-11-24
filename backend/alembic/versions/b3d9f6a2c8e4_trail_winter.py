"""trails: winter activities, avalanche exposure (ATES) and winter notes

- winter_activities: jsonb array of winter_hike / snowshoe / xc_ski; empty
  (the default) means not recommended in winter.
- avalanche_exposure: Avalanche Terrain Exposure Scale class, one of none /
  simple / challenging / complex / unknown. Default 'unknown'; any other
  value, 'none' included, must carry avalanche_source_url (the official
  rating), so a missing rating can never read as "no avalanche terrain".
- winter_access_note, winter_notes: short text (road closures, ice).
- winter_route_ends: when only part of the trail is a winter route, where
  it ends (the summer distance and gain then don't apply in winter). Only
  with winter activities.
- winter_source_url: where the winter activities came from; required when
  there are any.

Schema only: the values come from catalog_data/trail_winter.json through
scripts/trail_winter.py sync-db. Public read like the other trail columns.

Revision ID: b3d9f6a2c8e4
Revises: a6e3c9f2d8b4
Create Date: 2026-11-23 12:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b3d9f6a2c8e4"
down_revision: Union[str, Sequence[str], None] = "a6e3c9f2d8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE public.trails
          ADD COLUMN winter_activities jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN avalanche_exposure text NOT NULL DEFAULT 'unknown',
          ADD COLUMN avalanche_source_url text,
          ADD COLUMN winter_access_note text,
          ADD COLUMN winter_notes text,
          ADD COLUMN winter_route_ends text,
          ADD COLUMN winter_source_url text,
          ADD CONSTRAINT trails_winter_activities_check CHECK (
            jsonb_typeof(winter_activities) = 'array'
            AND winter_activities <@ '["winter_hike","snowshoe","xc_ski"]'::jsonb),
          ADD CONSTRAINT trails_avalanche_exposure_check CHECK (
            avalanche_exposure IN ('none','simple','challenging','complex','unknown')),
          ADD CONSTRAINT trails_avalanche_source_check CHECK (
            avalanche_exposure = 'unknown' OR avalanche_source_url IS NOT NULL),
          ADD CONSTRAINT trails_winter_source_check CHECK (
            winter_activities = '[]'::jsonb OR winter_source_url IS NOT NULL),
          ADD CONSTRAINT trails_winter_route_ends_check CHECK (
            winter_route_ends IS NULL OR winter_activities <> '[]'::jsonb)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE public.trails
          DROP COLUMN IF EXISTS winter_source_url,
          DROP COLUMN IF EXISTS winter_route_ends,
          DROP COLUMN IF EXISTS winter_notes,
          DROP COLUMN IF EXISTS winter_access_note,
          DROP COLUMN IF EXISTS avalanche_source_url,
          DROP COLUMN IF EXISTS avalanche_exposure,
          DROP COLUMN IF EXISTS winter_activities
    """)
