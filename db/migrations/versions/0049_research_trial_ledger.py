"""Append-only hypothesis versions, trial definitions and terminal evidence.

Revision ID: 0049_research_trial_ledger
Revises: 0048_runtime_schema_bridge
"""
from alembic import op

revision = "0049_research_trial_ledger"
down_revision = "0048_runtime_schema_bridge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE research_hypotheses (
        hypothesis_id VARCHAR(64) PRIMARY KEY,
        parent_hypothesis_id VARCHAR(64) REFERENCES research_hypotheses(hypothesis_id),
        trial_family VARCHAR(128) NOT NULL,
        version INTEGER NOT NULL CHECK(version > 0),
        spec JSONB NOT NULL CHECK(jsonb_typeof(spec)='object'),
        content_hash VARCHAR(64) NOT NULL UNIQUE,
        created_by VARCHAR(128) NOT NULL,
        code_commit VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX ix_research_hypothesis_family ON research_hypotheses(trial_family,created_at)")
    op.execute("""CREATE TABLE research_experiments (
        experiment_id VARCHAR(64) PRIMARY KEY,
        hypothesis_id VARCHAR(64) NOT NULL REFERENCES research_hypotheses(hypothesis_id),
        parent_experiment_id VARCHAR(64) REFERENCES research_experiments(experiment_id),
        trial_family VARCHAR(128) NOT NULL,
        trial_fingerprint VARCHAR(64) NOT NULL,
        strategy_id VARCHAR(128) NOT NULL,
        strategy_version VARCHAR(64) NOT NULL,
        dataset_version VARCHAR(128) NOT NULL REFERENCES adaptive_dataset_versions(dataset_version),
        feature_version VARCHAR(128) NOT NULL REFERENCES adaptive_feature_versions(feature_version),
        specification JSONB NOT NULL CHECK(jsonb_typeof(specification)='object'),
        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_research_trial UNIQUE(trial_family,trial_fingerprint)
    )""")
    op.execute("CREATE INDEX ix_research_experiment_family ON research_experiments(trial_family,started_at)")
    op.execute("""CREATE TABLE research_experiment_results (
        experiment_id VARCHAR(64) PRIMARY KEY REFERENCES research_experiments(experiment_id),
        status VARCHAR(24) NOT NULL CHECK(status IN ('COMPLETED','FAILED','REJECTED')),
        result JSONB NOT NULL CHECK(jsonb_typeof(result)='object'),
        evidence_hash VARCHAR(64) NOT NULL,
        completed_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    op.execute("""CREATE FUNCTION reject_research_evidence_mutation() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'research_evidence_is_append_only';
        END $$""")
    for table in ("research_hypotheses", "research_experiments", "research_experiment_results"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_research_evidence_mutation()")
        op.execute(f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION reject_research_evidence_mutation()")
    op.execute("""CREATE FUNCTION enforce_research_trial_lineage() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$ DECLARE parent_family VARCHAR(128); parent_version INTEGER;
        BEGIN
            IF TG_TABLE_NAME='research_hypotheses' THEN
                IF NEW.parent_hypothesis_id IS NOT NULL THEN
                    SELECT trial_family,version INTO parent_family,parent_version
                        FROM research_hypotheses WHERE hypothesis_id=NEW.parent_hypothesis_id;
                    IF NEW.trial_family IS DISTINCT FROM parent_family OR NEW.version<>parent_version+1 THEN
                        RAISE EXCEPTION 'research_hypothesis_lineage_mismatch';
                    END IF;
                ELSIF NEW.version<>1 THEN
                    RAISE EXCEPTION 'research_root_version_must_be_one';
                END IF;
            ELSE
                SELECT trial_family INTO parent_family FROM research_hypotheses WHERE hypothesis_id=NEW.hypothesis_id;
                IF NEW.trial_family IS DISTINCT FROM parent_family THEN
                    RAISE EXCEPTION 'research_experiment_lineage_mismatch';
                END IF;
                IF NEW.parent_experiment_id IS NOT NULL THEN
                    SELECT trial_family INTO parent_family FROM research_experiments WHERE experiment_id=NEW.parent_experiment_id;
                    IF NEW.trial_family IS DISTINCT FROM parent_family THEN
                        RAISE EXCEPTION 'research_experiment_parent_mismatch';
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
    for table in ("research_hypotheses", "research_experiments"):
        op.execute(f"CREATE TRIGGER {table}_lineage BEFORE INSERT ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION enforce_research_trial_lineage()")


def downgrade() -> None:
    # A schema rollback must preserve history. Use a forward repair or restore
    # an approved database snapshot; downgrade cannot silently erase trials.
    raise RuntimeError("research_ledger_rollback_requires_preserved_evidence_restore")
