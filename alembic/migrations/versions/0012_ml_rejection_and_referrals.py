"""Add ml_rejected_signals table and referral system enhancements

Revision ID: 0012_ml_rejection_and_referrals
Revises: 0011_add_ml_probability
Create Date: 2026-01-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0012_ml_rejection_and_referrals'
down_revision = '0012_merge_0011_heads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add premium_until column to users table
    op.add_column('users', sa.Column('premium_until', sa.DateTime(), nullable=True))
    
    # Create ml_rejected_signals table
    op.create_table(
        'ml_rejected_signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset', sa.String(32), nullable=False),
        sa.Column('timeframe', sa.String(8), nullable=False),
        sa.Column('direction', sa.String(8), nullable=False),
        sa.Column('entry', sa.Float(), nullable=False),
        sa.Column('stop_loss', sa.Float(), nullable=False),
        sa.Column('take_profit', sa.Text(), nullable=False),
        sa.Column('ml_probability', sa.Float(), nullable=False),
        sa.Column('rejection_reason', sa.String(128), nullable=False),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('actual_outcome', sa.String(32), nullable=True),
        sa.Column('outcome_tracked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ml_rejected_signals_asset', 'ml_rejected_signals', ['asset'])
    op.create_index('ix_ml_rejected_signals_timeframe', 'ml_rejected_signals', ['timeframe'])
    op.create_index('ix_ml_rejected_signals_actual_outcome', 'ml_rejected_signals', ['actual_outcome'])
    
    # Add referral tracking columns to existing referrals table
    op.add_column('referrals', sa.Column('is_successful', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('referrals', sa.Column('reward_applied', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('referrals', sa.Column('successful_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove referral tracking columns
    op.drop_column('referrals', 'successful_at')
    op.drop_column('referrals', 'reward_applied')
    op.drop_column('referrals', 'is_successful')

    # Drop ml_rejected_signals table
    op.drop_table('ml_rejected_signals')

    # Remove premium_until column from users table
    op.drop_column('users', 'premium_until')
