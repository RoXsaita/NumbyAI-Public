"""Add password_hash to users table

Revision ID: 013_add_user_password_hash
Revises: 012_add_categorization_rules
Create Date: 2025-01-XX
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '013_add_user_password_hash'
down_revision = '012_add_categorization_rules'
branch_labels = None
depends_on = None


def upgrade():
    """Add password_hash column to users table."""
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))


def downgrade():
    """Remove password_hash column from users table."""
    op.drop_column('users', 'password_hash')
