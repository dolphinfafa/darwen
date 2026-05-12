# -*- coding: utf-8 -*-
"""ChatGPT / OpenAI provider（PRD 第 13 节）。

默认模型 gpt-5（PRD 指定）。若 OpenAI 后续重命名，可在 ScreenConfig 或环境变量
DARWEN_CHATGPT_MODEL 中覆盖。
"""
from __future__ import annotations

import os

from backend.ai.provider_base import (
    AIAuthError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
)


class ChatGPTProvider(AIProvider):
    name = "chatgpt"
    default_model = os.environ.get("DARWEN_CHATGPT_MODEL", "gpt-5")

    def __init__(self, api_key: str, *, model: str | None = None, **kwargs):
        super().__init__(api_key, model=model, **kwargs)
        # 延迟 import 避免 backend.ai 模块无 openai 也能加载
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)

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
