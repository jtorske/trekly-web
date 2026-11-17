"""hiker search: findable private profiles, blocks, search + suggestion functions

- unaccent (with pg_trgm, already there) in the extensions schema, and
  private.search_fold(text): lower-case, accents removed. It's IMMUTABLE so
  it can be indexed; GIN trigram indexes on the folded username and display
  name serve prefix, substring and fuzzy matches.
- profile_settings.findable_in_search ("Let people find me in search"): off
  by default. Public profiles are always searchable; a private one appears
  only with it on, and then only with its name, username and photo.
- blocks: one row per (blocker, blocked). Only the API writes it; a client
  reads only the rows where it's the blocker, so nobody can learn who has
  blocked them. Search and suggestions leave out blocks in either direction.
- private.search_hikers(viewer, q, max_rows, skip) and
  private.suggest_hikers(viewer, max_rows): every matching, ranking and
  visibility rule for people search and "Hikers you might know", in one
  place. Executable by the API's role only (no client grant, not SECURITY
  DEFINER), so nobody can call them with someone else's id.

Who appears: a listed profile (has a username, not hidden by an admin) that
isn't a labeled account (official or demo), isn't the viewer and isn't
blocked either way; public, or private with findable_in_search on.

Ranking: exact username, then people the viewer follows, then people with
trails or home province in common, then the rest; best match first in each.
"In common" uses only what the viewer may see: trails count when the other
person's Trail Journal is visible to the viewer, and the province when they
show it. So ranking never reveals a hidden section.

Revision ID: e6b2d8a4c0f7
Revises: d7a2f9c4e6b1
Create Date: 2026-11-10 18:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e6b2d8a4c0f7"
down_revision: Union[str, Sequence[str], None] = "d7a2f9c4e6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
# Fuzzy matches (typos) need this much of the query's trigrams in one word.
WORD_SIMILARITY = "0.5"

# The other person as the viewer sees them: "opened" is public, or the
# viewer is an approved follower (app/privacy.py, private.section_visible).
SEEN = """
    SELECT
        p.id,
        p.username,
        p.display_name,
        p.home_province,
        s.is_private,
        (NOT s.is_private OR EXISTS (
            SELECT 1 FROM public.follows f
            WHERE f.follower_id = viewer AND f.followee_id = p.id AND f.status = 'accepted'
        )) AS opened,
        s.show_journal,
        s.show_home_province,
        s.show_in_community,
        s.findable_in_search
    FROM public.profiles p
    JOIN public.profile_settings s ON s.user_id = p.id
    WHERE p.username IS NOT NULL
      AND p.id <> viewer
      AND NOT EXISTS (SELECT 1 FROM public.profile_moderation m WHERE m.user_id = p.id)
      AND NOT EXISTS (SELECT 1 FROM public.account_labels l WHERE l.user_id = p.id)
      AND NOT EXISTS (
          SELECT 1 FROM public.blocks b
          WHERE (b.blocker_id = viewer AND b.blocked_id = p.id)
             OR (b.blocker_id = p.id AND b.blocked_id = viewer)
      )
"""

# Trails both have hiked (today or before), counted only when the other
# person's journal is visible to the viewer.
COMMON_TRAILS = """
    CASE WHEN c.opened AND c.show_journal THEN (
        SELECT count(DISTINCT theirs.trail_id)::int
        FROM public.hike_logs theirs
        JOIN public.hike_logs mine ON mine.trail_id = theirs.trail_id AND mine.user_id = viewer
        WHERE theirs.user_id = c.id
          AND (theirs.hiked_on IS NULL OR theirs.hiked_on <= current_date)
          AND (mine.hiked_on IS NULL OR mine.hiked_on <= current_date)
    ) END
