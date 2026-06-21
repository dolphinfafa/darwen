"""市场资讯 market_news（Tushare major_news 大盘新闻）

Revision ID: add_market_news
Revises: add_mcp_token
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_market_news"
down_revision: Union[str, Sequence[str], None] = "add_mcp_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_news",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("source", sa.String(60), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("ingested_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_market_news_url", "market_news", ["url"], unique=True)
    op.create_index("ix_market_news_published_at", "market_news", ["published_at"])


def downgrade() -> None:
    op.drop_table("market_news")
