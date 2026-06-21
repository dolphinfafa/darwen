"""user 加 mcp_token_hash（MCP 访问令牌）

Revision ID: add_mcp_token
Revises: add_watchlist
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_mcp_token"
down_revision: Union[str, Sequence[str], None] = "add_watchlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("mcp_token_hash", sa.String(64), nullable=True))
    op.create_index("ix_user_mcp_token_hash", "user", ["mcp_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_user_mcp_token_hash", table_name="user")
    op.drop_column("user", "mcp_token_hash")
