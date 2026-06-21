"""Add strategy_name, asset_class, regime columns to outcomes table.

Revision ID: 0016_add_strategy_regime_columns
Revises: 0015_add_users_timezone
Create Date: 2026-06-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016_add_strategy_regime_columns'
down_revision = '0015_add_users_timezone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns to outcomes table for Phase 2 ML weighting."""
    # Add strategy_name column
    op.add_column('outcomes', sa.Column('strategy_name', sa.String(64), nullable=True))
    
    # Add asset_class column (crypto, forex, stock)
    op.add_column('outcomes', sa.Column('asset_class', sa.String(32), nullable=True))
    
    # Add regime column (TRENDING, RANGING, VOLATILE)
    op.add_column('outcomes', sa.Column('regime', sa.String(32), nullable=True))
    
    # Create index on strategy_name, regime, created_at for fast queries
    op.create_index(
        'idx_outcomes_strategy_regime',
        'outcomes',
        ['strategy_name', 'regime', 'created_at'],
        postgresql_using='btree'
    )
    
    # Create index on asset_class, regime for asset-class-specific queries
    op.create_index(
        'idx_outcomes_asset_class_regime',
        'outcomes',
        ['asset_class', 'regime', 'created_at'],
        postgresql_using='btree'
    )


def downgrade() -> None:
    """Remove columns from outcomes table."""
    op.drop_index('idx_outcomes_asset_class_regime', table_name='outcomes')
    op.drop_index('idx_outcomes_strategy_regime', table_name='outcomes')
    op.drop_column('outcomes', 'regime')
    op.drop_column('outcomes', 'asset_class')
    op.drop_column('outcomes', 'strategy_name')
