# -*- coding: utf-8 -*-
"""AI Provider 抽象基类。

每个 provider 需实现：
- name: str   provider 标识（"chatgpt" / "minimax"）
- default_model: str
- call(system_prompt, user_prompt, *, timeout, temperature) -> str

call() 返回 raw 字符串，由 orchestrator 负责 JSON 解析与 schema 校验。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class AIProviderError(RuntimeError):
    """AI 调用基础错误。orchestrator 据此降级。"""


class AITimeoutError(AIProviderError):
    """超时错误（PRD 第 10 节：超时 20s 自动 REVIEW）。"""


class AIAuthError(AIProviderError):
    """key 无效 / 鉴权失败。"""


class AIProvider(ABC):
    """所有 provider 子类必须遵守的接口。"""

    name: str = ""              # "chatgpt" / "minimax"
    default_model: str = ""

    def __init__(self, api_key: str, *, model: Optional[str] = None, **kwargs):
        if not api_key:
            raise AIAuthError(f"{self.name}: api_key 为空")
        self.api_key = api_key
        self.model = model or self.default_model

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float = 20.0,
        temperature: float = 0.1,
    ) -> str:
        """同步阻塞调用 LLM，返回原始响应文本。

        实现要点：
        - 网络/认证错误抛 AIProviderError / AIAuthError
        - 超时抛 AITimeoutError
        - 不做 JSON 解析（由 orchestrator 做）
        """
        raise NotImplementedError


__all__ = ["AIProvider", "AIProviderError", "AITimeoutError", "AIAuthError"]
