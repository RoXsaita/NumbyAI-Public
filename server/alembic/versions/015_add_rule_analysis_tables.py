"""Add rule analysis run/finding tables

Revision ID: 015_add_rule_analysis_tables
Revises: 014_add_review_columns
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


revision = "015_add_rule_analysis_tables"
down_revision = "014_add_review_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rule_analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scope_since", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rule_analysis_runs_user_created",
        "rule_analysis_runs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_rule_analysis_runs_user_status_created",
        "rule_analysis_runs",
        ["user_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "rule_analysis_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("finding_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("bank_name", sa.String(length=100), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["rule_analysis_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rule_analysis_findings_run_status",
        "rule_analysis_findings",
        ["run_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_rule_analysis_findings_user_status_created",
        "rule_analysis_findings",
        ["user_id", "status", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "idx_rule_analysis_findings_user_status_created",
        table_name="rule_analysis_findings",
    )
    op.drop_index("idx_rule_analysis_findings_run_status", table_name="rule_analysis_findings")
    op.drop_table("rule_analysis_findings")

    op.drop_index("idx_rule_analysis_runs_user_status_created", table_name="rule_analysis_runs")
    op.drop_index("idx_rule_analysis_runs_user_created", table_name="rule_analysis_runs")
    op.drop_table("rule_analysis_runs")
