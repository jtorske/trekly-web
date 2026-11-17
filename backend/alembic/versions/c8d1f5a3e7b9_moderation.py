"""moderation: screened and reported content, account restrictions, quarantine

- moderation_items: one row per piece of user content under watch (an
  Activity post, a hike's note or photo, a bio, a profile photo, a profile,
  a comment), keyed by (kind, target_id). Holds the automated check's
  scores, the report counts, the admin's decision, and any withheld text or
  photo path (app/models/moderation.py).
- account_restrictions: suspensions and locks.
- profile_reports gains item_id and counts_toward_hide.
- admin_audit_log accepts the moderation actions.
- moderation-quarantine: a private Storage bucket with no client policies at
  all, where a photo flagged for child safety is copied so the author can't
  delete it.

Every new table is closed to clients (RLS on, no grants); only the API
reads and writes them.

Revision ID: c8d1f5a3e7b9
Revises: e3c7a9d5f1b2
Create Date: 2026-11-10 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c8d1f5a3e7b9"
down_revision: Union[str, Sequence[str], None] = "e3c7a9d5f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
ACTIONS_BEFORE = (
    "hide_profile", "unhide_profile", "clear_username", "ban_user", "unban_user",
    "send_password_reset", "resolve_report", "reopen_report", "hide_post", "unhide_post",
    "official_post", "delete_official_post",
)
ACTIONS_AFTER = (
    *ACTIONS_BEFORE, "approve_item", "hide_item", "warn_user", "suspend_user", "unsuspend_user", "lock_account",
)
QUARANTINE = "moderation-quarantine"


def _audit_check(actions: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{a}'" for a in actions)
    op.execute("ALTER TABLE public.admin_audit_log DROP CONSTRAINT admin_audit_log_action_check")
    op.execute(
        "ALTER TABLE public.admin_audit_log ADD CONSTRAINT admin_audit_log_action_check "
        f"CHECK (action IN ({listed}))"
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.moderation_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            kind text NOT NULL CONSTRAINT moderation_items_kind_check
                CHECK (kind IN ('post', 'hike_note', 'hike_photo', 'bio', 'avatar', 'profile', 'comment')),
            target_id uuid NOT NULL,
            author_id uuid NOT NULL,
            state text NOT NULL DEFAULT 'visible' CONSTRAINT moderation_items_state_check
                CHECK (state IN ('visible', 'held', 'hidden')),
            in_queue boolean NOT NULL DEFAULT false,
            queue_reason text CONSTRAINT moderation_items_queue_reason_check
                CHECK (queue_reason IS NULL OR queue_reason IN
                       ('flagged', 'unscreened', 'reported', 'child_safety', 'edited_after_hide')),
            text text,
            photo_path text,
            quarantine_path text,
            screening text CONSTRAINT moderation_items_screening_check
                CHECK (screening IS NULL OR screening IN ('passed', 'flagged', 'unavailable')),
            scores jsonb,
            flagged_categories jsonb,
            screened_at timestamptz,
            screening_model text,
            child_safety boolean NOT NULL DEFAULT false,
            qualifying_reports integer NOT NULL DEFAULT 0,
            open_reports integer NOT NULL DEFAULT 0,
            last_reported_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            activity_at timestamptz NOT NULL DEFAULT now(),
            decision text CONSTRAINT moderation_items_decision_check
                CHECK (decision IS NULL OR decision IN ('approved', 'hidden')),
            decision_reason text CONSTRAINT moderation_items_decision_reason_length_check
                CHECK (decision_reason IS NULL OR length(decision_reason) <= 500),
            decided_at timestamptz,
            decided_by uuid,
            digest_sent_at timestamptz,
            CONSTRAINT moderation_items_target_key UNIQUE (kind, target_id)
        )
        """
    )
    op.execute("CREATE INDEX moderation_items_queue_idx ON public.moderation_items (in_queue, activity_at)")
    op.execute("CREATE INDEX moderation_items_author_idx ON public.moderation_items (author_id)")

    op.execute(
        """
        CREATE TABLE public.account_restrictions (
            user_id uuid PRIMARY KEY,
            suspended_until timestamptz,
            locked_at timestamptz,
            lock_reason text CONSTRAINT account_restrictions_reason_check
                CHECK (lock_reason IS NULL OR length(lock_reason) <= 500),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    for table in ("moderation_items", "account_restrictions"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM {CLIENTS}")

    op.execute(
        """
        ALTER TABLE public.profile_reports
            ADD COLUMN item_id uuid REFERENCES public.moderation_items (id) ON DELETE SET NULL,
            ADD COLUMN counts_toward_hide boolean NOT NULL DEFAULT false
        """
    )
    op.execute("CREATE INDEX ix_profile_reports_item_id ON public.profile_reports (item_id)")
    _audit_check(ACTIONS_AFTER)

    # Private, and no policies: only the service-role key can read or write it.
    op.execute(
        "INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types) "
        f"VALUES ('{QUARANTINE}', '{QUARANTINE}', false, 5242880, "
        "ARRAY['image/webp','image/jpeg','image/png']) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    # The quarantine bucket is left in place: it may hold evidence that must be kept.
    _audit_check(ACTIONS_BEFORE)
    op.execute("DROP INDEX IF EXISTS public.ix_profile_reports_item_id")
    op.execute(
        """
        ALTER TABLE public.profile_reports
            DROP COLUMN IF EXISTS counts_toward_hide,
            DROP COLUMN IF EXISTS item_id
        """
    )
    op.execute("DROP TABLE IF EXISTS public.account_restrictions")
    op.execute("DROP TABLE IF EXISTS public.moderation_items")
