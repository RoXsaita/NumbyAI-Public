"""Add review columns to transactions table

Revision ID: 014_add_review_columns
Revises: 013_add_user_password_hash
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa


revision = '014_add_review_columns'
down_revision = '013_add_user_password_hash'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('review_status', sa.String(20), nullable=True))
    op.add_column('transactions', sa.Column('review_category', sa.String(100), nullable=True))
    op.add_column('transactions', sa.Column('review_reason', sa.Text(), nullable=True))
    op.create_index('idx_transactions_review_status', 'transactions', ['user_id', 'review_status'])


def downgrade():
    op.drop_index('idx_transactions_review_status', table_name='transactions')
    op.drop_column('transactions', 'review_reason')
    op.drop_column('transactions', 'review_category')
    op.drop_column('transactions', 'review_status')
