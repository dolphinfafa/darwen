# -*- coding: utf-8 -*-
"""用户 AI API Key 绑定 + 默认 provider 切换。

PRD 第 13 节：每用户独立绑定 ChatGPT / MiniMax key，Fernet 加密存于 user 表。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.ai.crypto import (
    FernetKeyMissing,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)
from backend.database import get_db
from backend.models.user import User
from backend.schemas.v2 import (
    APIKeyBindRequest,
    APIKeyDeleteRequest,
    APIKeyStatusResponse,
    DefaultProviderUpdateRequest,
)
from backend.services.auth import get_current_user
from backend.services.mcp_auth import generate_mcp_token, has_mcp_token


router = APIRouter(prefix="/v1/user", tags=["user-settings"])

# MCP 端点对外路径（经 nginx /darwen/v2/ → 后端；前端用 origin 拼完整 URL）
MCP_PATH = "/darwen/v2/mcp"


def _masked_key(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        plain = decrypt_api_key(encrypted)
    except Exception:  # noqa: BLE001
        return "(invalid)"
    return mask_api_key(plain)


@router.post("/api-key", response_model=APIKeyStatusResponse)
def bind_api_key(
    body: APIKeyBindRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """绑定 ChatGPT 或 MiniMax API key。覆盖式更新。"""
    try:
        enc = encrypt_api_key(body.api_key.strip())
    except FernetKeyMissing as e:
        raise HTTPException(500, str(e)) from e

    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")

    if body.provider == "chatgpt":
        db_user.chatgpt_api_key_encrypted = enc
    else:  # minimax
        if not body.group_id:
            raise HTTPException(400, "minimax 必须提供 group_id")
        db_user.minimax_api_key_encrypted = enc
        db_user.minimax_group_id = body.group_id.strip()

    db.commit()
    db.refresh(db_user)
    return _status_response(db_user)


@router.get("/api-key/status", response_model=APIKeyStatusResponse)
def get_api_key_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前绑定状态（key 用掩码返回，不暴露明文）。"""
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")
    return _status_response(db_user)


@router.delete("/api-key", response_model=APIKeyStatusResponse)
def unbind_api_key(
    body: APIKeyDeleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解绑指定 provider 的 key。"""
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")
    if body.provider == "chatgpt":
        db_user.chatgpt_api_key_encrypted = None
    else:
        db_user.minimax_api_key_encrypted = None
        db_user.minimax_group_id = None
    db.commit()
    db.refresh(db_user)
    return _status_response(db_user)


@router.patch("/ai-provider-default", response_model=APIKeyStatusResponse)
def set_default_provider(
    body: DefaultProviderUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """切换默认 provider（chatgpt / minimax）。"""
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")
    db_user.ai_provider_default = body.provider
    db.commit()
    db.refresh(db_user)
    return _status_response(db_user)


@router.post("/mcp-token")
def create_mcp_token(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成 MCP 访问令牌（明文仅此一次返回，覆盖旧令牌）。外部 agent 凭此读股票池行情。"""
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")
    token = generate_mcp_token(db, db_user)
    return {"token": token, "mcp_path": MCP_PATH}


@router.get("/mcp-token")
def get_mcp_token_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """是否已生成 MCP 令牌（不返回明文）。"""
    db_user = db.get(User, user.id)
    if db_user is None:
        raise HTTPException(404, "user not found")
    return {"has_token": has_mcp_token(db_user), "mcp_path": MCP_PATH}


def _status_response(user: User) -> APIKeyStatusResponse:
    return APIKeyStatusResponse(
        chatgpt_bound=bool(user.chatgpt_api_key_encrypted),
        chatgpt_masked=_masked_key(user.chatgpt_api_key_encrypted),
        minimax_bound=bool(user.minimax_api_key_encrypted),
        minimax_masked=_masked_key(user.minimax_api_key_encrypted),
        minimax_group_id=user.minimax_group_id,
        default_provider=user.ai_provider_default or "chatgpt",
    )
