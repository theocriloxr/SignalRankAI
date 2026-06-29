"""Active Signal Registry Migration

Creates active_signals table for tracking active signals per user with message updates.

This table enables:
- Outcome tracking (entry_hit, tp1_hit, tp2_hit, tp3_hit, sl_hit, expiry)
- Message updates (message_id, chat_id)
- Signal replacement when same fingerprint appears

Revision ID: 0015
Create Date: 2024-xx-xx

Table: active_signals
- signal_id (PK)
- fingerprint (index for dedup check)
- asset (index)
- direction 
- timeframe
- status (NEW, ACTIVE, ENTRY_HIT, TP1, TP2, TP3, SL, EXPIRED, ARCHIVED)
- message_id (for edits)
- chat_id (for edits)
- user_id (index for user signals)
- entry_hit (datetime)
- tp1_hit (datetime)
- tp2_hit (datetime)
- tp3_hit (datetime)
- sl_hit (datetime)
- expiry (datetime)
- created_at
- updated_at
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '0015_active_signal_registry'
down_revision = '0014_decision_log_and_ml_rejected'  # Update this to your latest revision
depends_on = None


def upgrade() -> None:
    # Create active_signals table
    op.create_table(
        'active_signals',
        sa.Column('signal_id', sa.String(36), primary_key=True),
        sa.Column('fingerprint', sa.String(128), nullable=False, index=True),
        sa.Column('asset', sa.String(32), nullable=False, index=True),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('timeframe', sa.String(8), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='NEW'),
        sa.Column('message_id', sa.BigInteger, nullable=True),
        sa.Column('chat_id', sa.BigInteger, nullable=True, index=True),
        sa.Column('user_id', sa.Integer, nullable=False, index=True),
        sa.Column('entry_hit', sa.DateTime, nullable=True),
        sa.Column('tp1_hit', sa.DateTime, nullable=True),
        sa.Column('tp2_hit', sa.DateTime, nullable=True),
        sa.Column('tp3_hit', sa.DateTime, nullable=True),
        sa.Column('sl_hit', sa.DateTime, nullable=True),
        sa.Column('expiry', sa.DateTime, nullable=True),
        sa.Column('signal_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Add indexes for common queries
    op.create_index('ix_active_signals_user_status', 'active_signals', ['user_id', 'status'])
    op.create_index('ix_active_signals_asset_status', 'active_signals', ['asset', 'status'])
    op.create_index('ix_active_signals_status', 'active_signals', ['status'])
    
    # Create unique constraint for user + signal
    op.create_unique_constraint(
        'uq_active_signals_user_signal',
        'active_signals',
        ['user_id', 'signal_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_active_signals_user_signal', 'active_signals')
    op.drop_index('ix_active_signals_status', 'active_signals')
    op.drop_index('ix_active_signals_asset_status', 'active_signals')
    op.drop_index('ix_active_signals_user_status', 'active_signals')
    op.drop_table('active_signals')
