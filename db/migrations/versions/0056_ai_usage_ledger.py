"""Append-only AI usage/cost ledger and deduplicated budget alerts.

Every OpenAI/Gemini call reserves its worst-case cost before the provider is
contacted and settles its estimated actual cost afterwards; a call refused by an
exhausted budget is recorded as ``skipped``. Spend is the settled cost plus every
reservation that never settled, so a crashed call stays counted.

There is deliberately no foreign key to ``users``: account merges move rows that
reference ``users.id`` and this ledger must never be rewritten.

Revision ID: 0056_ai_usage_ledger
Revises: 0055_user_renewal_default
"""
from alembic import op
from sqlalchemy import text

revision = "0056_ai_usage_ledger"
down_revision = "0055_user_renewal_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_usage_ledger (
        id BIGSERIAL PRIMARY KEY,
        call_id VARCHAR(64) NOT NULL,
        entry_kind VARCHAR(16) NOT NULL CHECK(entry_kind IN ('reservation','settlement','skipped')),
        created_at TIMESTAMP NOT NULL DEFAULT timezone('utc', now()),
        provider VARCHAR(32) NOT NULL,
        model VARCHAR(128) NOT NULL,
        workload VARCHAR(48) NOT NULL,
        task VARCHAR(96),
        user_id INTEGER,
        telegram_user_id BIGINT,
        prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK(prompt_tokens >= 0),
        completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK(completion_tokens >= 0),
        tokens_estimated BOOLEAN NOT NULL DEFAULT FALSE,
        cost_usd NUMERIC(14,6) NOT NULL DEFAULT 0 CHECK(cost_usd >= 0),
        pricing_source VARCHAR(32) NOT NULL,
        latency_ms DOUBLE PRECISION,
        outcome VARCHAR(48) NOT NULL,
        error VARCHAR(160),
        budget_scope VARCHAR(160),
        CONSTRAINT uq_ai_usage_ledger_call_entry UNIQUE(call_id, entry_kind)
    )""")
    op.execute("CREATE INDEX ix_ai_usage_ledger_created ON ai_usage_ledger(created_at)")
    op.execute("CREATE INDEX ix_ai_usage_ledger_provider ON ai_usage_ledger(provider, created_at)")
    op.execute("CREATE INDEX ix_ai_usage_ledger_workload ON ai_usage_ledger(workload, created_at)")
    op.execute("CREATE INDEX ix_ai_usage_ledger_user ON ai_usage_ledger(user_id, created_at) "
               "WHERE user_id IS NOT NULL")
    op.execute("""CREATE TABLE ai_budget_alerts (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT timezone('utc', now()),
        scope VARCHAR(160) NOT NULL,
        period VARCHAR(8) NOT NULL CHECK(period IN ('daily','monthly')),
        period_start TIMESTAMP NOT NULL,
        threshold NUMERIC(6,4) NOT NULL CHECK(threshold > 0),
        spend_usd NUMERIC(14,6) NOT NULL,
        limit_usd NUMERIC(14,6) NOT NULL,
        exhausted BOOLEAN NOT NULL DEFAULT FALSE,
        CONSTRAINT uq_ai_budget_alert UNIQUE(scope, period, period_start, threshold)
    )""")
    op.execute("CREATE INDEX ix_ai_budget_alerts_created ON ai_budget_alerts(created_at)")
    op.execute("""CREATE FUNCTION reject_ai_ledger_mutation() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'ai_usage_ledger_is_append_only';
        END $$""")
    for table in ("ai_usage_ledger", "ai_budget_alerts"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_ai_ledger_mutation()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION reject_ai_ledger_mutation()")
    op.execute("""CREATE FUNCTION enforce_ai_settlement_reservation() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.entry_kind = 'settlement' AND NOT EXISTS (
                SELECT 1 FROM ai_usage_ledger
                WHERE call_id = NEW.call_id AND entry_kind = 'reservation'
                  AND provider = NEW.provider AND model = NEW.model
            ) THEN
                RAISE EXCEPTION 'ai_settlement_without_reservation';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("CREATE TRIGGER ai_usage_ledger_settlement BEFORE INSERT ON ai_usage_ledger "
               "FOR EACH ROW EXECUTE FUNCTION enforce_ai_settlement_reservation()")


def downgrade() -> None:
    # Spend history is evidence. Only an empty ledger may be dropped; otherwise
    # restore an approved snapshot or repair forward.
    bind = op.get_bind()
    for table in ("ai_usage_ledger", "ai_budget_alerts"):
        if bind.execute(text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError("ai_usage_ledger_rollback_requires_preserved_evidence_restore")
    op.execute("DROP TABLE ai_usage_ledger")
    op.execute("DROP TABLE ai_budget_alerts")
    op.execute("DROP FUNCTION enforce_ai_settlement_reservation()")
    op.execute("DROP FUNCTION reject_ai_ledger_mutation()")
