"""create partitioned time-series tables for candles and outcomes

Revision ID: 0022_timeseries_partition_tables
Revises: 0021_auto_cap_default_unlimited
Create Date: 2026-04-08
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0022_timeseries_partition_tables"
down_revision = "0021_auto_cap_default_unlimited"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partitioned market candles table for high-volume ingest.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_candles_ts (
            id BIGSERIAL,
            symbol VARCHAR(32) NOT NULL,
            timeframe VARCHAR(8) NOT NULL,
            open_time_ms BIGINT NOT NULL,
            close_time_ms BIGINT,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL DEFAULT 0,
            is_final BOOLEAN NOT NULL DEFAULT FALSE,
            event_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, event_at)
        ) PARTITION BY RANGE (event_at);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes_ts (
            id BIGSERIAL,
            signal_id VARCHAR(36) NOT NULL,
            status VARCHAR(16) NOT NULL,
            r_multiple DOUBLE PRECISION,
            percent DOUBLE PRECISION,
            opened_at TIMESTAMP,
            closed_at TIMESTAMP,
            duration_seconds INTEGER,
            event_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, event_at)
        ) PARTITION BY RANGE (event_at);
        """
    )

    # Create partitions for current month and next two months.
    op.execute(
        """
        DO $$
        DECLARE
            i INTEGER;
            start_ts DATE;
            end_ts DATE;
            part_name TEXT;
        BEGIN
            FOR i IN 0..2 LOOP
                start_ts := date_trunc('month', now())::date + (i || ' month')::interval;
                end_ts := date_trunc('month', now())::date + ((i + 1) || ' month')::interval;
                part_name := 'market_candles_ts_' || to_char(start_ts, 'YYYYMM');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF market_candles_ts FOR VALUES FROM (%L) TO (%L);',
                    part_name,
                    start_ts,
                    end_ts
                );

                part_name := 'outcomes_ts_' || to_char(start_ts, 'YYYYMM');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF outcomes_ts FOR VALUES FROM (%L) TO (%L);',
                    part_name,
                    start_ts,
                    end_ts
                );
            END LOOP;
        END $$;
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_market_candles_ts_symbol_tf_event_at ON market_candles_ts(symbol, timeframe, event_at DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outcomes_ts_signal_status_event_at ON outcomes_ts(signal_id, status, event_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outcomes_ts CASCADE;")
    op.execute("DROP TABLE IF EXISTS market_candles_ts CASCADE;")