"""

# Same home province, when they show theirs. "Outside Canada" isn't a place in common.
SAME_PROVINCE = """
    (c.opened AND c.show_home_province AND c.home_province IS NOT NULL AND c.home_province <> 'outside'
     AND c.home_province = (SELECT v.home_province FROM public.profiles v WHERE v.id = viewer))
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions")

    op.execute(
        """
        CREATE FUNCTION private.search_fold(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        SET search_path = ''
        AS $$ SELECT lower(extensions.unaccent('extensions.unaccent'::regdictionary, value)) $$
        """
    )
    # Executable by everyone (the default): client profile updates evaluate the indexes.
    op.execute(
        "CREATE INDEX profiles_username_search_idx ON public.profiles "
        "USING gin (private.search_fold(username) extensions.gin_trgm_ops) WHERE username IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX profiles_display_name_search_idx ON public.profiles "
        "USING gin (private.search_fold(display_name) extensions.gin_trgm_ops) WHERE username IS NOT NULL"
    )

    op.execute(
        "ALTER TABLE public.profile_settings ADD COLUMN findable_in_search boolean NOT NULL DEFAULT false"
    )
    # Clients already SELECT the whole table (their own row, by policy).
    op.execute("GRANT UPDATE (findable_in_search) ON public.profile_settings TO authenticated")

    op.execute(
        """
        CREATE TABLE public.blocks (
            blocker_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            blocked_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT blocks_pkey PRIMARY KEY (blocker_id, blocked_id),
            CONSTRAINT blocks_not_self_check CHECK (blocker_id <> blocked_id)
        )
        """
    )
    op.execute("CREATE INDEX blocks_blocked_idx ON public.blocks (blocked_id)")
    op.execute("ALTER TABLE public.blocks ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.blocks FROM {CLIENTS}")
    op.execute("GRANT SELECT (blocker_id, blocked_id, created_at) ON public.blocks TO authenticated")
    op.execute(
        'CREATE POLICY "blocks_select_own" ON public.blocks FOR SELECT TO authenticated '
        "USING (blocker_id = (SELECT auth.uid()))"
    )

    op.execute(
        f"""
        CREATE FUNCTION private.search_hikers(viewer uuid, q text, max_rows integer, skip integer)
        RETURNS TABLE (user_id uuid, tier integer, score real, common_trails integer, opened boolean)
        LANGUAGE sql
        STABLE
        SET search_path = ''
        SET pg_trgm.word_similarity_threshold = {WORD_SIMILARITY}
        AS $$
            WITH term AS (
                SELECT t, replace(replace(replace(t, '\\', '\\\\'), '%', '\\%'), '_', '\\_') AS esc
                FROM (SELECT private.search_fold(btrim(ltrim(btrim(q), '@'))) AS t) folded
            ),
            seen AS ({SEEN}),
            matched AS (
                SELECT
                    c.*,
                    private.search_fold(c.username) AS fu,
                    coalesce(private.search_fold(c.display_name), '') AS fn,
                    term.t,
                    term.esc
                FROM seen c, term
                WHERE length(term.t) >= 2
                  AND (NOT c.is_private OR c.findable_in_search)
                  AND (
                      private.search_fold(c.username) LIKE '%' || term.esc || '%'
                      OR private.search_fold(c.display_name) LIKE '%' || term.esc || '%'
                      OR (length(term.t) >= 3 AND (
                          term.t OPERATOR(extensions.<%) private.search_fold(c.username)
                          OR term.t OPERATOR(extensions.<%) private.search_fold(c.display_name)
                      ))
                  )
            ),
            scored AS (
                SELECT
                    c.id,
                    c.username,
                    c.opened,
                    c.fu = c.t AS exact,
                    EXISTS (
                        SELECT 1 FROM public.follows f
                        WHERE f.follower_id = viewer AND f.followee_id = c.id AND f.status = 'accepted'
                    ) AS followed,
                    {COMMON_TRAILS} AS common_trails,
                    {SAME_PROVINCE} AS same_province,
                    greatest(
                        CASE WHEN c.fu LIKE c.esc || '%' THEN 1.0 ELSE 0 END,
                        CASE WHEN c.fn LIKE c.esc || '%' OR c.fn LIKE '% ' || c.esc || '%' THEN 0.9 ELSE 0 END,
                        CASE WHEN c.fu LIKE '%' || c.esc || '%' OR c.fn LIKE '%' || c.esc || '%' THEN 0.7 ELSE 0 END,
                        0.6 * extensions.word_similarity(c.t, c.fu),
                        0.6 * extensions.word_similarity(c.t, c.fn)
                    )::real AS score
                FROM matched c
            )
            SELECT
                s.id,
                CASE
                    WHEN s.exact THEN 0
                    WHEN s.followed THEN 1
                    WHEN coalesce(s.common_trails, 0) > 0 OR s.same_province THEN 2
                    ELSE 3
                END AS tier,
                s.score,
                s.common_trails,
                s.opened
            FROM scored s
            ORDER BY tier, s.score DESC, coalesce(s.common_trails, 0) DESC, s.username, s.id
            LIMIT least(greatest(max_rows, 1), 51)
            OFFSET greatest(skip, 0)
        $$
        """
    )

    op.execute(
        f"""
        CREATE FUNCTION private.suggest_hikers(viewer uuid, max_rows integer)
        RETURNS TABLE (user_id uuid, common_trails integer, same_province boolean)
        LANGUAGE sql
        STABLE
        SET search_path = ''
        AS $$
            WITH seen AS ({SEEN}),
            candidates AS (
                SELECT
                    c.id,
                    c.username,
                    {COMMON_TRAILS} AS common_trails,
                    {SAME_PROVINCE} AS same_province
                FROM seen c
                -- Community features on: public, journal shown, opted in.
                WHERE NOT c.is_private AND c.show_journal AND c.show_in_community
                  AND NOT EXISTS (
                      SELECT 1 FROM public.follows f WHERE f.follower_id = viewer AND f.followee_id = c.id
                  )
            )
            SELECT c.id, coalesce(c.common_trails, 0), c.same_province
            FROM candidates c
            WHERE coalesce(c.common_trails, 0) > 0 OR c.same_province
            ORDER BY coalesce(c.common_trails, 0) DESC, c.same_province DESC, c.username, c.id
            LIMIT least(greatest(max_rows, 1), 20)
        $$
        """
    )
    for signature in ("search_hikers(uuid, text, integer, integer)", "suggest_hikers(uuid, integer)"):
        op.execute(f"REVOKE ALL ON FUNCTION private.{signature} FROM PUBLIC, {CLIENTS}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS private.suggest_hikers(uuid, integer)")
    op.execute("DROP FUNCTION IF EXISTS private.search_hikers(uuid, text, integer, integer)")
    op.execute("DROP TABLE IF EXISTS public.blocks")
    op.execute("REVOKE UPDATE (findable_in_search) ON public.profile_settings FROM authenticated")
    op.execute("ALTER TABLE public.profile_settings DROP COLUMN IF EXISTS findable_in_search")
    op.execute("DROP INDEX IF EXISTS public.profiles_display_name_search_idx")
    op.execute("DROP INDEX IF EXISTS public.profiles_username_search_idx")
    op.execute("DROP FUNCTION IF EXISTS private.search_fold(text)")
    # unaccent stays: dropping an extension could break anything else using it.
