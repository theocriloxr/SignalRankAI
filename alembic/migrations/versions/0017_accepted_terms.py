"""Add accepted_terms column to users table

Revision ID: 0017_accepted_terms
Revises: 0016_managed_asset_last_analyzed
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_accepted_terms"
down_revision = "0016_managed_asset_last_analyzed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add accepted_terms with a server-side default of FALSE so existing rows
    # are populated immediately without a table rewrite on large deployments.
    op.add_column(
        "users",
        sa.Column(
            "accepted_terms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "accepted_terms")
