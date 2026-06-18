"""我的股票池 watchlist / watchlist_item

Revision ID: add_watchlist
Revises: add_risk_ai_layer
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_watchlist"
down_revision: Union[str, Sequence[str], None] = "add_risk_ai_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), index=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "watchlist_item",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("watchlist_id", sa.BigInteger, sa.ForeignKey("watchlist.id"), index=True, nullable=False),
        sa.Column("company_id", sa.String(32), sa.ForeignKey("company.company_id"), index=True, nullable=False),
        sa.Column("source_run_id", sa.BigInteger, nullable=True, comment="来源筛选 run"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("added_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_company"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_item")
    op.drop_table("watchlist")
