"""Trekly Guide chat: daily message counts (per user) and daily totals

- guide_chat_usage (user_id, day, messages): the per-user daily cap.
  user_id references auth.users ON DELETE CASCADE, so it goes with the account.
- guide_chat_metrics (day, messages, tool_calls, fallbacks, provider_errors,
  rate_limited, moderation_blocked, cap_reached, guarded): admin totals.

Counts only: no message text is stored anywhere. Row-level security on and
every client grant revoked: only the API (service role) reads or writes them.

Revision ID: a9d4c7e2b6f1
Revises: f3b8d2a6c4e1
Create Date: 2026-11-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a9d4c7e2b6f1"
down_revision: Union[str, Sequence[str], None] = "f3b8d2a6c4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"
METRICS = ("messages", "tool_calls", "fallbacks", "provider_errors", "rate_limited",
           "moderation_blocked", "cap_reached", "guarded")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.guide_chat_usage (
            user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
            day date NOT NULL,
            messages integer NOT NULL DEFAULT 0 CHECK (messages >= 0),
            PRIMARY KEY (user_id, day)
        )
        """
    )
    columns = ",\n".join(f"{m} integer NOT NULL DEFAULT 0 CHECK ({m} >= 0)" for m in METRICS)
    op.execute(f"CREATE TABLE public.guide_chat_metrics (day date PRIMARY KEY, {columns})")
    for table in ("guide_chat_usage", "guide_chat_metrics"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM {CLIENTS}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.guide_chat_metrics")
    op.execute("DROP TABLE IF EXISTS public.guide_chat_usage")
