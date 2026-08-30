"""staging certification ecosystem (v1.4.0)

Revision ID: 0035_staging_certification
Revises: 0034_production_integrity
Create Date: 2026-08-05

Safe forward migration: every DDL uses IF NOT EXISTS so the migration is
rerunnable and backward compatible for rolling deployments.  One head.
"""
from alembic import op

revision = "0035_staging_certification"
down_revision = "0034_production_integrity"
branch_labels = None
depends_on = None

_SIGNAL_COLUMNS = [
    ("pre_entry_high", "DOUBLE PRECISION"),
    ("pre_entry_low", "DOUBLE PRECISION"),
    ("post_entry_high", "DOUBLE PRECISION"),
    ("post_entry_low", "DOUBLE PRECISION"),
    ("mfe_price", "DOUBLE PRECISION"),
    ("mae_price", "DOUBLE PRECISION"),
    ("mfe_pct", "DOUBLE PRECISION"),
    ("mae_pct", "DOUBLE PRECISION"),
    ("entry_triggered_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("highest_price_seen", "DOUBLE PRECISION"),
    ("lowest_price_seen", "DOUBLE PRECISION"),
    ("monitoring_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("terminal_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("terminal_reason", "VARCHAR(128)"),
    ("lifecycle_state", "VARCHAR(32) NOT NULL DEFAULT 'created'"),
    ("geometry_reason", "VARCHAR(128)"),
    ("risk_distance", "DOUBLE PRECISION"),
    ("rr_tp1", "DOUBLE PRECISION"),
    ("rr_tp2", "DOUBLE PRECISION"),
    ("rr_tp3", "DOUBLE PRECISION"),
    ("rr_selected_target", "DOUBLE PRECISION"),
    ("final_rejection_stage", "VARCHAR(64)"),
    ("final_rejection_reason", "VARCHAR(255)"),
]

_USER_COLUMNS = [
    ("telegram_reachable", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("telegram_unreachable_reason", "VARCHAR(128)"),
    ("telegram_unreachable_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("notification_suppressed", "BOOLEAN NOT NULL DEFAULT FALSE"),
]


def _table(table: str, columns: list[tuple[str, str]], constraints: str = "") -> str:
    body = ",\n    ".join(f"{name} {typ}" for name, typ in columns)
    suffix = f",\n    {constraints}" if constraints else ""
    return f"CREATE TABLE IF NOT EXISTS {table} (\n    {body}{suffix}\n)"


def upgrade() -> None:
    # ── Signal lifecycle / MFE-MAE / geometry columns ──────────────────────
    for name, typ in _SIGNAL_COLUMNS:
        op.execute(f"ALTER TABLE signals ADD COLUMN IF NOT EXISTS {name} {typ}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_signals_lifecycle_state ON signals (lifecycle_state)")

    # ── User Telegram reachability (terminal unreachable state) ─────────────
    for name, typ in _USER_COLUMNS:
        op.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {typ}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_telegram_reachable ON users (telegram_reachable)")

    # ── Canonical instrument registry ───────────────────────────────────────
    op.execute(_table(
        "instruments",
        [
            ("instrument_id", "VARCHAR(128) PRIMARY KEY"),
            ("canonical_symbol", "VARCHAR(64) NOT NULL"),
            ("display_symbol", "VARCHAR(64) NOT NULL"),
            ("asset_class", "VARCHAR(32) NOT NULL"),
            ("instrument_type", "VARCHAR(32) NOT NULL"),
            ("market_type", "VARCHAR(32) NOT NULL DEFAULT 'cash'"),
            ("base_currency", "VARCHAR(16)"),
            ("quote_currency", "VARCHAR(16)"),
            ("settlement_currency", "VARCHAR(16)"),
            ("underlying", "VARCHAR(32)"),
            ("expiry", "TIMESTAMP WITHOUT TIME ZONE"),
            ("strike", "DOUBLE PRECISION"),
            ("option_type", "VARCHAR(16)"),
            ("contract_size", "DOUBLE PRECISION NOT NULL DEFAULT 1"),
            ("contract_multiplier", "DOUBLE PRECISION NOT NULL DEFAULT 1"),
            ("tick_size", "DOUBLE PRECISION"),
            ("quantity_step", "DOUBLE PRECISION"),
            ("minimum_quantity", "DOUBLE PRECISION"),
            ("minimum_notional", "DOUBLE PRECISION"),
            ("maximum_leverage", "DOUBLE PRECISION"),
            ("inverse_contract", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("trading_timezone", "VARCHAR(32) NOT NULL DEFAULT 'UTC'"),
            ("active", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("tradable", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("discovery_status", "VARCHAR(32) NOT NULL DEFAULT 'discovered'"),
            ("first_discovered_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("last_discovered_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("last_verified_at", "TIMESTAMP WITHOUT TIME ZONE"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_instruments_asset_class ON instruments (asset_class)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_instruments_active ON instruments (active)")

    op.execute(_table(
        "provider_instruments",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("provider", "VARCHAR(64) NOT NULL"),
            ("venue", "VARCHAR(64) NOT NULL"),
            ("provider_symbol", "VARCHAR(64) NOT NULL"),
            ("provider_instrument_id", "VARCHAR(128)"),
            ("canonical_instrument_id", "VARCHAR(128)"),
            ("market_status", "VARCHAR(32) NOT NULL DEFAULT 'active'"),
            ("trading_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("data_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("execution_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("historical_candles_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("live_quotes_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("order_book_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("trades_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("funding_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("open_interest_supported", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("provider_metadata", "JSONB"),
            ("first_seen_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("last_seen_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("last_successful_refresh_at", "TIMESTAMP WITHOUT TIME ZONE"),
            ("delisted_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ],
        "CONSTRAINT uq_provider_instrument UNIQUE (provider, venue, provider_instrument_id)",
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_provider_instruments_canonical ON provider_instruments (canonical_instrument_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_provider_instruments_provider ON provider_instruments (provider)")

    op.execute(_table(
        "instrument_discovery_runs",
        [
            ("run_id", "BIGSERIAL PRIMARY KEY"),
            ("provider", "VARCHAR(64) NOT NULL"),
            ("started_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("duration_ms", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
            ("discovered", "INTEGER NOT NULL DEFAULT 0"),
            ("created", "INTEGER NOT NULL DEFAULT 0"),
            ("updated", "INTEGER NOT NULL DEFAULT 0"),
            ("unchanged", "INTEGER NOT NULL DEFAULT 0"),
            ("mapping_failures", "INTEGER NOT NULL DEFAULT 0"),
            ("state", "VARCHAR(24) NOT NULL DEFAULT 'ok'"),
            ("reason", "VARCHAR(255)"),
        ],
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_discovery_runs_provider ON instrument_discovery_runs (provider, started_at)")

    op.execute(_table(
        "instrument_discovery_failures",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("provider", "VARCHAR(64) NOT NULL"),
            ("provider_symbol", "VARCHAR(64)"),
            ("error_type", "VARCHAR(64)"),
            ("error_detail", "VARCHAR(255)"),
            ("occurred_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))

    op.execute(_table(
        "instrument_certifications",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("instrument_id", "VARCHAR(128) NOT NULL"),
            ("readiness_state", "VARCHAR(32) NOT NULL DEFAULT 'discovered'"),
            ("evidence", "JSONB"),
            ("certified_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_instrument_cert UNIQUE (instrument_id)",
    ))

    # ── Entitlement catalogue ───────────────────────────────────────────────
    op.execute(_table(
        "subscription_products",
        [
            ("product_id", "VARCHAR(64) PRIMARY KEY"),
            ("tier", "VARCHAR(24) NOT NULL"),
            ("display_name", "VARCHAR(128) NOT NULL"),
            ("duration_days", "INTEGER NOT NULL"),
            ("active", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "subscription_prices",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("product_id", "VARCHAR(64) NOT NULL"),
            ("currency", "VARCHAR(8) NOT NULL DEFAULT 'NGN'"),
            ("price_kobo", "BIGINT NOT NULL"),
            ("effective_from", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("effective_until", "TIMESTAMP WITHOUT TIME ZONE"),
        ],
        "CONSTRAINT uq_product_price UNIQUE (product_id, currency, effective_from)",
    ))
    op.execute(_table(
        "subscription_entitlements",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("entitlement_key", "VARCHAR(64) NOT NULL"),
            ("tier", "VARCHAR(24) NOT NULL"),
            ("enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("limit_value", "DOUBLE PRECISION"),
            ("period", "VARCHAR(16)"),
            ("priority", "INTEGER NOT NULL DEFAULT 0"),
            ("configuration", "JSONB"),
            ("effective_from", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("effective_until", "TIMESTAMP WITHOUT TIME ZONE"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
        ],
        "CONSTRAINT uq_entitlement UNIQUE (entitlement_key, tier, version)",
    ))
    op.execute(_table(
        "usage_counters",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("user_id", "BIGINT NOT NULL"),
            ("counter_key", "VARCHAR(64) NOT NULL"),
            ("period_key", "VARCHAR(32) NOT NULL"),
            ("value", "BIGINT NOT NULL DEFAULT 0"),
            ("updated_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_usage_counter UNIQUE (user_id, counter_key, period_key)",
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_usage_counters_user ON usage_counters (user_id)")

    # ── ML governance ───────────────────────────────────────────────────────
    op.execute(_table(
        "model_registry",
        [
            ("model_id", "VARCHAR(64) PRIMARY KEY"),
            ("model_name", "VARCHAR(64) NOT NULL"),
            ("status", "VARCHAR(24) NOT NULL DEFAULT 'candidate'"),
            ("version", "VARCHAR(64)"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_model_registry_name UNIQUE (model_name)",
    ))
    op.execute(_table(
        "model_versions",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("model_id", "VARCHAR(64) NOT NULL"),
            ("version", "VARCHAR(64) NOT NULL"),
            ("artifact_hash", "VARCHAR(64)"),
            ("feature_schema_version", "VARCHAR(64)"),
            ("label_schema_version", "VARCHAR(64)"),
            ("dataset_version", "VARCHAR(64)"),
            ("status", "VARCHAR(24) NOT NULL DEFAULT 'candidate'"),
            ("trained_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_model_version UNIQUE (model_id, version)",
    ))
    op.execute(_table(
        "model_metrics",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("model_version_id", "BIGINT NOT NULL"),
            ("metric_key", "VARCHAR(64) NOT NULL"),
            ("metric_value", "DOUBLE PRECISION"),
            ("recorded_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "model_promotions",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("model_version_id", "BIGINT NOT NULL"),
            ("decision", "VARCHAR(24) NOT NULL"),
            ("reasons", "JSONB"),
            ("promoted_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "feature_definitions",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("feature_name", "VARCHAR(128) NOT NULL"),
            ("feature_version", "VARCHAR(32) NOT NULL DEFAULT '1'"),
            ("data_type", "VARCHAR(32) NOT NULL DEFAULT 'float'"),
            ("feature_order", "INTEGER NOT NULL DEFAULT 0"),
            ("normalization", "VARCHAR(32) NOT NULL DEFAULT 'none'"),
            ("missing_policy", "VARCHAR(32) NOT NULL DEFAULT 'missing'"),
            ("provider", "VARCHAR(64)"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_feature_definition UNIQUE (feature_name, feature_version)",
    ))
    op.execute(_table(
        "dataset_versions",
        [
            ("dataset_version", "VARCHAR(64) PRIMARY KEY"),
            ("feature_schema_version", "VARCHAR(64)"),
            ("label_version", "VARCHAR(64)"),
            ("row_count", "INTEGER NOT NULL DEFAULT 0"),
            ("hash", "VARCHAR(64)"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "label_versions",
        [
            ("label_version", "VARCHAR(64) PRIMARY KEY"),
            ("label_spec", "JSONB"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "drift_events",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("model_version_id", "BIGINT"),
            ("drift_type", "VARCHAR(64) NOT NULL"),
            ("severity", "VARCHAR(24) NOT NULL DEFAULT 'unknown'"),
            ("details", "JSONB"),
            ("occurred_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))

    # ── Strategy governance ─────────────────────────────────────────────────
    op.execute(_table(
        "strategy_versions",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("strategy_id", "VARCHAR(64) NOT NULL"),
            ("version", "VARCHAR(32) NOT NULL DEFAULT '1'"),
            ("family", "VARCHAR(64)"),
            ("status", "VARCHAR(24) NOT NULL DEFAULT 'active'"),
            ("certification", "VARCHAR(32) NOT NULL DEFAULT 'declared'"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_strategy_version UNIQUE (strategy_id, version)",
    ))
    op.execute(_table(
        "strategy_version_metrics",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("strategy_version_id", "BIGINT NOT NULL"),
            ("metric_key", "VARCHAR(64) NOT NULL"),
            ("metric_value", "DOUBLE PRECISION"),
            ("sample_size", "INTEGER NOT NULL DEFAULT 0"),
            ("recorded_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute(_table(
        "strategy_quarantines",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("strategy_id", "VARCHAR(64) NOT NULL"),
            ("reason", "VARCHAR(255) NOT NULL"),
            ("quarantined_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("released_at", "TIMESTAMP WITHOUT TIME ZONE"),
        ],
    ))

    # ── Trading profiles + portfolio exposure ───────────────────────────────
    op.execute(_table(
        "user_trader_profiles",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("user_id", "BIGINT NOT NULL"),
            ("trader_style", "VARCHAR(32) NOT NULL DEFAULT 'discretionary'"),
            ("risk_tolerance", "VARCHAR(24) NOT NULL DEFAULT 'moderate'"),
            ("max_risk_per_trade_pct", "DOUBLE PRECISION NOT NULL DEFAULT 1.0"),
            ("max_daily_risk_pct", "DOUBLE PRECISION NOT NULL DEFAULT 3.0"),
            ("max_drawdown_pct", "DOUBLE PRECISION NOT NULL DEFAULT 15.0"),
            ("preferred_asset_classes", "JSONB"),
            ("preferred_timeframes", "JSONB"),
            ("blocked_assets", "JSONB"),
            ("updated_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_trader_profile UNIQUE (user_id)",
    ))
    op.execute(_table(
        "portfolio_exposure_snapshots",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("user_id", "BIGINT NOT NULL"),
            ("snapshot_type", "VARCHAR(32) NOT NULL"),
            ("payload", "JSONB"),
            ("recorded_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolio_snapshots_user ON portfolio_exposure_snapshots (user_id, recorded_at)")

    # ── Outcome corrections (compensating, auditable, idempotent) ───────────
    op.execute(_table(
        "outcome_corrections",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("signal_id", "VARCHAR(36) NOT NULL"),
            ("original_outcome", "VARCHAR(32) NOT NULL"),
            ("corrected_outcome", "VARCHAR(32) NOT NULL"),
            ("correction_reason", "VARCHAR(255) NOT NULL"),
            ("correction_evidence", "JSONB"),
            ("correction_version", "INTEGER NOT NULL DEFAULT 1"),
            ("correction_source", "VARCHAR(64) NOT NULL DEFAULT 'system_reconciliation'"),
            ("compensating_ledger_entry_id", "BIGINT"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_outcome_correction UNIQUE (signal_id, corrected_outcome, correction_version)",
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_outcome_corrections_signal ON outcome_corrections (signal_id)")

    # ── Terminal notification suppressions (duplicate-thesis) ───────────────
    op.execute(_table(
        "notification_suppressions",
        [
            ("id", "BIGSERIAL PRIMARY KEY"),
            ("notification_key", "VARCHAR(255) NOT NULL"),
            ("canonical_notification_id", "BIGINT"),
            ("reason", "VARCHAR(128) NOT NULL"),
            ("terminal", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("created_at", "TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()"),
        ],
        "CONSTRAINT uq_notification_suppression UNIQUE (notification_key)",
    ))
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_suppressions_key ON notification_suppressions (notification_key)")


def downgrade() -> None:
    # Non-destructive policy: drop only the new tables/columns introduced here.
    for table in (
        "notification_suppressions",
        "outcome_corrections",
        "portfolio_exposure_snapshots",
        "user_trader_profiles",
        "strategy_quarantines",
        "strategy_version_metrics",
        "strategy_versions",
        "drift_events",
        "label_versions",
        "dataset_versions",
        "feature_definitions",
        "model_promotions",
        "model_metrics",
        "model_versions",
        "model_registry",
        "usage_counters",
        "subscription_entitlements",
        "subscription_prices",
        "subscription_products",
        "instrument_certifications",
        "instrument_discovery_failures",
        "instrument_discovery_runs",
        "provider_instruments",
        "instruments",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for name, _typ in _SIGNAL_COLUMNS:
        op.execute(f"ALTER TABLE signals DROP COLUMN IF EXISTS {name}")
    for name, _typ in _USER_COLUMNS:
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {name}")
    op.execute("DROP INDEX IF EXISTS ix_users_telegram_reachable")
    op.execute("DROP INDEX IF EXISTS ix_signals_lifecycle_state")
