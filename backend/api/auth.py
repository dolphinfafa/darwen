# -*- coding: utf-8 -*-
"""用户注册 / 登录 / 短信验证 API"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.services.auth import (
    hash_password, verify_password, create_token, get_current_user,
)
from backend.services.sms import send_verification_code, verify_code

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def mask_phone(phone: str) -> str:
    """手机号脱敏：131****3950"""
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return "****"


# ── Schema ────────────────────────────────

class SendCodeRequest(BaseModel):
    phone: str


class SendCodeByUsernameRequest(BaseModel):
    username: str


class RegisterRequest(BaseModel):
    username: str
    phone: str
    password: str
    code: str


class LoginStep1Request(BaseModel):
    """第一步：用户名 + 密码"""
    username: str
    password: str


class LoginStep1Response(BaseModel):
    """第一步返回：是否需要验证码 + 脱敏手机号"""
    need_verify: bool
    masked_phone: str
    token: str | None = None
    username: str
    is_admin: bool


class LoginStep2Request(BaseModel):
    """第二步：用户名 + 密码 + 验证码 + 设备ID"""
    username: str
    password: str
    code: str
    device_id: str


class TokenResponse(BaseModel):
    token: str
    username: str
    is_admin: bool


class UserInfo(BaseModel):
    id: int
    username: str
    phone: str
    is_admin: bool
    phone_verified: bool


# ── 接口 ──────────────────────────────────

@router.post("/send-code")
def api_send_code(req: SendCodeRequest):
    """通过手机号发送验证码（注册用）"""
    if not req.phone or len(req.phone) != 11:
        raise HTTPException(400, "请输入正确的 11 位手机号")
    ok, msg = send_verification_code(req.phone)
    if not ok:
        raise HTTPException(429, msg)
    return {"ok": True, "message": msg}


@router.post("/send-code-by-username")
def api_send_code_by_username(req: SendCodeByUsernameRequest, db: Session = Depends(get_db)):
    """通过用户名发送验证码（登录设备验证用），返回脱敏手机号"""
    user = db.execute(select(User).where(User.username == req.username)).scalar()
    if not user:
        raise HTTPException(404, "用户不存在")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")

    ok, msg = send_verification_code(user.phone)
    if not ok:
        raise HTTPException(429, msg)
    return {"ok": True, "message": msg, "masked_phone": mask_phone(user.phone)}


@router.post("/register", response_model=TokenResponse)
def api_register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户"""
    if not req.username or len(req.username) < 2:
        raise HTTPException(400, "用户名至少 2 个字符")
    if not req.phone or len(req.phone) != 11:
        raise HTTPException(400, "请输入正确的 11 位手机号")
    if not req.password or len(req.password) < 6:
        raise HTTPException(400, "密码至少 6 位")

    if not verify_code(req.phone, req.code):
        raise HTTPException(400, "验证码错误或已过期")

    if db.execute(select(User).where(User.username == req.username)).scalar():
        raise HTTPException(409, "用户名已被注册")
    if db.execute(select(User).where(User.phone == req.phone)).scalar():
        raise HTTPException(409, "该手机号已被注册")

    user = User(
        username=req.username,
        phone=req.phone,
        password_hash=hash_password(req.password),
        phone_verified=True,
        last_login=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.username, user.is_admin)
    return TokenResponse(token=token, username=user.username, is_admin=user.is_admin)


@router.post("/login", response_model=LoginStep1Response)
def api_login(req: LoginStep1Request, db: Session = Depends(get_db)):
    """登录第一步：验证用户名+密码，告知是否需要设备验证"""
    user = db.execute(select(User).where(User.username == req.username)).scalar()
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")

    # 密码正确，返回脱敏手机号，由前端决定是否需要设备验证
    return LoginStep1Response(
        need_verify=True,
        masked_phone=mask_phone(user.phone),
        token=None,
        username=user.username,
        is_admin=user.is_admin,
    )


@router.post("/login-verify", response_model=TokenResponse)
def api_login_verify(req: LoginStep2Request, db: Session = Depends(get_db)):
    """登录第二步：密码+验证码 → 签发 token"""
    user = db.execute(select(User).where(User.username == req.username)).scalar()
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not verify_code(user.phone, req.code):
        raise HTTPException(400, "验证码错误或已过期")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_token(user.id, user.username, user.is_admin)
    return TokenResponse(token=token, username=user.username, is_admin=user.is_admin)


@router.post("/login-trusted", response_model=TokenResponse)
def api_login_trusted(req: LoginStep1Request, db: Session = Depends(get_db)):
    """已信任设备直接登录（仅用户名+密码）"""
    user = db.execute(select(User).where(User.username == req.username)).scalar()
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已被禁用")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_token(user.id, user.username, user.is_admin)
    return TokenResponse(token=token, username=user.username, is_admin=user.is_admin)


@router.get("/me", response_model=UserInfo)
def api_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfo(
        id=user.id,
        username=user.username,
        phone=mask_phone(user.phone),
        is_admin=user.is_admin,
        phone_verified=user.phone_verified,
    )
