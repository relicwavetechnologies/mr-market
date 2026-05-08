"""add screeners table + 6 seed packs (P3-A3)

Revision ID: b8e2f1c4a7d3
Revises: a3b7c2d1e4f6
Create Date: 2026-05-08 09:30:00.000000

Creates the `screeners` table and inserts six seed packs that exercise
every field family the screener engine (P3-A2) currently supports —
technicals, holdings, sector. The seed packs are intentionally simple:
they have to parse against `app.analytics.screener.ALLOWED_FIELDS` and
return a non-empty result on the live NIFTY-100 universe so the demo
flow always has something to show.

Seed packs:
  oversold_quality      — RSI oversold + healthy promoter holding
  value_rebound         — Below 200-DMA + neutral RSI (mean-reversion candidate)
  momentum_breakout     — RSI strong + price above both SMAs
  high_pledge_avoid     — REJECTS Adani-style high-promoter holdings
                          (placeholder until pledged_pct is in the
                          allowlist; A-3 ships the table, the field
                          column will land alongside the persisted
                          pledge cache later in the phase)
  fii_buying            — Public-holding rose vs prior quarter
                          (placeholder using public_pct only — full
                          QoQ delta requires a join not yet wired)
  promoter_increasing   — Heavy promoter floor (>60%) + neutral RSI
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'b8e2f1c4a7d3'
down_revision: Union[str, Sequence[str], None] = 'a3b7c2d1e4f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_PACKS: list[tuple[str, str, str]] = [
    (
        "oversold_quality",
        "rsi_14 < 35 AND promoter_pct > 50",
        "RSI oversold (< 35) with healthy promoter ownership (> 50%). "
        "Mean-reversion candidates where founder skin-in-the-game is high.",
    ),
    (
        "value_rebound",
        "close < sma_200 AND rsi_14 < 50",
        "Below 200-day moving average with non-overbought RSI. "
        "Below-trend names with room to rebound.",
    ),
    (
        "momentum_breakout",
        "rsi_14 > 65 AND close > sma_50 AND close > sma_200",
        "Strong momentum (RSI > 65) with price above both 50-DMA and "
        "200-DMA. Trending names extending the move.",
    ),
    (
        "high_pledge_avoid",
        "promoter_pct > 70 AND rsi_14 > 60",
        "High promoter concentration (> 70%) with rising RSI — flag for "
        "extra diligence before sizing in.",
    ),
    (
        "fii_buying",
        "public_pct > 35 AND close > sma_50",
        "Public ownership > 35% (proxy for FII/DII presence) trading "
        "above 50-DMA — broader-base trend confirmation.",
    ),
    (
        "promoter_increasing",
        "promoter_pct > 60 AND rsi_14 > 40 AND rsi_14 < 70",
        "Heavy promoter floor (> 60%) in the neutral-momentum band. "
        "Steady-compounder profile.",
    ),
]


def upgrade() -> None:
    op.create_table(
        'screeners',
        sa.Column('name', sa.String(length=64), primary_key=True),
        sa.Column('expr', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'is_seed',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column(
            'created_by',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
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
    op.create_index('ix_screeners_is_seed', 'screeners', ['is_seed'])

    # Insert seed packs.
    screeners_table = sa.table(
        'screeners',
        sa.column('name', sa.String),
        sa.column('expr', sa.Text),
        sa.column('description', sa.Text),
        sa.column('is_seed', sa.Boolean),
    )
    op.bulk_insert(
        screeners_table,
        [
            {"name": n, "expr": e, "description": d, "is_seed": True}
            for n, e, d in SEED_PACKS
        ],
    )


def downgrade() -> None:
    op.drop_index('ix_screeners_is_seed', table_name='screeners')
    op.drop_table('screeners')
