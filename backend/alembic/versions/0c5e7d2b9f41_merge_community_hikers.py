"""merge community hikers into the main line

9d4f2a6c8e13 ("Hiked by" opt-in) branched from 6e2f4b8d1a37 alongside
trail parks and featured badges, which c5e8a1d3f7b9 already merged. None
of them touch the same objects, so there's nothing to do here but join
the two heads.

Revision ID: 0c5e7d2b9f41
Revises: c5e8a1d3f7b9, 9d4f2a6c8e13
Create Date: 2026-10-28 13:26:49.616402

"""
from typing import Sequence, Union


revision: str = "0c5e7d2b9f41"
down_revision: Union[str, Sequence[str], None] = ("c5e8a1d3f7b9", "9d4f2a6c8e13")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
