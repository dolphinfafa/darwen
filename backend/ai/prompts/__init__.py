# -*- coding: utf-8 -*-
"""AI 风险层 prompt 模板。

prompt 变更必须 bump PROMPT_VERSION，旧 prompt_version 的 risk_ai_result
自动作废（funnel 重跑时重新调用 AI）。
"""
from backend.ai.prompts.risk_filter import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from backend.ai.prompts.version import PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "SYSTEM_PROMPT", "build_user_prompt"]
