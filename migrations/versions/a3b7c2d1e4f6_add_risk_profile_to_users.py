"""add risk_profile to users

Revision ID: a3b7c2d1e4f6
Revises: f5741afc4c98
Create Date: 2026-05-08 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b7c2d1e4f6'
down_revision: Union[str, Sequence[str], None] = 'f5741afc4c98'
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
