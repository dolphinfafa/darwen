# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime)

    chatgpt_api_key_encrypted: Mapped[str | None] = mapped_column(
        Text, comment="Fernet 加密后的 ChatGPT/OpenAI API Key"
    )
    minimax_api_key_encrypted: Mapped[str | None] = mapped_column(
        Text, comment="Fernet 加密后的 MiniMax API Key"
    )
    minimax_group_id: Mapped[str | None] = mapped_column(
        String(128), comment="MiniMax 必需的 Group ID（不敏感，明文）"
    )
    ai_provider_default: Mapped[str] = mapped_column(
        Enum("chatgpt", "minimax", name="ai_provider_enum"),
        default="chatgpt",
        comment="默认 AI 提供商",
    )
    mcp_token_hash: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="MCP 访问令牌的 sha256（外部 agent 凭此读股票池行情）"
    )
