"""add named gear setups

gear_setups groups a user's own inventory items ("Ultralight 2-Night Kit").
gear_setup_items only links existing user_gear_items; RLS requires both the
setup and the linked item to belong to the signed-in user.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-13 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.gear_setups (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
            name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 80),
            description text CHECK (description IS NULL OR length(description) <= 500),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX gear_setups_user_id_idx ON public.gear_setups (user_id)")
    op.execute("CREATE UNIQUE INDEX gear_setups_user_name_key ON public.gear_setups (user_id, lower(btrim(name)))")
    op.execute(
        """
        CREATE TABLE public.gear_setup_items (
            setup_id uuid NOT NULL REFERENCES public.gear_setups (id) ON DELETE CASCADE,
            gear_item_id uuid NOT NULL REFERENCES public.user_gear_items (id) ON DELETE CASCADE,
            position integer NOT NULL DEFAULT 0,
            PRIMARY KEY (setup_id, gear_item_id)
        )
        """
    )
    op.execute("CREATE INDEX gear_setup_items_item_idx ON public.gear_setup_items (gear_item_id)")

    op.execute("ALTER TABLE public.gear_setups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.gear_setup_items ENABLE ROW LEVEL SECURITY")
    own = "user_id = (select auth.uid())"
    for action, clause in (
        ("select", f"USING ({own})"),
        ("insert", f"WITH CHECK ({own})"),
        ("update", f"USING ({own}) WITH CHECK ({own})"),
        ("delete", f"USING ({own})"),
    ):
        op.execute(
            f'CREATE POLICY "gear_setups_{action}_own" ON public.gear_setups '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    # A link is visible/writable only if the user owns both the setup and the item.
    owns_link = (
        "EXISTS (SELECT 1 FROM public.gear_setups s WHERE s.id = setup_id AND s.user_id = (select auth.uid())) "
        "AND EXISTS (SELECT 1 FROM public.user_gear_items g WHERE g.id = gear_item_id AND g.user_id = (select auth.uid()))"
    )
    for action, clause in (
        ("select", f"USING ({owns_link})"),
        ("insert", f"WITH CHECK ({owns_link})"),
        ("update", f"USING ({owns_link}) WITH CHECK ({owns_link})"),
        ("delete", f"USING ({owns_link})"),
    ):
        op.execute(
            f'CREATE POLICY "gear_setup_items_{action}_own" ON public.gear_setup_items '
            f"FOR {action.upper()} TO authenticated {clause}"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.gear_setups TO authenticated")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.gear_setup_items TO authenticated")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.gear_setup_items")
    op.execute("DROP TABLE IF EXISTS public.gear_setups")
