# -*- coding: utf-8 -*-
"""MiniMax provider（httpx 直连）。

默认模型 abab-2.7-chat-completion-v2（PRD 第 13 节）。
MiniMax 需要 group_id（明文）+ api_key（加密存储）。

API: https://api.minimax.chat/v1/text/chatcompletion_pro
"""
from __future__ import annotations

import json
import os

import httpx

from backend.ai.provider_base import (
    AIAuthError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
)


_MINIMAX_ENDPOINT = "https://api.minimax.chat/v1/text/chatcompletion_v2"


class MiniMaxProvider(AIProvider):
    name = "minimax"
    default_model = os.environ.get("DARWEN_MINIMAX_MODEL", "abab-2.7-chat-completion-v2")

    def __init__(
        self,
        api_key: str,
        *,
        group_id: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(api_key, model=model, **kwargs)
        if not group_id:
            raise AIAuthError("minimax: group_id required")
        self.group_id = group_id

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout: float = 20.0,
        temperature: float = 0.1,
    ) -> str:
        url = f"{_MINIMAX_ENDPOINT}?GroupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise AITimeoutError(f"minimax timeout: {e}") from e
        except httpx.HTTPError as e:
            raise AIProviderError(f"minimax http error: {e}") from e

        if resp.status_code == 401:
            raise AIAuthError(f"minimax auth failed: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise AIProviderError(f"minimax http {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise AIProviderError(f"minimax non-json: {resp.text[:200]}") from e

        # 兼容 OpenAI 风格响应
        choices = data.get("choices") or []
        if not choices:
            raise AIProviderError(f"minimax: empty choices, raw={data}")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if not content:
            raise AIProviderError(f"minimax: empty content, raw={data}")
        return content
