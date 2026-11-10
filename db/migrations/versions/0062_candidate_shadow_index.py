"""Index challenger forward-proof rows (10 Nov 2026).

``ml/candidate_forward.evaluate_candidate_forward_evidence`` reads the
``ml_rejected_signals`` rows a challenger model was shadow-tested on. It
filtered two JSON keys with no index, so the read scanned every row since the
challenger was trained and timed out (production: ``/ml_candidate`` failed with
TimeoutError, and the training lease could not be evaluated). This partial
index on decision_log (artifact hash, created_at) for candidate-shadow rows serves that
query, now written with literal keys. Built CONCURRENTLY; index only.

Revision ID: 0062_candidate_shadow_index
Revises: 0061_tracked_shadow_index
"""
from alembic import op

revision = "0062_candidate_shadow_index"
down_revision = "0061_tracked_shadow_index"
branch_labels = None
depends_on = None

# ml_rejected_signals is a view over decision_log (0046), so the index lives on
# decision_log and the query reads decision_log with the same expressions.
CREATE_SQL = """CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ml_rejected_candidate_shadow
    ON decision_log ((meta->'features'->>'candidate_artifact_hash_sha256'), created_at)
    WHERE decision = 'rejected' AND meta->>'layer' = 'ml'
      AND meta->'features'->>'rejection_type' = 'candidate_shadow'"""
VALIDATE_SQL = """DO $candidate_index$
DECLARE index_state RECORD;
BEGIN
    SELECT i.indisvalid, i.indisready, a.amname
    INTO index_state
    FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_am a ON a.oid=c.relam
    WHERE i.indrelid='decision_log'::regclass AND c.relname='ix_ml_rejected_candidate_shadow';
    IF NOT FOUND OR NOT index_state.indisvalid OR NOT index_state.indisready OR index_state.amname<>'btree'
    THEN RAISE EXCEPTION 'candidate_shadow_index_invalid_or_definition_mismatch';
    END IF;
END; $candidate_index$"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(CREATE_SQL)
        op.execute(VALIDATE_SQL)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_ml_rejected_candidate_shadow")
