"""Add users.timezone column

Revision ID: 0015_add_users_timezone
Revises: 0014_decision_log_and_ml_rejected
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '0015_add_users_timezone'
down_revision: Union[str, None] = '0014_decision_log_and_ml_rejected'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('timezone', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('dca_profile', sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'dca_profile')
    op.drop_column('users', 'timezone')
