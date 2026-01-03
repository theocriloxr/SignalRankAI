"""Add referral_count to users and referrer_notified_at to referrals

Revision ID: 0010_referral_enhancements
Revises: 0009_bonus_days_archived
Create Date: 2026-01-03 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '0010_referral_enhancements'
down_revision = '0009_bonus_days_archived'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add referral_count to users (tracks progress toward next reward)
    # Nullable to allow gradual rollout
    op.add_column('users', sa.Column('referral_count', sa.Integer(), nullable=True, server_default='0'))
    
    # Add referrer_notified_at to referrals (tracks when referrer was notified)
    op.add_column('referrals', sa.Column('referrer_notified_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('referrals', 'referrer_notified_at')
    op.drop_column('users', 'referral_count')
