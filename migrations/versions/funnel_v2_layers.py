"""Funnel v2: 三层漏斗分层执行 + 人工 gate 字段

screen_run  +current_layer / layer_status / auto_advance
screen_result +rejected_at_layer / layer_results / manual_action (+索引)

全部为加列，不改既有列、不动 enum；可安全回滚。

Revision ID: funnel_v2_layers
Revises: add_ingest_task
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import JSON


revision: str = "funnel_v2_layers"
down_revision: Union[str, Sequence[str], None] = "add_ingest_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # screen_run：分层执行状态
    op.add_column("screen_run", sa.Column(
        "current_layer", sa.String(20), nullable=True, server_default="roce",
        comment="roce|sturdiness|risk|done",
    ))
    op.add_column("screen_run", sa.Column(
        "layer_status", sa.String(20), nullable=True, server_default="running",
        comment="running|awaiting_review|completed|failed",
    ))
    op.add_column("screen_run", sa.Column(
        "auto_advance", sa.Boolean, nullable=False, server_default=sa.text("0"),
        comment="True=三层连跑；False=每层暂停等人工 gate",
    ))

    # screen_result：逐层结果 + 人工干预
    op.add_column("screen_result", sa.Column(
        "rejected_at_layer", sa.String(20), nullable=True,
        comment="roce|sturdiness|risk；NULL=存活/最终入选",
    ))
    op.add_column("screen_result", sa.Column("layer_results", JSON, nullable=True))
    op.add_column("screen_result", sa.Column("manual_action", JSON, nullable=True))
    op.create_index(
        "ix_screen_result_run_layer", "screen_result", ["run_id", "rejected_at_layer"]
    )


def downgrade() -> None:
    op.drop_index("ix_screen_result_run_layer", table_name="screen_result")
    op.drop_column("screen_result", "manual_action")
    op.drop_column("screen_result", "layer_results")
    op.drop_column("screen_result", "rejected_at_layer")
    op.drop_column("screen_run", "auto_advance")
    op.drop_column("screen_run", "layer_status")
    op.drop_column("screen_run", "current_layer")
