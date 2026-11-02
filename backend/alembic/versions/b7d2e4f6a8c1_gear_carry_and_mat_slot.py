"""gear items: carry mode (worn / consumable) and a mat slot override

- carry: how an item counts toward pack weight. Null is the slot's default
  (footwear worn, the rest packed); base weight leaves out worn and
  consumable items.
- mat_slot: the gear mat slot the owner dragged the item to. Null means
  the slot its category maps to.

Neither column joins the client column grants (214aa07bf743): the app reads
gear through the API, and public profiles don't show them.

Revision ID: b7d2e4f6a8c1
Revises: 0c5e7d2b9f41
Create Date: 2026-10-28 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7d2e4f6a8c1"
down_revision: Union[str, Sequence[str], None] = "0c5e7d2b9f41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_gear_items", sa.Column("carry", sa.Text(), nullable=True))
    op.add_column("user_gear_items", sa.Column("mat_slot", sa.Text(), nullable=True))
    op.create_check_constraint(
        "user_gear_items_carry_check",
        "user_gear_items",
        "carry is null or carry in ('packed','worn','consumable')",
    )
    op.create_check_constraint(
        "user_gear_items_mat_slot_check",
        "user_gear_items",
        "mat_slot is null or (length(mat_slot) between 1 and 40)",
    )


def downgrade() -> None:
    op.drop_constraint("user_gear_items_mat_slot_check", "user_gear_items", type_="check")
    op.drop_constraint("user_gear_items_carry_check", "user_gear_items", type_="check")
    op.drop_column("user_gear_items", "mat_slot")
    op.drop_column("user_gear_items", "carry")
