"""Add parsing instructions and statement insights

Revision ID: 004_add_parsing_and_statement_insights
Revises: 003_category_summaries
Create Date: 2025-11-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from app.config import settings
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '004_add_parsing_and_statement_insights'
down_revision = '003_category_summaries'
branch_labels = None
depends_on = None

def upgrade():
    # Determine UUID type based on database backend
    if settings.database_url.startswith("sqlite"):
        uuid_type = sa.String(36)
    else:
        uuid_type = UUID(as_uuid=True)

    # Create statement_insights table
    op.create_table(
        'statement_insights',
        sa.Column('id', uuid_type, nullable=False),
        sa.Column('user_id', uuid_type, nullable=False),
        sa.Column('bank_name', sa.String(length=100), nullable=False),
        sa.Column('month_year', sa.String(length=7), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for statement_insights
    op.create_index(op.f('ix_statement_insights_bank_name'), 'statement_insights', ['bank_name'], unique=False)
    op.create_index(op.f('ix_statement_insights_month_year'), 'statement_insights', ['month_year'], unique=False)
    op.create_index('idx_stmt_insight_user_bank_month', 'statement_insights', ['user_id', 'bank_name', 'month_year'], unique=True)

    # Create parsing_instructions table
    op.create_table(
        'parsing_instructions',
        sa.Column('id', uuid_type, nullable=False),
        sa.Column('user_id', uuid_type, nullable=False),
        sa.Column('bank_name', sa.String(length=100), nullable=False),
        sa.Column('file_format', sa.String(length=20), nullable=False),
        sa.Column('instructions', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Indexes for parsing_instructions
    op.create_index(op.f('ix_parsing_instructions_bank_name'), 'parsing_instructions', ['bank_name'], unique=False)
    op.create_index(op.f('ix_parsing_instructions_file_format'), 'parsing_instructions', ['file_format'], unique=False)
    op.create_index('idx_parsing_instr_user_bank_format', 'parsing_instructions', ['user_id', 'bank_name', 'file_format'], unique=True)


def downgrade():
    op.drop_table('parsing_instructions')
    op.drop_table('statement_insights')

