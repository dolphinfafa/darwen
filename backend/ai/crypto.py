# -*- coding: utf-8 -*-
"""Fernet 加密 user 表 API key。

密钥来源（按优先级）：
1. 环境变量 DARWEN_FERNET_KEY
2. backend.config.get_settings().darwen_fernet_key（如已注册）

生成新密钥：
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    写入 .env: DARWEN_FERNET_KEY=...
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class FernetKeyMissing(RuntimeError):
    """DARWEN_FERNET_KEY 未配置时抛出。"""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get("DARWEN_FERNET_KEY")
    if not key:
        # 尝试从 settings 读
        try:
            from backend.config import get_settings
            settings = get_settings()
            key = getattr(settings, "darwen_fernet_key", None)
        except Exception:  # noqa: BLE001
            pass
    if not key:
        raise FernetKeyMissing(
            "DARWEN_FERNET_KEY 未配置。运行 "
            "`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` "
            "生成并写入 .env"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_api_key(plaintext: str) -> str:
    """加密 API key → base64 字符串。"""
    if not plaintext:
        raise ValueError("plaintext 为空")
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """解密 → 原 API key。密钥失配抛 cryptography.fernet.InvalidToken。"""
    if not ciphertext:
        raise ValueError("ciphertext 为空")
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask_api_key(plaintext: str, *, prefix: int = 4, suffix: int = 4) -> str:
    """返回掩码 'sk-XXXX...xxxx'，用于前端展示已绑定状态。"""
    if not plaintext or len(plaintext) <= prefix + suffix:
        return "*" * len(plaintext or "")
    return f"{plaintext[:prefix]}...{plaintext[-suffix:]}"


__all__ = [
    "FernetKeyMissing",
    "InvalidToken",
    "encrypt_api_key",
    "decrypt_api_key",
    "mask_api_key",
]
