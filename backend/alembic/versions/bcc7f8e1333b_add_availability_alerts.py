"""add availability alerts, availability cache, provider request budget and job locks

- availability_alerts: a user's "alert me when this opens up" for one
  campground and stay. user_id references auth.users and cascades, so
  deleting an account deletes its alerts. Owners can read their own alerts;
  all writes go through the API (status changes are validated there), so
  there are no write policies.
- availability_cache: provider responses for a few minutes, shared by the API
  and the poller.
- provider_request_budget: the global per-minute cap on provider requests.
- job_locks: the poller's overlap lease and minimum-interval bookkeeping.

The last three are backend-only: RLS on with no policies, and every
privilege revoked from anon/authenticated.

The DDL was generated from app/models/availability.py when this migration was
written and is frozen here on purpose.

Revision ID: bcc7f8e1333b
Revises: f1afb297138e
Create Date: 2026-10-15 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "bcc7f8e1333b"
down_revision: Union[str, Sequence[str], None] = "f1afb297138e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BACKEND_ONLY = ["availability_cache", "provider_request_budget", "job_locks"]

CREATE = [
    """
    CREATE TABLE public.availability_cache (
    	cache_key TEXT NOT NULL,
    	response JSONB NOT NULL,
    	fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
    	PRIMARY KEY (cache_key)
    )
    """,
    "CREATE INDEX ix_availability_cache_fetched_at ON public.availability_cache (fetched_at)",
    """
    CREATE TABLE public.provider_request_budget (
    	provider TEXT NOT NULL,
    	window_started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    	window_count INTEGER NOT NULL DEFAULT 0,
    	total_requests INTEGER NOT NULL DEFAULT 0,
    	PRIMARY KEY (provider)
    )
    """,
    """
    CREATE TABLE public.job_locks (
    	name TEXT NOT NULL,
    	locked_by TEXT,
    	locked_until TIMESTAMP WITH TIME ZONE,
    	last_started_at TIMESTAMP WITH TIME ZONE,
    	last_finished_at TIMESTAMP WITH TIME ZONE,
    	last_result TEXT,
    	PRIMARY KEY (name)
    )
    """,
    """
    CREATE TABLE public.availability_alerts (
    	id UUID NOT NULL DEFAULT gen_random_uuid(),
    	user_id UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    	email TEXT NOT NULL,
    	site_id UUID NOT NULL,
    	trail_id UUID,
    	start_date DATE NOT NULL,
    	nights INTEGER NOT NULL,
    	party_size INTEGER NOT NULL,
    	status TEXT NOT NULL DEFAULT 'active',
    	last_checked_at TIMESTAMP WITH TIME ZONE,
    	last_result JSONB,
    	notified_at TIMESTAMP WITH TIME ZONE,
    	cancelled_at TIMESTAMP WITH TIME ZONE,
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    	PRIMARY KEY (id),
    	CONSTRAINT availability_alerts_status_check CHECK (status in ('active','notified','cancelled','expired')),
    	CONSTRAINT availability_alerts_nights_check CHECK (nights between 1 and 14),
    	CONSTRAINT availability_alerts_party_check CHECK (party_size between 1 and 12),
    	FOREIGN KEY(site_id) REFERENCES public.backcountry_sites (id) ON DELETE RESTRICT,
    	FOREIGN KEY(trail_id) REFERENCES public.trails (id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX availability_alerts_user_idx ON public.availability_alerts (user_id, status)",
    "CREATE INDEX availability_alerts_active_idx ON public.availability_alerts (status, start_date)",
]


def upgrade() -> None:
    for statement in CREATE:
        op.execute(statement)

    for table in BACKEND_ONLY + ["availability_alerts"]:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")

    op.execute("GRANT SELECT ON public.availability_alerts TO authenticated")
    op.execute(
        'CREATE POLICY "availability_alerts_select_own" ON public.availability_alerts '
        "FOR SELECT TO authenticated USING (user_id = (select auth.uid()))"
    )


def downgrade() -> None:
    for table in ["availability_alerts"] + list(reversed(BACKEND_ONLY)):
        op.execute(f"DROP TABLE IF EXISTS public.{table}")
