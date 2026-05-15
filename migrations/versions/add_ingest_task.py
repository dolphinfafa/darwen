"""Add ingest_task for manual company ingestion

Revision ID: add_ingest_task
Revises: screen_run_progress
Create Date: 2026-05-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_ingest_task"
down_revision: Union[str, Sequence[str], None] = "screen_run_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_task",
        sa.Column("task_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), index=True),
        sa.Column("market", sa.Enum("US", "CN_A", name="ingest_market_enum"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False, comment="CIK (美股) 或 6 位 stock_code (A股)"),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="ingest_task_status_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("current_stage", sa.String(100), nullable=True,
                  comment="当前阶段：fetching_company / ingest_income / compute_metrics / ..."),
        sa.Column("company_id", sa.String(32), nullable=True, comment="完成后填入"),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingest_task")
