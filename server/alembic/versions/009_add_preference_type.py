"""Add preference_type column to categorization_preferences

Revision ID: 009_add_preference_type
Revises: 008_add_category_insights
Create Date: 2025-12-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009_add_preference_type"
down_revision = "008_add_category_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add preference_type column with default 'categorization' for existing rows."""
    op.add_column(
        "categorization_preferences",
        sa.Column(
            "preference_type",
            sa.String(20),
            nullable=False,
            server_default="categorization"
        )
    )
    
    # Create index for filtering by preference_type
    op.create_index(
        "idx_cat_pref_user_type",
        "categorization_preferences",
        ["user_id", "preference_type"],
    )


def downgrade() -> None:
    """Remove preference_type column."""
    op.drop_index("idx_cat_pref_user_type", table_name="categorization_preferences")
    op.drop_column("categorization_preferences", "preference_type")

