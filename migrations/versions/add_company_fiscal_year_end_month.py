"""Add company.fiscal_year_end_month for authoritative fiscal year end

Revision ID: company_fye_month
Revises: v2_three_funnel
Create Date: 2026-05-13

由 SEC submissions.fiscalYearEnd 填充权威值（如 TSLA=12, NVDA=1, AAPL=9, MSFT=6），
取代基于 NetIncomeLoss 月份众数的启发式（TSLA/NVDA 推断失败）。A 股一律 12。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "company_fye_month"
down_revision: Union[str, Sequence[str], None] = "v2_three_funnel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company",
        sa.Column("fiscal_year_end_month", sa.Integer(), nullable=True,
                  comment="财年末月份 1-12（SEC submissions.fiscalYearEnd 权威；A 股 12）"),
    )


def downgrade() -> None:
    op.drop_column("company", "fiscal_year_end_month")
