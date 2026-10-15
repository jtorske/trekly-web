"""add trail country/province, popularity and retirement columns

- country_code / province_code: where the trail is, backfilled from the free
  text region on existing rows (fails loudly on any region it can't place).
- popularity_rank / _score / _source / _updated_at: catalogue ordering and its
  provenance ('editorial' for now), recomputable without a schema change.
- retired_at: trails that drop out of the catalogue are retired, never
  deleted, so saved_trails, trail_seasonal_conditions and campsites rows
  (whose FKs cascade or block on delete) are left untouched.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-15 12:30:00.000000

"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CA_PROVINCES = {
    "Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB", "New Brunswick": "NB",
    "Newfoundland and Labrador": "NL", "Nova Scotia": "NS", "Northwest Territories": "NT",
    "Nunavut": "NU", "Ontario": "ON", "Prince Edward Island": "PE", "Quebec": "QC",
    "Saskatchewan": "SK", "Yukon": "YT",
}
US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}
CA_CODE = re.compile(r"\b(" + "|".join(CA_PROVINCES.values()) + r")\b")


def place_region(region: str) -> tuple[str, str] | None:
    """(country_code, province_code) for an existing free-text region."""
    region = region.strip()
    if region in US_STATES:
        return "US", US_STATES[region]
    if region in CA_PROVINCES:
        return "CA", CA_PROVINCES[region]
    # "Banff National Park, AB", "Banff/Mount Assiniboine ..., BC-AB border"
    match = CA_CODE.search(region)
    if match:
        return "CA", match.group(1)
    return None


def upgrade() -> None:
    op.add_column("trails", sa.Column("country_code", sa.Text(), nullable=True))
    op.add_column("trails", sa.Column("province_code", sa.Text(), nullable=True))
    op.add_column("trails", sa.Column("popularity_rank", sa.Integer(), nullable=True))
    op.add_column("trails", sa.Column("popularity_score", sa.Numeric(6, 4), nullable=True))
    op.add_column("trails", sa.Column("popularity_source", sa.Text(), nullable=True))
    op.add_column("trails", sa.Column("popularity_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trails", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name, region FROM trails")).all()
    unplaced = []
    for trail_id, name, region in rows:
        placed = place_region(region)
        if placed is None:
            unplaced.append(f"{name} ({region})")
            continue
        bind.execute(
            sa.text("UPDATE trails SET country_code = :c, province_code = :p WHERE id = :id"),
            {"c": placed[0], "p": placed[1], "id": trail_id},
        )
    if unplaced:
        raise RuntimeError("Can't derive country/province for: " + "; ".join(unplaced))

    op.alter_column("trails", "country_code", nullable=False)
    op.create_check_constraint("trails_country_code_check", "trails", "country_code ~ '^[A-Z]{2}$'")
    op.create_check_constraint("trails_popularity_rank_check", "trails", "popularity_rank >= 1")
    op.create_unique_constraint("trails_name_province_key", "trails", ["name", "province_code"])
    op.create_index("trails_country_rank_idx", "trails", ["country_code", "popularity_rank"])


def downgrade() -> None:
    op.drop_index("trails_country_rank_idx", table_name="trails")
    op.drop_constraint("trails_name_province_key", "trails", type_="unique")
    op.drop_constraint("trails_popularity_rank_check", "trails", type_="check")
    op.drop_constraint("trails_country_code_check", "trails", type_="check")
    for column in (
        "retired_at", "popularity_updated_at", "popularity_source", "popularity_score",
        "popularity_rank", "province_code", "country_code",
    ):
        op.drop_column("trails", column)
