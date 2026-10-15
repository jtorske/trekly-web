"""revoke TRUNCATE on trails from anon and authenticated

Supabase's default grants give the API roles TRUNCATE on public tables, and
TRUNCATE bypasses row-level security. Trails are read-only for clients (RLS
allows SELECT only), so drop the one privilege RLS can't guard.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("REVOKE TRUNCATE ON public.trails FROM anon, authenticated")


def downgrade() -> None:
    op.execute("GRANT TRUNCATE ON public.trails TO anon, authenticated")
