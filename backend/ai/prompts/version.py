# -*- coding: utf-8 -*-
"""Prompt 版本号。

变更 prompt 模板时必须 bump 此版本。
risk_ai_result.prompt_version 字段记录调用时的版本，
funnel 检测到 prompt_version 不匹配时会重新调 AI。
"""

PROMPT_VERSION = "v2026.06.18.001"  # funnel_v2 双层（稳健 4 类 + 风险 8 类）
