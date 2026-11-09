"""signup email requests: the rate limit for the sign-up email helper

- signup_email_requests: one row per accepted request to POST
  /api/auth/signup-email, keyed by SHA-256 digests of the email address and
  the client IP (never the values themselves). The API counts the last
  hour's rows per key and deletes rows older than a day.
  Row-level security is on with no policies, and anon/authenticated hold no
  grants: only the backend reads or writes it.

Revision ID: c4f8e2a6d1b3
Revises: b4e7a2c9d1f3
Create Date: 2026-11-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c4f8e2a6d1b3"
down_revision: Union[str, Sequence[str], None] = "b4e7a2c9d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIENTS = "anon, authenticated"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.signup_email_requests (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            email_key text NOT NULL,
            ip_key text NOT NULL,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX signup_email_requests_email_idx ON public.signup_email_requests (email_key, created_at)")
    op.execute("CREATE INDEX signup_email_requests_ip_idx ON public.signup_email_requests (ip_key, created_at)")
    op.execute("CREATE INDEX signup_email_requests_created_idx ON public.signup_email_requests (created_at)")
    op.execute("ALTER TABLE public.signup_email_requests ENABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON public.signup_email_requests FROM {CLIENTS}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.signup_email_requests")
