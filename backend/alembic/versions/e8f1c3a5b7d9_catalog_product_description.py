"""catalog_products.description: an optional one-line summary written by Trekly

Revision ID: e8f1c3a5b7d9
Revises: 5a9c3e7d1f24
Create Date: 2026-11-02 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e8f1c3a5b7d9"
down_revision: Union[str, Sequence[str], None] = "5a9c3e7d1f24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, no default: existing rows stay as they are. The catalogue's
    # table-level SELECT grant to anon/authenticated already covers it.
    op.add_column("catalog_products", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_products", "description")
