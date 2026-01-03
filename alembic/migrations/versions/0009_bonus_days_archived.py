"""Add bonus_days to subscriptions and archived to signals

Revision ID: 0009_bonus_days_archived
Revises: 0008_user_tier_column
Create Date: 2026-01-03 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0009_bonus_days_archived'
down_revision = '0008_user_tier_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add bonus_days column to subscriptions (for referral stacking)
    op.add_column('subscriptions', sa.Column('bonus_days', sa.Integer(), nullable=False, server_default='0'))
    
    # Add archived column to signals (soft delete after outcome)
    op.add_column('signals', sa.Column('archived', sa.Boolean(), nullable=False, server_default='false', index=True))


def downgrade() -> None:
    op.drop_column('signals', 'archived')
    op.drop_column('subscriptions', 'bonus_days')
