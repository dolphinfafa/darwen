"""risk_ai_result +layer（区分稳健层/风险层 AI 判定）

Revision ID: add_risk_ai_layer
Revises: funnel_v2_layers
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_risk_ai_layer"
down_revision: Union[str, Sequence[str], None] = "funnel_v2_layers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("risk_ai_result", sa.Column(
        "layer", sa.String(20), nullable=True,
        comment="sturdiness|risk；NULL=旧 R 层",
    ))
    op.create_index("ix_risk_ai_layer", "risk_ai_result", ["layer"])


def downgrade() -> None:
    op.drop_index("ix_risk_ai_layer", table_name="risk_ai_result")
    op.drop_column("risk_ai_result", "layer")
