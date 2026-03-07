"""Add category summaries model - replace transaction-based with summary-based storage

Revision ID: 003_category_summaries
Revises: 002_add_insights
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_category_summaries'
down_revision = '002_add_insights'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # Drop old tables (transactions first due to foreign keys)
    op.drop_index('idx_transactions_date', table_name='transactions')
    op.drop_index('idx_transactions_user_category', table_name='transactions')
    op.drop_index('idx_transactions_statement', table_name='transactions')
    op.drop_index('ix_transactions_source_hash', table_name='transactions')
    op.drop_index('ix_transactions_transaction_date', table_name='transactions')
    op.drop_index('ix_transactions_category', table_name='transactions')
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_index('ix_transactions_statement_id', table_name='transactions')
    op.drop_table('transactions')

    # Drop statements table
    if is_sqlite:
        with op.batch_alter_table('statements', schema=None) as batch_op:
            batch_op.drop_constraint('uq_statements_user_account_period', type_='unique')
    else:
        op.drop_constraint('uq_statements_user_account_period', 'statements', type_='unique')

    op.drop_index('idx_statements_user_month', table_name='statements')
    op.drop_index('ix_statements_account_key', table_name='statements')
    op.drop_index('ix_statements_statement_month', table_name='statements')
    op.drop_index('ix_statements_user_id', table_name='statements')
    op.drop_table('statements')

    # Create category_summaries table
    if is_sqlite:
        op.create_table(
            'category_summaries',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('bank_name', sa.String(100), nullable=False),
            sa.Column('month_year', sa.String(7), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('transaction_count', sa.Numeric(), nullable=False),
            sa.Column('coverage_from', sa.Date(), nullable=False),
            sa.Column('coverage_to', sa.Date(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    else:
        op.create_table(
            'category_summaries',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('bank_name', sa.String(100), nullable=False),
            sa.Column('month_year', sa.String(7), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('transaction_count', sa.Numeric(), nullable=False),
            sa.Column('coverage_from', sa.Date(), nullable=False),
            sa.Column('coverage_to', sa.Date(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )

    # Create indexes
    op.create_index('ix_category_summaries_user_id', 'category_summaries', ['user_id'])
    op.create_index('ix_category_summaries_bank_name', 'category_summaries', ['bank_name'])
    op.create_index('ix_category_summaries_month_year', 'category_summaries', ['month_year'])
    op.create_index('ix_category_summaries_category', 'category_summaries', ['category'])
    op.create_index('idx_summaries_user_month', 'category_summaries', ['user_id', 'month_year'])
    op.create_index('idx_summaries_user_bank_month', 'category_summaries', ['user_id', 'bank_name', 'month_year'])
    op.create_index('idx_summaries_user_category', 'category_summaries', ['user_id', 'category'])


def downgrade() -> None:
    # Drop category_summaries table
    op.drop_index('idx_summaries_user_category', table_name='category_summaries')
    op.drop_index('idx_summaries_user_bank_month', table_name='category_summaries')
    op.drop_index('idx_summaries_user_month', table_name='category_summaries')
    op.drop_index('ix_category_summaries_category', table_name='category_summaries')
    op.drop_index('ix_category_summaries_month_year', table_name='category_summaries')
    op.drop_index('ix_category_summaries_bank_name', table_name='category_summaries')
    op.drop_index('ix_category_summaries_user_id', table_name='category_summaries')
    op.drop_table('category_summaries')

    # Recreate old tables (statements first, then transactions)
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        op.create_table(
            'statements',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('upload_date', sa.DateTime(), nullable=False),
            sa.Column('statement_month', sa.String(7), nullable=False),
            sa.Column('account_key', sa.String(255), nullable=True),
            sa.Column('file_name', sa.String(255), nullable=False),
            sa.Column('bank_name', sa.String(100)),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('starting_balance', sa.Numeric(12, 2), nullable=False),
            sa.Column('ending_balance', sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    else:
        op.create_table(
            'statements',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('upload_date', sa.DateTime(), nullable=False),
            sa.Column('statement_month', sa.String(7), nullable=False),
            sa.Column('account_key', sa.String(255), nullable=True),
            sa.Column('file_name', sa.String(255), nullable=False),
            sa.Column('bank_name', sa.String(100)),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('starting_balance', sa.Numeric(12, 2), nullable=False),
            sa.Column('ending_balance', sa.Numeric(12, 2), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    op.create_index('ix_statements_user_id', 'statements', ['user_id'])
    op.create_index('ix_statements_statement_month', 'statements', ['statement_month'])
    op.create_index('ix_statements_account_key', 'statements', ['account_key'])
    op.create_index('idx_statements_user_month', 'statements', ['user_id', 'statement_month'])

    if is_sqlite:
        with op.batch_alter_table('statements', schema=None) as batch_op:
            batch_op.create_unique_constraint('uq_statements_user_account_period', ['user_id', 'account_key', 'statement_month'])
    else:
        op.create_unique_constraint('uq_statements_user_account_period', 'statements', ['user_id', 'account_key', 'statement_month'])

    if is_sqlite:
        op.create_table(
            'transactions',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('statement_id', sa.String(36), nullable=False),
            sa.Column('user_id', sa.String(36), nullable=False),
            sa.Column('transaction_date', sa.Date(), nullable=False),
            sa.Column('description', sa.String(), nullable=False),
            sa.Column('merchant', sa.String(255)),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('source_hash', sa.String(64), nullable=True, unique=True),
            sa.ForeignKeyConstraint(['statement_id'], ['statements.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    else:
        op.create_table(
            'transactions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('statement_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('transaction_date', sa.Date(), nullable=False),
            sa.Column('description', sa.String(), nullable=False),
            sa.Column('merchant', sa.String(255)),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False),
            sa.Column('currency', sa.String(3), nullable=False),
            sa.Column('category', sa.String(100), nullable=False),
            sa.Column('source_hash', sa.String(64), nullable=True, unique=True),
            sa.ForeignKeyConstraint(['statement_id'], ['statements.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        )
    op.create_index('ix_transactions_statement_id', 'transactions', ['statement_id'])
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'])
    op.create_index('ix_transactions_category', 'transactions', ['category'])
    op.create_index('ix_transactions_transaction_date', 'transactions', ['transaction_date'])
    op.create_index('ix_transactions_source_hash', 'transactions', ['source_hash'], unique=True)
    op.create_index('idx_transactions_statement', 'transactions', ['statement_id'])
    op.create_index('idx_transactions_user_category', 'transactions', ['user_id', 'category'])
    op.create_index('idx_transactions_date', 'transactions', ['transaction_date'])
