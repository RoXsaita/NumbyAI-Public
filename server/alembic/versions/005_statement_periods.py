"""Move coverage to statement-level table and drop per-summary columns

Revision ID: 005_statement_periods
Revises: 004_add_parsing_and_statement_insights
Create Date: 2025-02-02

"""
from datetime import datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005_statement_periods"
down_revision = "004_add_parsing_and_statement_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Create statement_periods table (one row per user/bank/month coverage window)
    if is_sqlite:
        op.create_table(
            "statement_periods",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("bank_name", sa.String(100), nullable=False),
            sa.Column("month_year", sa.String(7), nullable=False),
            sa.Column("coverage_from", sa.Date(), nullable=False),
            sa.Column("coverage_to", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )
    else:
        op.create_table(
            "statement_periods",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("bank_name", sa.String(100), nullable=False),
            sa.Column("month_year", sa.String(7), nullable=False),
            sa.Column("coverage_from", sa.Date(), nullable=False),
            sa.Column("coverage_to", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )

    op.create_index(
        "idx_stmt_period_user_bank_month",
        "statement_periods",
        ["user_id", "bank_name", "month_year"],
        unique=True,
    )

    # Backfill statement_periods from existing category_summaries coverage
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            SELECT user_id, bank_name, month_year,
                   MIN(coverage_from) AS coverage_from,
                   MAX(coverage_to) AS coverage_to
            FROM category_summaries
            GROUP BY user_id, bank_name, month_year
            """
        )
    )
    rows = result.fetchall()
    now = datetime.utcnow()

    period_table = sa.table(
        "statement_periods",
        sa.column("id", sa.String if is_sqlite else postgresql.UUID(as_uuid=True)),
        sa.column("user_id", sa.String if is_sqlite else postgresql.UUID(as_uuid=True)),
        sa.column("bank_name", sa.String),
        sa.column("month_year", sa.String),
        sa.column("coverage_from", sa.Date),
        sa.column("coverage_to", sa.Date),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    for row in rows:
        conn.execute(
            sa.insert(period_table).values(
                id=str(uuid4()) if is_sqlite else uuid4(),
                user_id=row.user_id,
                bank_name=row.bank_name,
                month_year=row.month_year,
                coverage_from=row.coverage_from,
                coverage_to=row.coverage_to,
                created_at=now,
                updated_at=now,
            )
        )

    # Drop per-summary coverage columns
    if is_sqlite:
        with op.batch_alter_table("category_summaries", schema=None) as batch_op:
            batch_op.drop_column("coverage_from")
            batch_op.drop_column("coverage_to")
    else:
        op.drop_column("category_summaries", "coverage_from")
        op.drop_column("category_summaries", "coverage_to")


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Restore coverage columns on category_summaries
    if is_sqlite:
        with op.batch_alter_table("category_summaries", schema=None) as batch_op:
            batch_op.add_column(sa.Column("coverage_from", sa.Date(), nullable=True))
            batch_op.add_column(sa.Column("coverage_to", sa.Date(), nullable=True))
    else:
        op.add_column("category_summaries", sa.Column("coverage_from", sa.Date(), nullable=True))
        op.add_column("category_summaries", sa.Column("coverage_to", sa.Date(), nullable=True))

    # Backfill coverage values from statement_periods
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT user_id, bank_name, month_year, coverage_from, coverage_to
            FROM statement_periods
            """
        )
    ).fetchall()

    for row in rows:
        conn.execute(
            sa.text(
                """
                UPDATE category_summaries
                SET coverage_from = :coverage_from,
                    coverage_to = :coverage_to
                WHERE user_id = :user_id
                  AND bank_name = :bank_name
                  AND month_year = :month_year
                """
            ),
            {
                "coverage_from": row.coverage_from,
                "coverage_to": row.coverage_to,
                "user_id": row.user_id,
                "bank_name": row.bank_name,
                "month_year": row.month_year,
            },
        )

    # Enforce non-null coverage columns
    if is_sqlite:
        with op.batch_alter_table("category_summaries", schema=None) as batch_op:
            batch_op.alter_column("coverage_from", existing_type=sa.Date(), nullable=False)
            batch_op.alter_column("coverage_to", existing_type=sa.Date(), nullable=False)
    else:
        op.alter_column("category_summaries", "coverage_from", existing_type=sa.Date(), nullable=False)
        op.alter_column("category_summaries", "coverage_to", existing_type=sa.Date(), nullable=False)

    # Drop statement_periods table
    op.drop_index("idx_stmt_period_user_bank_month", table_name="statement_periods")
    op.drop_table("statement_periods")
