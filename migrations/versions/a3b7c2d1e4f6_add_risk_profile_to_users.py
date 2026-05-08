"""add risk_profile to users

Revision ID: a3b7c2d1e4f6
Revises: c1f4a12c9d3b
Create Date: 2026-05-08 07:00:00.000000

Note: down_revision rebased from f5741afc4c98 → c1f4a12c9d3b in P3-A3.
The original parent `f5741afc4c98` predates the `users` table (created in
`c1f4a12c9d3b`), so this migration could not actually run from there. The
rebase makes the chain linear and well-ordered. Safe to apply because no
production DB has yet upgraded to either head.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b7c2d1e4f6'
down_revision: Union[str, Sequence[str], None] = 'c1f4a12c9d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'risk_profile',
            sa.String(length=20),
            server_default='balanced',
            nullable=False,
        ),
    )
    op.create_check_constraint(
        'ck_users_risk_profile',
        'users',
        "risk_profile IN ('conservative', 'balanced', 'aggressive')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_users_risk_profile', 'users', type_='check')
    op.drop_column('users', 'risk_profile')
