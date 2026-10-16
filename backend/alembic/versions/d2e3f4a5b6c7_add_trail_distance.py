"""add trail distance

- route_type: 'out_and_back', 'loop' or 'point_to_point'.
- distance_km: the distance a hiker covers, from OpenStreetMap (see the
  catalogue's verification.distance_km), one decimal: the round trip for an
  out-and-back, the loop for a loop, the full one-way length for a
  point-to-point route. Set together with route_type; null where it couldn't
  be sourced.

Values come from catalog_data/trails_canada.json via scripts/seed_trails.py;
this migration only adds the columns.

Revision ID: d2e3f4a5b6c7
Revises: 6cf9b95bf4d2
Create Date: 2026-10-15 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "6cf9b95bf4d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trails", sa.Column("distance_km", sa.Numeric(5, 1)))
    op.add_column("trails", sa.Column("route_type", sa.Text()))
    op.create_check_constraint(
        "trails_distance_check",
        "trails",
        "(distance_km is null and route_type is null) or "
        "(distance_km > 0 and route_type in ('out_and_back','loop','point_to_point'))",
    )


def downgrade() -> None:
    op.drop_constraint("trails_distance_check", "trails", type_="check")
    op.drop_column("trails", "route_type")
    op.drop_column("trails", "distance_km")
