"""Add ml_probability column to signals table

Revision ID: 0011_add_ml_probability
Revises: 0010_bonus_days_archived
Create Date: 2026-01-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0011_add_ml_probability'
down_revision = '0010_bonus_days_archived'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ml_probability column to signals table
    op.add_column('signals', sa.Column('ml_probability', sa.Float(), nullable=True))


def downgrade() -> None:
    # Remove ml_probability column from signals table
    op.drop_column('signals', 'ml_probability')
