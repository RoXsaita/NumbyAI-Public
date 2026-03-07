"""Add insights column to category_summaries

Revision ID: 008_add_category_insights
Revises: 007_add_budgets
Create Date: 2025-11-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "008_add_category_insights"
down_revision = "007_add_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("category_summaries", schema=None) as batch_op:
            batch_op.add_column(sa.Column("insights", sa.String(), nullable=True))
    else:
        op.add_column(
            "category_summaries", sa.Column("insights", sa.String(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("category_summaries", schema=None) as batch_op:
            batch_op.drop_column("insights")
    else:
        op.drop_column("category_summaries", "insights")

