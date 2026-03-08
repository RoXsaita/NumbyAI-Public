"""Add currency conversion columns to transactions

Revision ID: 017_add_currency_conversion_columns
Revises: 016_add_transaction_category_source
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa


revision = '017_add_currency_conversion_columns'
down_revision = '016_add_transaction_category_source'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transactions', sa.Column('original_amount', sa.Numeric(12, 2), nullable=True))
    op.add_column('transactions', sa.Column('original_currency', sa.String(3), nullable=True))
    op.add_column('transactions', sa.Column('exchange_rate', sa.Numeric(18, 8), nullable=True))


def downgrade():
    op.drop_column('transactions', 'exchange_rate')
    op.drop_column('transactions', 'original_currency')
    op.drop_column('transactions', 'original_amount')
