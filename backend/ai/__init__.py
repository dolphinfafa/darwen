# -*- coding: utf-8 -*-
"""Darwen V2 AI 风险层（PRD 第 4.5 节 + 第 13 节）。

双 provider 架构：ChatGPT 5（OpenAI SDK）+ MiniMax 2.7（httpx 直连）。
每用户独立绑定 key，Fernet 加密落 user 表。

模块结构：
- crypto       : Fernet 加密 / 解密 user.{chatgpt|minimax}_api_key_encrypted
- schema       : Pydantic 校验 AI 输出 JSON
- prompts/     : 系统 + 用户 prompt 模板 + 版本号
- provider_base: AIProvider 抽象基类
- chatgpt_provider / minimax_provider : 两个具体 provider
- orchestrator : 编排（取 user key、构 prompt、调用、校验、落库）
"""
