"""add portfolios + holdings_user (P3-A4)

Revision ID: c91d4f6e8b27
Revises: b8e2f1c4a7d3
Create Date: 2026-05-08 11:00:00.000000

`holdings_user` is intentionally distinct from the existing `holdings`
table (which stores NSE quarterly shareholding-pattern data). Same
domain word, different scope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'c91d4f6e8b27'
down_revision: Union[str, Sequence[str], None] = 'b8e2f1c4a7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolios',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'name',
            sa.String(length=128),
            server_default='My Portfolio',
            nullable=False,
        ),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index('ix_portfolios_user_id', 'portfolios', ['user_id'])

    op.create_table(
        'holdings_user',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            'portfolio_id',
            sa.BigInteger(),
            sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'ticker',
            sa.String(length=32),
            sa.ForeignKey('stocks.ticker', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('avg_price', sa.Numeric(14, 4), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_holdings_user_portfolio_id', 'holdings_user', ['portfolio_id']
    )
    op.create_index('ix_holdings_user_ticker', 'holdings_user', ['ticker'])


def downgrade() -> None:
    op.drop_index('ix_holdings_user_ticker', table_name='holdings_user')
    op.drop_index('ix_holdings_user_portfolio_id', table_name='holdings_user')
    op.drop_table('holdings_user')
    op.drop_index('ix_portfolios_user_id', table_name='portfolios')
    op.drop_table('portfolios')
