"""Add profile column for household profiles

Revision ID: 010_add_profile
Revises: 009_add_preference_type
Create Date: 2025-12-20

This migration adds a 'profile' column to support household profiles
(e.g., "Me", "Partner", "Joint") for multi-person tracking within
a single account.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '010_add_profile'
down_revision = '009_add_preference_type'
branch_labels = None
depends_on = None


def upgrade():
    """Add profile column to category_summaries, statement_periods, and statement_insights."""
    # Add profile column to category_summaries
    op.add_column('category_summaries', sa.Column('profile', sa.String(50), nullable=True))
    op.create_index('idx_summaries_user_profile', 'category_summaries', ['user_id', 'profile'])
    
    # Add profile column to statement_periods
    op.add_column('statement_periods', sa.Column('profile', sa.String(50), nullable=True))
    op.create_index('idx_stmt_period_user_profile', 'statement_periods', ['user_id', 'profile'])
    
    # Add profile column to statement_insights
    op.add_column('statement_insights', sa.Column('profile', sa.String(50), nullable=True))
    op.create_index('idx_stmt_insight_user_profile', 'statement_insights', ['user_id', 'profile'])


def downgrade():
    """Remove profile column from all tables."""
    # Remove from statement_insights
    op.drop_index('idx_stmt_insight_user_profile', table_name='statement_insights')
    op.drop_column('statement_insights', 'profile')
    
    # Remove from statement_periods
    op.drop_index('idx_stmt_period_user_profile', table_name='statement_periods')
    op.drop_column('statement_periods', 'profile')
    
    # Remove from category_summaries
    op.drop_index('idx_summaries_user_profile', table_name='category_summaries')
    op.drop_column('category_summaries', 'profile')

