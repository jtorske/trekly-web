"""automatic @trekly posts: drafts, per-type auto-publish, fact bank, post sources

- trekly_post_drafts: generated posts waiting for review (app/models/trekly_post.py).
  A unique dedupe_key makes the daily run idempotent.
- trekly_post_type_settings: the per-type auto-publish toggle (off unless an
  admin turns it on; a missing row means off).
- trekly_facts: the curated fact bank; only approved facts are posted.
- activity_posts gains source_url / source_label / source_date, the official
  page an announcement quotes or cites. Clients keep their column grants
  (no new ones): the API returns these.

All three new tables are API-only: RLS on, no policies, no client privileges.

Revision ID: d7a2f9c4e6b1
Revises: b9e4d2a7c1f6
Create Date: 2026-11-17 12:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d7a2f9c4e6b1"
down_revision: Union[str, Sequence[str], None] = "b9e4d2a7c1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
TYPES = "'trending', 'spotlight', 'new_on_trekly', 'roundup', 'fun_fact', 'conditions'"
TABLES = ("trekly_post_drafts", "trekly_post_type_settings", "trekly_facts")


def upgrade() -> None:
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN source_url text")
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN source_label text")
    op.execute("ALTER TABLE public.activity_posts ADD COLUMN source_date date")
    op.execute(
        "ALTER TABLE public.activity_posts ADD CONSTRAINT activity_posts_source_check "
        "CHECK (source_url IS NULL OR (kind = 'announcement' AND length(source_url) <= 500 "
        "AND source_url LIKE 'https://%'))"
    )

    op.execute(
        """
        CREATE TABLE public.trekly_facts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            text text NOT NULL CONSTRAINT trekly_facts_text_length_check CHECK (length(text) BETWEEN 1 AND 400),
            trail_id uuid REFERENCES public.trails (id) ON DELETE SET NULL,
            park_name text,
            source_url text NOT NULL CONSTRAINT trekly_facts_source_url_check
                CHECK (length(source_url) BETWEEN 1 AND 500 AND source_url LIKE 'https://%'),
            approved boolean NOT NULL DEFAULT false,
            seed_key text,
            updated_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX trekly_facts_seed_key ON public.trekly_facts (seed_key)")

    op.execute(
        f"""
        CREATE TABLE public.trekly_post_drafts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_type text NOT NULL CONSTRAINT trekly_post_drafts_type_check CHECK (post_type IN ({TYPES})),
            status text NOT NULL DEFAULT 'draft' CONSTRAINT trekly_post_drafts_status_check
                CHECK (status IN ('draft', 'scheduled', 'published', 'rejected', 'expired')),
            dedupe_key text NOT NULL,
            run_date date NOT NULL,
            body text NOT NULL CONSTRAINT trekly_post_drafts_body_length_check CHECK (length(body) BETWEEN 1 AND 500),
            template_body text NOT NULL,
            writer text NOT NULL DEFAULT 'template' CONSTRAINT trekly_post_drafts_writer_check
                CHECK (writer IN ('template', 'ai', 'admin')),
            ai_note text,
            trail_id uuid REFERENCES public.trails (id) ON DELETE SET NULL,
            fact_id uuid REFERENCES public.trekly_facts (id) ON DELETE SET NULL,
            source_url text,
            source_label text,
            source_date date,
            data jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            publish_on date,
            post_id uuid REFERENCES public.activity_posts (id) ON DELETE SET NULL,
            published_at timestamptz,
            decided_by uuid,
            decided_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT trekly_post_drafts_schedule_check CHECK (status <> 'scheduled' OR publish_on IS NOT NULL),
            -- A published draft whose post was later deleted keeps status 'published'
            -- with post_id cleared by the FK, so this only applies on the way in.
            CONSTRAINT trekly_post_drafts_published_check
                CHECK (status <> 'published' OR post_id IS NOT NULL OR published_at IS NOT NULL)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX trekly_post_drafts_dedupe_key ON public.trekly_post_drafts (dedupe_key)")
    op.execute("CREATE INDEX trekly_post_drafts_status_idx ON public.trekly_post_drafts (status, created_at)")
    op.execute("CREATE INDEX trekly_post_drafts_trail_idx ON public.trekly_post_drafts (trail_id, created_at)")

    op.execute(
        f"""
        CREATE TABLE public.trekly_post_type_settings (
            post_type text PRIMARY KEY CONSTRAINT trekly_post_type_settings_type_check CHECK (post_type IN ({TYPES})),
            auto_publish boolean NOT NULL DEFAULT false,
            updated_by uuid,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC, {CLIENTS}")


def downgrade() -> None:
    for table in ("trekly_post_drafts", "trekly_post_type_settings", "trekly_facts"):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
    op.execute("ALTER TABLE public.activity_posts DROP CONSTRAINT IF EXISTS activity_posts_source_check")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS source_date")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS source_label")
    op.execute("ALTER TABLE public.activity_posts DROP COLUMN IF EXISTS source_url")
