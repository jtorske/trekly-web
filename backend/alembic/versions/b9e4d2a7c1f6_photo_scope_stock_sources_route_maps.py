"""trail photos: stock sources, a scope for the credit line, and route maps

- trail_photos.source also allows 'pixabay' and 'pexels' (stock libraries
  whose licences allow commercial use and editing; still credited).
- trail_photos.scope: what the approved photo shows, copied from the
  candidate's confidence when it's approved: 'trail' (the trail or a
  landmark on it), 'nearby' (within 3 km of the route) or 'park' (the park,
  not this trail). A 'park' photo's credit says so. Existing photos are
  backfilled from their candidate's confidence (old 'low'/'off_topic' are
  park-level); the owner's own uploads stay null (shown as the trail).
- trail_photo_candidates.best_confidence also allows 'park'.
- trail_route_maps: a generated image of the trail's stored route on the
  topo style (scripts/route_maps.py), shown instead of the plain topo
  fallback when a trail has no photo. Public read like trail_photos; only
  the backend writes. Files live in the trail-photos bucket at
  `{trail_id}/route-map-{hash}-hero.webp` / `-thumb.webp`.

Revision ID: b9e4d2a7c1f6
Revises: f4a9c2e7b1d3
Create Date: 2026-11-10 15:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b9e4d2a7c1f6"
down_revision: Union[str, Sequence[str], None] = "f4a9c2e7b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROUTE_MAP_NAME = r"^[0-9a-f-]{36}/route-map-[0-9a-f]{12}-(hero|thumb)\.webp$"


def upgrade() -> None:
    op.execute("ALTER TABLE public.trail_photos DROP CONSTRAINT trail_photos_source_check")
    op.execute(
        "ALTER TABLE public.trail_photos ADD CONSTRAINT trail_photos_source_check "
        "CHECK (source IN ('commons', 'openverse', 'pixabay', 'pexels', 'owner'))"
    )
    op.execute(
        "ALTER TABLE public.trail_photos ADD COLUMN scope text "
        "CHECK (scope IS NULL OR scope IN ('trail', 'nearby', 'park'))"
    )
    # The approved candidate's confidence, where its search result is still stored.
    op.execute(
        """
        UPDATE public.trail_photos p
        SET scope = CASE c.value->>'confidence'
                WHEN 'high' THEN 'trail'
                WHEN 'medium' THEN 'nearby'
                ELSE 'park'
            END
        FROM public.trail_photo_candidates pc, jsonb_array_elements(pc.candidates) c
        WHERE pc.trail_id = p.trail_id
          AND p.source <> 'owner'
          AND c.value->>'id' = p.candidate_id
        """
    )

    op.execute(
        "ALTER TABLE public.trail_photo_candidates "
        "DROP CONSTRAINT trail_photo_candidates_best_confidence_check"
    )
    op.execute(
        "ALTER TABLE public.trail_photo_candidates ADD CONSTRAINT trail_photo_candidates_best_confidence_check "
        "CHECK (best_confidence IS NULL OR best_confidence IN ('high', 'medium', 'park', 'low', 'off_topic'))"
    )

    op.execute(
        """
        CREATE TABLE public.trail_route_maps (
            trail_id uuid PRIMARY KEY REFERENCES public.trails (id) ON DELETE RESTRICT,
            hero_path text NOT NULL CHECK (hero_path ~ '{NAME}'),
            thumb_path text NOT NULL CHECK (thumb_path ~ '{NAME}'),
            hero_width integer NOT NULL CHECK (hero_width > 0),
            hero_height integer NOT NULL CHECK (hero_height > 0),
            -- Hash of the route and drawing settings: unchanged means no redraw.
            route_hash text NOT NULL CHECK (route_hash ~ '^[0-9a-f]{12}$'),
            generated_at timestamptz NOT NULL DEFAULT now()
        )
        """.replace("{NAME}", ROUTE_MAP_NAME)
    )
    op.execute("ALTER TABLE public.trail_route_maps ENABLE ROW LEVEL SECURITY")
    op.execute(
        'CREATE POLICY "trail_route_maps_select_all" ON public.trail_route_maps '
        "FOR SELECT TO anon, authenticated USING (true)"
    )
    op.execute("REVOKE ALL ON public.trail_route_maps FROM anon, authenticated")
    op.execute("GRANT SELECT ON public.trail_route_maps TO anon, authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.trail_route_maps")
    op.execute(
        "ALTER TABLE public.trail_photo_candidates "
        "DROP CONSTRAINT trail_photo_candidates_best_confidence_check"
    )
    op.execute(
        "ALTER TABLE public.trail_photo_candidates ADD CONSTRAINT trail_photo_candidates_best_confidence_check "
        "CHECK (best_confidence IS NULL OR best_confidence IN ('high', 'medium', 'low', 'off_topic'))"
    )
    op.execute("ALTER TABLE public.trail_photos DROP COLUMN scope")
    op.execute("ALTER TABLE public.trail_photos DROP CONSTRAINT trail_photos_source_check")
    op.execute(
        "ALTER TABLE public.trail_photos ADD CONSTRAINT trail_photos_source_check "
        "CHECK (source IN ('commons', 'openverse', 'owner'))"
    )
