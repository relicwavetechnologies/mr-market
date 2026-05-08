"""widen documents.fy from VARCHAR(8) to VARCHAR(16)

Revision ID: e7a3c1f2b9d8
Revises: d4e5a8b1f3c9
Create Date: 2026-05-08 12:30:00.000000

VARCHAR(8) only fits the canonical "FY25" / "FY2025" formats — uploads
in the wild use "FY24-FY25" (9), "FY24-25" (7), "Q4 FY26" (7), etc.
Widening to 16 covers every realistic format without a recompile.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a3c1f2b9d8'
down_revision: Union[str, Sequence[str], None] = 'd4e5a8b1f3c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'documents',
        'fy',
        existing_type=sa.String(length=8),
        type_=sa.String(length=16),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'documents',
        'fy',
        existing_type=sa.String(length=16),
        type_=sa.String(length=8),
        existing_nullable=True,
    )
