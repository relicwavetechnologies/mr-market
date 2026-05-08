"""add watchlist (P3-A7)

Revision ID: d4e5a8b1f3c9
Revises: c91d4f6e8b27
Create Date: 2026-05-08 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'd4e5a8b1f3c9'
down_revision: Union[str, Sequence[str], None] = 'c91d4f6e8b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watchlist',
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'ticker',
            sa.String(length=32),
            sa.ForeignKey('stocks.ticker', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('user_id', 'ticker', name='pk_watchlist'),
    )
    op.create_index('ix_watchlist_user_id', 'watchlist', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_watchlist_user_id', table_name='watchlist')
    op.drop_table('watchlist')
