"""Add category source to transactions

Revision ID: 016_add_transaction_category_source
Revises: 015_add_rule_analysis_tables
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa


revision = '016_add_transaction_category_source'
down_revision = '015_add_rule_analysis_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('category_source', sa.String(20), nullable=True))
    op.create_index('idx_transactions_user_category_source', 'transactions', ['user_id', 'category_source'])


def downgrade():
    op.drop_index('idx_transactions_user_category_source', table_name='transactions')
    op.drop_column('transactions', 'category_source')
