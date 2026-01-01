"""market data cache tables

Revision ID: 0007_market_data_cache
Revises: 0006_bigint_telegram_ids
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa


revision = "0007_market_data_cache"
down_revision = "0006_bigint_telegram_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_ticks",
        sa.Column("symbol", sa.String(length=32), primary_key=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("event_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "market_candles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open_time_ms", sa.BigInteger(), nullable=False),
        sa.Column("close_time_ms", sa.BigInteger(), nullable=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("symbol", "timeframe", "open_time_ms", name="uq_market_candles_symbol_tf_open"),
    )
    op.create_index("ix_market_candles_symbol", "market_candles", ["symbol"], unique=False)
    op.create_index("ix_market_candles_timeframe", "market_candles", ["timeframe"], unique=False)
    op.create_index("ix_market_candles_open_time_ms", "market_candles", ["open_time_ms"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_market_candles_open_time_ms", table_name="market_candles")
    op.drop_index("ix_market_candles_timeframe", table_name="market_candles")
    op.drop_index("ix_market_candles_symbol", table_name="market_candles")
    op.drop_table("market_candles")
    op.drop_table("market_ticks")
