"""Add categorization_rules table for merchant → category mappings

Revision ID: 012_add_categorization_rules
Revises: 011_add_transactions
Create Date: 2025-01-XX

This migration adds a 'categorization_rules' table to store learned merchant
patterns that map to categories. Rules are learned automatically when a merchant
is categorized the same way 3+ times.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '012_add_categorization_rules'
down_revision = '011_add_transactions'
branch_labels = None
depends_on = None


def upgrade():
    """Create categorization_rules table with merchant pattern matching."""
    # Detect database type
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    
    if is_sqlite:
        # SQLite version
        op.create_table(
            'categorization_rules',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('merchant_pattern', sa.String(200), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('confidence_score', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    else:
        # PostgreSQL version
        op.create_table(
            'categorization_rules',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('merchant_pattern', sa.String(200), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('confidence_score', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    
    # Create indexes for fast lookups
    op.create_index('ix_categorization_rules_user_id', 'categorization_rules', ['user_id'])
    op.create_index('ix_categorization_rules_user_merchant', 'categorization_rules', ['user_id', 'merchant_pattern'])
    op.create_index('ix_categorization_rules_enabled', 'categorization_rules', ['user_id', 'enabled'])


def downgrade():
    """Remove categorization_rules table and all indexes."""
    op.drop_index('ix_categorization_rules_enabled', table_name='categorization_rules')
    op.drop_index('ix_categorization_rules_user_merchant', table_name='categorization_rules')
    op.drop_index('ix_categorization_rules_user_id', table_name='categorization_rules')
    op.drop_table('categorization_rules')
