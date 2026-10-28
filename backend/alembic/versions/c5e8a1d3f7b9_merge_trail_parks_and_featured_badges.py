"""merge trail parks and featured badges

Both branched from 6e2f4b8d1a37 and touch different tables.

Revision ID: c5e8a1d3f7b9
Revises: 7a3c9e1f5b20, 8b3e5f1c2d40
Create Date: 2026-10-28 17:00:00.000000

"""
from typing import Sequence, Union


revision: str = "c5e8a1d3f7b9"
down_revision: Union[str, Sequence[str], None] = ("7a3c9e1f5b20", "8b3e5f1c2d40")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
