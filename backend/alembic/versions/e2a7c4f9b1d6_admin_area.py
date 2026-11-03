"""admin area: report status and trip-note link, admin audit log

- profile_reports gains status ('open' until an admin resolves it),
  resolved_at / resolved_by, and trail_id (set when the report is about the
  user's trip note on that trail). Existing reports start open.
- admin_audit_log: one row per admin action (who, what, when, on whom). No
  foreign keys to auth.users, so rows outlive the accounts they mention.

Both tables stay closed to clients (RLS on, no grants to anon or
authenticated); only the backend reads and writes them.

Revision ID: e2a7c4f9b1d6
Revises: d3b8f1a6c2e4
Create Date: 2026-11-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e2a7c4f9b1d6"
down_revision: Union[str, Sequence[str], None] = "d3b8f1a6c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
ACTIONS = (
    "hide_profile", "unhide_profile", "clear_username", "ban_user", "unban_user",
    "send_password_reset", "resolve_report", "reopen_report",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.profile_reports
            ADD COLUMN trail_id uuid REFERENCES public.trails (id) ON DELETE SET NULL,
            ADD COLUMN status text NOT NULL DEFAULT 'open',
            ADD COLUMN resolved_at timestamptz,
            ADD COLUMN resolved_by uuid,
            ADD CONSTRAINT profile_reports_status_check CHECK (status IN ('open', 'resolved'))
        """
    )
    op.execute(
        "CREATE INDEX profile_reports_status_created_idx ON public.profile_reports (status, created_at DESC)"
    )

    actions = ", ".join(f"'{a}'" for a in ACTIONS)
    op.execute(
        f"""
        CREATE TABLE public.admin_audit_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            admin_id uuid NOT NULL,
            action text NOT NULL CONSTRAINT admin_audit_log_action_check CHECK (action IN ({actions})),
            target_user_id uuid,
            target_report_id uuid,
            details jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX admin_audit_log_created_idx ON public.admin_audit_log (created_at)")
    op.execute(
        "CREATE INDEX admin_audit_log_target_idx ON public.admin_audit_log (target_user_id, created_at)"
    )
    op.execute("ALTER TABLE public.admin_audit_log ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.admin_audit_log FROM {CLIENTS}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.admin_audit_log")
    op.execute("DROP INDEX IF EXISTS public.profile_reports_status_created_idx")
    op.execute(
        """
        ALTER TABLE public.profile_reports
            DROP CONSTRAINT IF EXISTS profile_reports_status_check,
            DROP COLUMN IF EXISTS resolved_by,
            DROP COLUMN IF EXISTS resolved_at,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS trail_id
        """
    )
