"""trails.slug: readable trail page URLs (/trails/lake-agnes-tea-house)

Adds a unique, not-null slug to every trail, retired ones included (their
bookmarks still resolve). Backfilled from the name; namesakes (the two
Skyline Trails) both get their park added, then the province, then a
number (app/trail_slugs.py). New trails get theirs from the API on insert.
Public read like the other trail columns.

Revision ID: d7a3f9c1e5b8
Revises: e6b2d8a4c0f7
Create Date: 2026-11-17 12:00:00
"""
from typing import Sequence, Union

import re
import unicodedata

import sqlalchemy as sa
from alembic import op


revision: str = "d7a3f9c1e5b8"
down_revision: Union[str, Sequence[str], None] = "e6b2d8a4c0f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A frozen copy of app/trail_slugs.py as of this revision, so later edits
# there can't change what this migration does.
def _slugify(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.replace("&", " and ").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:120].rstrip("-")


def _candidates(name, park_name, province_code):
    base = _slugify(name) or "trail"
    yield base
    park = _slugify(park_name)
    if park.startswith(f"{base}-"):
        park = park[len(base) + 1:]
    with_park = f"{base}-{park}" if park and park not in base else base
    if with_park != base:
        yield with_park
    province = _slugify(province_code)
    with_province = f"{with_park}-{province}" if province else with_park
    if with_province != with_park:
        yield with_province
    number = 2
    while True:
        yield f"{with_province}-{number}"
        number += 1


def assign_slugs(rows):
    used, groups, out = set(), {}, {}
    for _, name, _, _, live in rows:
        groups.setdefault(_slugify(name) or "trail", []).append(live)
    for trail_id, name, park_name, province_code, live in rows:
        options = _candidates(name, park_name, province_code)
        base = next(options)
        group = groups[base]
        owns_base = len(group) == 1 or (live and group.count(True) == 1)
        slug = base if owns_base and base not in used else next(o for o in options if o not in used)
        used.add(slug)
        out[trail_id] = slug
    return out


def upgrade() -> None:
    op.add_column("trails", sa.Column("slug", sa.Text(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "select id, name, park_name, province_code, retired_at is null from trails "
        "order by popularity_rank nulls last, created_at, id"
    )).all()
    slugs = assign_slugs([tuple(row) for row in rows])
    for trail_id, slug in slugs.items():
        bind.execute(sa.text("update trails set slug = :slug where id = :id"), {"slug": slug, "id": trail_id})
    op.alter_column("trails", "slug", nullable=False)
    op.create_unique_constraint("trails_slug_key", "trails", ["slug"])
    op.create_check_constraint("trails_slug_format_check", "trails", "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'")


def downgrade() -> None:
    op.drop_constraint("trails_slug_format_check", "trails", type_="check")
    op.drop_constraint("trails_slug_key", "trails", type_="unique")
    op.drop_column("trails", "slug")
