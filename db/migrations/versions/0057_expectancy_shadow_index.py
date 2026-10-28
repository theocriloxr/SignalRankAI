"""Index expectancy-shadow rows without blocking decision writes.

Candidates refused only for missing expectancy evidence are recorded as
``decision_log`` rows with ``layer='expectancy'`` (engine/expectancy_shadow.py).
Their tracker and the evidence query must never scan the whole decision log.

Revision ID: 0057_expectancy_shadow_index
Revises: 0056_ai_usage_ledger
"""
from alembic import op

revision = "0057_expectancy_shadow_index"
down_revision = "0056_ai_usage_ledger"
branch_labels = None
depends_on = None

CREATE_SQL = """CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_decision_log_expectancy_shadow_created
    ON decision_log (created_at)
    WHERE decision='rejected' AND meta->>'layer'='expectancy'"""
VALIDATE_SQL = """DO $expectancy_index$
DECLARE index_state RECORD;
BEGIN
    SELECT i.indisvalid,i.indisready,i.indnkeyatts,a.amname,
        pg_get_indexdef(i.indexrelid,1,true) AS column_name,
        regexp_replace(pg_get_expr(i.indpred,i.indrelid),'::text|[()[:space:]]','','g') AS predicate
    INTO index_state
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_am a ON a.oid=c.relam
    WHERE i.indrelid='decision_log'::regclass AND c.relname='ix_decision_log_expectancy_shadow_created';
    IF NOT FOUND OR NOT index_state.indisvalid OR NOT index_state.indisready
        OR index_state.indnkeyatts<>1 OR index_state.amname<>'btree'
        OR index_state.column_name<>'created_at'
        OR index_state.predicate IS DISTINCT FROM 'decision=''rejected''ANDmeta->>''layer''=''expectancy'''
    THEN RAISE EXCEPTION 'expectancy_shadow_index_invalid_or_definition_mismatch';
    END IF;
END; $expectancy_index$"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(CREATE_SQL)
        # A failed concurrent build leaves an invalid index; never claim it works.
        op.execute(VALIDATE_SQL)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_decision_log_expectancy_shadow_created")
