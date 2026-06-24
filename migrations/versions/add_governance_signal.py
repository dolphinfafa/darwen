"""治理硬事实信号 governance_signal（阶段2：SEC 8-K Item / A股 Tushare / Form4）

Revision ID: add_governance_signal
Revises: add_market_news
Create Date: 2026-06-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_governance_signal"
down_revision: Union[str, Sequence[str], None] = "add_market_news"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governance_signal",
        sa.Column("signal_id", sa.String(64), primary_key=True),
        sa.Column("company_id", sa.String(32), sa.ForeignKey("company.company_id"), nullable=False),
        sa.Column("signal_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_doc_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_governance_signal_company_id", "governance_signal", ["company_id"])
    op.create_index("ix_governance_signal_signal_type", "governance_signal", ["signal_type"])
    op.create_index("ix_governance_signal_event_date", "governance_signal", ["event_date"])
    op.create_index("ix_govsig_company_type", "governance_signal", ["company_id", "signal_type"])
    op.create_index("ix_govsig_company_event", "governance_signal", ["company_id", "event_date"])


def downgrade() -> None:
    op.drop_table("governance_signal")
