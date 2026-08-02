"""durable multisource ML learning and runtime activation

Revision ID: 0033_ml_learning_runtime
Revises: 0032_referral_reliability
Create Date: 2026-08-02
"""

from alembic import op

revision = "0033_ml_learning_runtime"
down_revision = "0032_referral_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_model_artifacts (
            id BIGSERIAL PRIMARY KEY,
            model_name VARCHAR(64) NOT NULL DEFAULT 'primary',
            model_version VARCHAR(64) NOT NULL,
            feature_schema_version VARCHAR(64) NOT NULL DEFAULT '1',
            artifact_hash_sha256 VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            trained_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ml_model_artifacts_active_name
        ON ml_model_artifacts (model_name)
        WHERE is_active = TRUE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ml_model_artifacts_name_created
        ON ml_model_artifacts (model_name, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ml_model_artifacts_hash
        ON ml_model_artifacts (artifact_hash_sha256)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ml_model_artifacts_hash")
    op.execute("DROP INDEX IF EXISTS ix_ml_model_artifacts_name_created")
    op.execute("DROP INDEX IF EXISTS uq_ml_model_artifacts_active_name")
    op.execute("DROP TABLE IF EXISTS ml_model_artifacts")
