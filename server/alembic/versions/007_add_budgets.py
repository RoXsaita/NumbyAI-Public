"""Add budgets table

Revision ID: 007_add_budgets
Revises: 006_add_categorization_preferences
Create Date: 2025-05-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_add_budgets"
down_revision = "006_add_categorization_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        op.create_table(
            "budgets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("month_year", sa.String(7), nullable=True),  # NULL = default budget
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, default="USD"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )
    else:
        op.create_table(
            "budgets",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("month_year", sa.String(7), nullable=True),  # NULL = default budget
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, default="USD"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )

    # Index for fast lookups by user + category + month
    op.create_index(
        "idx_budget_user_category_month",
        "budgets",
        ["user_id", "category", "month_year"],
        unique=True,
    )
    op.create_index(
        "idx_budget_user_category",
        "budgets",
        ["user_id", "category"],
    )


def downgrade() -> None:
    op.drop_index("idx_budget_user_category", table_name="budgets")
    op.drop_index("idx_budget_user_category_month", table_name="budgets")
    op.drop_table("budgets")

