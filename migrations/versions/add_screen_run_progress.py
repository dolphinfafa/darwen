"""Add screen_run.progress_count + current_company_name

Revision ID: screen_run_progress
Revises: company_fye_month
Create Date: 2026-05-15

让前端轮询能实时看到"已处理 N/total + 正在评估 X 公司"。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "screen_run_progress"
down_revision: Union[str, Sequence[str], None] = "company_fye_month"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "screen_run",
        sa.Column("progress_count", sa.Integer(), nullable=False, server_default="0",
                  comment="已处理公司数（实时刷新）"),
    )
    op.add_column(
        "screen_run",
        sa.Column("current_company_name", sa.String(200), nullable=True,
                  comment="当前正在评估的公司名（用户可读，每家公司开始时更新）"),
    )


def downgrade() -> None:
    op.drop_column("screen_run", "current_company_name")
    op.drop_column("screen_run", "progress_count")
