# -*- coding: utf-8 -*-
"""ChatGPT / OpenAI provider（PRD 第 13 节）。

默认模型 gpt-5（PRD 指定）。环境变量覆盖：
- DARWEN_CHATGPT_MODEL  覆盖模型名
- DARWEN_CHATGPT_BASE_URL  覆盖 API base URL（用于 apiyi 等 OpenAI 兼容代理）

OpenAI SDK 1.x 兼容任何符合 OpenAI 协议的代理（如 api.apiyi.com）。
"""
from __future__ import annotations

import os

from backend.ai.provider_base import (
    AIAuthError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
)


def _default_model() -> str:
    """运行时读 settings / env，避免模块加载时定型。"""
    try:
        from backend.config import get_settings
        m = get_settings().darwen_chatgpt_model
        if m:
            return m
    except Exception:
        pass
    return os.environ.get("DARWEN_CHATGPT_MODEL", "gpt-5")


def _default_base_url() -> str | None:
    try:
        from backend.config import get_settings
        b = get_settings().darwen_chatgpt_base_url
        if b:
            return b
    except Exception:
        pass
    return os.environ.get("DARWEN_CHATGPT_BASE_URL") or None


class ChatGPTProvider(AIProvider):
    name = "chatgpt"
    # 这里仅作占位；实例化时从 settings 读真实默认
    default_model = "gpt-5"

    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ):
        # 显式 model 优先，否则用 settings 默认
        effective_model = model or _default_model()
        super().__init__(api_key, model=effective_model, **kwargs)
        # 延迟 import 避免 backend.ai 模块无 openai 也能加载
        from openai import OpenAI
        effective_base = base_url or _default_base_url()
        client_kwargs = {"api_key": api_key}
        if effective_base:
            client_kwargs["base_url"] = effective_base
        self._client = OpenAI(**client_kwargs)

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float = 20.0,
        temperature: float = 0.1,
    ) -> str:
        from openai import (
            APITimeoutError,
            AuthenticationError,
            APIConnectionError,
            APIError,
            BadRequestError,
        )

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=timeout,
            )
        except APITimeoutError as e:
            raise AITimeoutError(f"chatgpt timeout: {e}") from e
        except AuthenticationError as e:
            raise AIAuthError(f"chatgpt auth failed: {e}") from e
        except (APIConnectionError, BadRequestError, APIError) as e:
            raise AIProviderError(f"chatgpt api error: {e}") from e

        if not resp.choices:
            raise AIProviderError("chatgpt: empty choices")
        content = resp.choices[0].message.content
        if not content:
            raise AIProviderError("chatgpt: empty content")
        return content
