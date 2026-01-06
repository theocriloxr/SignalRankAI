"""Add signal corrections table

Revision ID: 0011_signal_corrections
Revises: 0010
Create Date: 2026-01-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '0011_signal_corrections'
down_revision = '0010_bonus_days_archived'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'signal_corrections',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('original_signal_id', sa.String(length=36), nullable=False),
        sa.Column('corrected_signal_id', sa.String(length=36), nullable=True),
        sa.Column('error_type', sa.String(length=64), nullable=False),
        sa.Column('error_description', sa.Text(), nullable=False),
        sa.Column('users_notified', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['original_signal_id'], ['signals.signal_id'], ),
        sa.ForeignKeyConstraint(['corrected_signal_id'], ['signals.signal_id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signal_corrections_original_signal_id'), 'signal_corrections', ['original_signal_id'], unique=False)
    op.create_index(op.f('ix_signal_corrections_corrected_signal_id'), 'signal_corrections', ['corrected_signal_id'], unique=False)
    op.create_index(op.f('ix_signal_corrections_error_type'), 'signal_corrections', ['error_type'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_signal_corrections_error_type'), table_name='signal_corrections')
    op.drop_index(op.f('ix_signal_corrections_corrected_signal_id'), table_name='signal_corrections')
    op.drop_index(op.f('ix_signal_corrections_original_signal_id'), table_name='signal_corrections')
    op.drop_table('signal_corrections')
