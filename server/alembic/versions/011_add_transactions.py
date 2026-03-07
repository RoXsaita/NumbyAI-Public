"""Add transactions table for full transaction storage

Revision ID: 011_add_transactions
Revises: 010_add_profile
Create Date: 2025-01-XX

This migration adds a 'transactions' table to store individual transaction
records instead of aggregated category summaries. This enables transaction-level
editing, recategorization, and better data granularity.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = '011_add_transactions'
down_revision = '010_add_profile'
branch_labels = None
depends_on = None


def upgrade():
    """Create transactions table with all required fields and indexes."""
    # Detect database type
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    
    if is_sqlite:
        # SQLite version
        op.create_table(
            'transactions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.Column('description', sa.String(500), nullable=False),
            sa.Column('merchant', sa.String(200), nullable=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('bank_name', sa.String(100), nullable=False),
            sa.Column('statement_period_id', sa.String(36), nullable=True),
            sa.Column('profile', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['statement_period_id'], ['statement_periods.id']),
        )
    else:
        # PostgreSQL version
        op.create_table(
            'transactions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('date', sa.Date(), nullable=False),
            sa.Column('description', sa.String(500), nullable=False),
            sa.Column('merchant', sa.String(200), nullable=True),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('bank_name', sa.String(100), nullable=False),
            sa.Column('statement_period_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('profile', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['statement_period_id'], ['statement_periods.id']),
        )
    
    # Create indexes for common query patterns
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])
    op.create_index('ix_transactions_user_date', 'transactions', ['user_id', 'date'])
    op.create_index('ix_transactions_user_category', 'transactions', ['user_id', 'category'])
    op.create_index('ix_transactions_user_merchant', 'transactions', ['user_id', 'merchant'])
    op.create_index('ix_transactions_user_bank_date', 'transactions', ['user_id', 'bank_name', 'date'])
    op.create_index('ix_transactions_date', 'transactions', ['date'])
    op.create_index('ix_transactions_category', 'transactions', ['category'])
    op.create_index('ix_transactions_bank_name', 'transactions', ['bank_name'])


def downgrade():
    """Remove transactions table and all indexes."""
    op.drop_index('ix_transactions_bank_name', table_name='transactions')
    op.drop_index('ix_transactions_category', table_name='transactions')
    op.drop_index('ix_transactions_date', table_name='transactions')
    op.drop_index('ix_transactions_user_bank_date', table_name='transactions')
    op.drop_index('ix_transactions_user_merchant', table_name='transactions')
    op.drop_index('ix_transactions_user_category', table_name='transactions')
    op.drop_index('ix_transactions_user_date', table_name='transactions')
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_table('transactions')
