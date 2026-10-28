"""trails get a structured park: park_name and park_type

Explore filters by province, park type and park, so these move out of the
free-text region into indexed columns. park_type is national, provincial,
regional or none (see app/models/trail.py). The values come from
catalog_data/trails_canada.json: run scripts/seed_trails.py after this
migration to fill them. Retired trails stay null.

Revision ID: 7a3c9e1f5b20
Revises: 6e2f4b8d1a37
Create Date: 2026-10-28 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7a3c9e1f5b20"
down_revision: Union[str, Sequence[str], None] = "6e2f4b8d1a37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trails", sa.Column("park_name", sa.Text(), nullable=True))
    op.add_column("trails", sa.Column("park_type", sa.Text(), nullable=True))
    op.create_check_constraint(
        "trails_park_type_check",
        "trails",
        "park_type in ('national','provincial','regional','none')",
    )
    op.create_index("trails_province_code_idx", "trails", ["province_code"])
    op.create_index("trails_park_type_idx", "trails", ["park_type"])
    op.create_index("trails_park_name_idx", "trails", ["park_name"])


def downgrade() -> None:
    op.drop_index("trails_park_name_idx", table_name="trails")
    op.drop_index("trails_park_type_idx", table_name="trails")
    op.drop_index("trails_province_code_idx", table_name="trails")
    op.drop_constraint("trails_park_type_check", "trails", type_="check")
    op.drop_column("trails", "park_type")
    op.drop_column("trails", "park_name")
