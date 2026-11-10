"""User trade ideas: analyse a trade a user plans to take and track how it ends (10 Nov 2026).

Owner request: "add a feature where users can input the details of a trade they
want to take (asset, entry, TP and SL with every other detail); the bot analyses
it and tells them its possibility, and it also learns from those signals."

One row per submitted idea from Telegram (/check_trade), the website/app or the API.
``analysis`` holds what the user was shown; ``features`` the market features
measured at submission (used as low-weight, fit-only training rows once the idea
resolves). The tracker fills ``outcome``/``outcome_r``/``resolved_at`` and the
notifier ``notified_at``. Own table, so ideas never mix with engine decisions
in decision_log statistics.

Revision ID: 0063_user_trade_ideas
Revises: 0062_candidate_shadow_index
"""
from alembic import op

revision = "0063_user_trade_ideas"
down_revision = "0062_candidate_shadow_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_trade_ideas (
            id BIGSERIAL PRIMARY KEY,
            idea_id VARCHAR(36) NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            asset VARCHAR(32) NOT NULL,
            asset_class VARCHAR(16),
            timeframe VARCHAR(8) NOT NULL,
            direction VARCHAR(8) NOT NULL,
            order_type VARCHAR(32),
            entry DOUBLE PRECISION NOT NULL,
            stop_loss DOUBLE PRECISION NOT NULL,
            take_profit JSONB NOT NULL DEFAULT '[]'::jsonb,
            price_at_submit DOUBLE PRECISION,
            probability DOUBLE PRECISION,
            verdict VARCHAR(16),
            analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
            features JSONB NOT NULL DEFAULT '{}'::jsonb,
            source VARCHAR(16) NOT NULL DEFAULT 'web',
            notes TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'tracking',
            entry_touched_at TIMESTAMP WITHOUT TIME ZONE,
            outcome VARCHAR(32),
            outcome_r DOUBLE PRECISION,
            resolved_at TIMESTAMP WITHOUT TIME ZONE,
            notified_at TIMESTAMP WITHOUT TIME ZONE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_trade_ideas_user_time ON user_trade_ideas(user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_trade_ideas_tracking ON user_trade_ideas(id) WHERE status = 'tracking'")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_trade_ideas_unnotified ON user_trade_ideas(id) "
        "WHERE status = 'resolved' AND notified_at IS NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_trade_ideas_asset_resolved ON user_trade_ideas(asset, resolved_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_trade_ideas")
