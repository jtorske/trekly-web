"""merge home province and admin area

Both branched from d3b8f1a6c2e4; nothing to change, this just joins them.

Revision ID: 5a9c3e7d1f24
Revises: 4f8b2c6d9e13, e2a7c4f9b1d6
Create Date: 2026-11-03 09:00:00.000000

"""
from typing import Sequence, Union


revision: str = "5a9c3e7d1f24"
down_revision: Union[str, Sequence[str], None] = ("4f8b2c6d9e13", "e2a7c4f9b1d6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
