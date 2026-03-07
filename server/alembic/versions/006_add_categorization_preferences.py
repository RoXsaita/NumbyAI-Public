"""Add categorization_preferences table

Revision ID: 006_add_categorization_preferences
Revises: 005_statement_periods
Create Date: 2025-05-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006_add_categorization_preferences"
down_revision = "005_statement_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        op.create_table(
            "categorization_preferences",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("bank_name", sa.String(100), nullable=True, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("rule", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, default=0),
            sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )
    else:
        op.create_table(
            "categorization_preferences",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("bank_name", sa.String(100), nullable=True, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("rule", postgresql.JSONB(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, default=0),
            sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )

    op.create_index(
        "idx_cat_pref_user_bank",
        "categorization_preferences",
        ["user_id", "bank_name"],
    )
    op.create_index(
        "idx_cat_pref_user_priority",
        "categorization_preferences",
        ["user_id", "priority"],
    )


def downgrade() -> None:
    op.drop_index("idx_cat_pref_user_priority", table_name="categorization_preferences")
    op.drop_index("idx_cat_pref_user_bank", table_name="categorization_preferences")
    op.drop_table("categorization_preferences")
