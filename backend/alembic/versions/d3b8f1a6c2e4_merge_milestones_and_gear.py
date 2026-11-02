"""merge the milestone set (a4c7e2b9d1f3) and gear carry/mat slot (b7d2e4f6a8c1)

Both branched from 0c5e7d2b9f41 and touch different tables.

Revision ID: d3b8f1a6c2e4
Revises: a4c7e2b9d1f3, b7d2e4f6a8c1
Create Date: 2026-11-02 12:00:00.000000

"""
from typing import Sequence, Union


revision: str = "d3b8f1a6c2e4"
down_revision: Union[str, Sequence[str], None] = ("a4c7e2b9d1f3", "b7d2e4f6a8c1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
