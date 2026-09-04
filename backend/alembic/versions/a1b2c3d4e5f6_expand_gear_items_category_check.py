"""expand gear_items category check to include essentials and safety

Revision ID: a1b2c3d4e5f6
Revises: ac80d30d85f6
Create Date: 2026-09-04 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ac80d30d85f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_CATEGORIES = ("shelter", "sleep", "kitchen", "clothing", "navigation", "first_aid", "other")
NEW_CATEGORIES = OLD_CATEGORIES + ("essentials", "safety")


def _check_sql(categories: tuple[str, ...]) -> str:
    values = ",".join(f"'{c}'::text" for c in categories)
    return f"category = ANY (ARRAY[{values}])"


def upgrade() -> None:
    op.drop_constraint("gear_items_category_check", "gear_items", type_="check")
    op.create_check_constraint(
        "gear_items_category_check", "gear_items", _check_sql(NEW_CATEGORIES)
    )


def downgrade() -> None:
    op.drop_constraint("gear_items_category_check", "gear_items", type_="check")
    op.create_check_constraint(
        "gear_items_category_check", "gear_items", _check_sql(OLD_CATEGORIES)
    )
