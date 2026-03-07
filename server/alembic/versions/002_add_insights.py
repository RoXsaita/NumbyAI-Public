"""Add insights table

Revision ID: 002_add_insights
Revises: 001_initial
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_insights'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # Create insights table
    if is_sqlite:
        op.create_table(
            'insights',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('period', sa.String(7), nullable=True),
            sa.Column('insight_type', sa.String(50), nullable=False),
            sa.Column('content', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    else:
        op.create_table(
            'insights',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('period', sa.String(7), nullable=True),
            sa.Column('insight_type', sa.String(50), nullable=False),
            sa.Column('content', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )

    # Create indexes
    op.create_index('ix_insights_user_id', 'insights', ['user_id'])
    op.create_index('ix_insights_title', 'insights', ['title'])
    op.create_index('ix_insights_period', 'insights', ['period'])
    op.create_index('ix_insights_insight_type', 'insights', ['insight_type'])
    op.create_index('idx_insights_user_type', 'insights', ['user_id', 'insight_type'])
    op.create_index('idx_insights_user_period', 'insights', ['user_id', 'period'])


def downgrade() -> None:
    op.drop_index('idx_insights_user_period', table_name='insights')
    op.drop_index('idx_insights_user_type', table_name='insights')
    op.drop_index('ix_insights_insight_type', table_name='insights')
    op.drop_index('ix_insights_period', table_name='insights')
    op.drop_index('ix_insights_title', table_name='insights')
    op.drop_index('ix_insights_user_id', table_name='insights')
    op.drop_table('insights')
