"""Create managed_assets table for admin-pinned asset universe

Revision ID: 0015_managed_assets
Revises: 0014_create_decision_log_table
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_managed_assets"
down_revision = "0014_create_decision_log_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False, server_default="crypto"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_managed_assets_symbol", "managed_assets", ["symbol"], unique=True)
    op.create_index("ix_managed_assets_is_active", "managed_assets", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_managed_assets_is_active", table_name="managed_assets")
    op.drop_index("ix_managed_assets_symbol", table_name="managed_assets")
    op.drop_table("managed_assets")
