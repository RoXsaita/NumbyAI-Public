"""Add custom categories table

Revision ID: 018_add_custom_categories
Revises: 017_add_currency_conversion_columns
Create Date: 2026-03-08
"""
from alembic import op
import sqlalchemy as sa


revision = '018_add_custom_categories'
down_revision = '017_add_currency_conversion_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custom_categories',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_custom_categories_user', 'custom_categories', ['user_id'])
    op.create_index(
        'idx_custom_categories_user_name', 'custom_categories',
        ['user_id', 'name'], unique=True,
    )


def downgrade():
    op.drop_index('idx_custom_categories_user_name', table_name='custom_categories')
    op.drop_index('idx_custom_categories_user', table_name='custom_categories')
    op.drop_table('custom_categories')
