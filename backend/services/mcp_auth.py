# -*- coding: utf-8 -*-
"""MCP 访问令牌：为用户生成长期 token（供外部 agent 凭此读股票池行情）。

token 明文仅在生成时返回一次，库内只存 sha256；重新生成即失效旧 token。
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.user import User


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_mcp_token(db: Session, user: User) -> str:
    """生成并存储新 token（覆盖旧的），返回明文（仅此一次可见）。"""
    token = secrets.token_urlsafe(32)
    user.mcp_token_hash = _hash(token)
    db.add(user)
    db.commit()
    return token


def resolve_user_by_token(db: Session, token: str) -> Optional[User]:
    """按 token 明文反查用户（sha256 比对）；无效返回 None。"""
    if not token:
        return None
    return db.execute(
        select(User).where(User.mcp_token_hash == _hash(token)).limit(1)
    ).scalar()


def has_mcp_token(user: User) -> bool:
    return bool(user.mcp_token_hash)
