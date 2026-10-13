"""add user_gear table for per-user gear collections

Rows are read and written directly from the browser through Supabase, so
row-level security scopes every operation to the signed-in user.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = ("pack", "shelter", "sleep", "clothing", "cooking", "water", "accessories")


def upgrade() -> None:
    categories = ",".join(f"'{c}'" for c in CATEGORIES)
    op.execute(
        f"""
        create table public.user_gear (
            id uuid primary key default gen_random_uuid(),
            user_id uuid not null default auth.uid()
                references auth.users (id) on delete cascade,
            category text not null check (category in ({categories})),
            slot text,
            name text not null check (length(trim(name)) > 0),
            brand text,
            model text,
            weight_g integer check (weight_g is null or weight_g >= 0),
            quantity integer not null default 1 check (quantity > 0),
            gear_item_id uuid references public.gear_items (id) on delete set null,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        """
    )
    op.execute("create index user_gear_user_id_idx on public.user_gear (user_id)")
    op.execute("alter table public.user_gear enable row level security")
    for action, clause in (
        ("select", "using (user_id = auth.uid())"),
        ("insert", "with check (user_id = auth.uid())"),
        ("update", "using (user_id = auth.uid()) with check (user_id = auth.uid())"),
        ("delete", "using (user_id = auth.uid())"),
    ):
        op.execute(
            f'create policy "user_gear_{action}_own" on public.user_gear '
            f"for {action} to authenticated {clause}"
        )
    op.execute(
        "grant select, insert, update, delete on public.user_gear to authenticated"
    )


def downgrade() -> None:
    op.execute("drop table if exists public.user_gear")
