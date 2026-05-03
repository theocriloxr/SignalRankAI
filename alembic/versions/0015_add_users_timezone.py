"""Add users.timezone and dca_profile columns

Revision ID: 0024_add_users_timezone_and_dca_profile
Revises: 0023_outcome_truth_and_delivery_state
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = '0024_add_users_timezone_and_dca_profile'
down_revision: Union[str, None] = '0023_outcome_truth_and_delivery_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone column if it doesn't exist
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)
    """)
    # Add dca_profile column if it doesn't exist
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS dca_profile VARCHAR(32)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS dca_profile")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS timezone")
