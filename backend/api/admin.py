# -*- coding: utf-8 -*-
"""后台管理 API — 仅管理员可访问"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.user import User
from backend.services.auth import get_current_user, hash_password

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "需要管理员权限")
    return user


# ── Schema ────────────────────────────────

class UserRow(BaseModel):
    id: int
    username: str
    phone: str
    is_admin: bool
    is_active: bool
    phone_verified: bool
    created_at: str
    last_login: str | None


class UserListResponse(BaseModel):
    total: int
    users: list[UserRow]


class ToggleActiveRequest(BaseModel):
    user_id: int
    is_active: bool


class ResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str


class SystemStats(BaseModel):
    total_users: int
    active_users: int
    admin_count: int
    verified_count: int


# ── 接口 ──────────────────────────────────

@router.get("/stats", response_model=SystemStats)
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """系统统计概览"""
    total = db.execute(select(func.count()).select_from(User)).scalar()
    active = db.execute(select(func.count()).select_from(User).where(User.is_active == True)).scalar()
    admins = db.execute(select(func.count()).select_from(User).where(User.is_admin == True)).scalar()
    verified = db.execute(select(func.count()).select_from(User).where(User.phone_verified == True)).scalar()
    return SystemStats(
        total_users=total, active_users=active,
        admin_count=admins, verified_count=verified,
    )


@router.get("/users", response_model=UserListResponse)
def admin_list_users(
    search: str = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """用户列表"""
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)

    if search:
        flt = User.username.contains(search) | User.phone.contains(search)
        stmt = stmt.where(flt)
        count_stmt = count_stmt.where(flt)

    total = db.execute(count_stmt).scalar()
    users = db.execute(
        stmt.order_by(User.id.desc()).offset(offset).limit(limit)
    ).scalars().all()

    return UserListResponse(
        total=total,
        users=[
            UserRow(
                id=u.id,
                username=u.username,
                phone=u.phone,
                is_admin=u.is_admin,
                is_active=u.is_active,
                phone_verified=u.phone_verified,
                created_at=u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
                last_login=u.last_login.strftime("%Y-%m-%d %H:%M") if u.last_login else None,
            )
            for u in users
        ],
    )


@router.post("/users/toggle-active")
def admin_toggle_active(
    req: ToggleActiveRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """启用/禁用用户"""
    user = db.get(User, req.user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, "不能禁用自己")
    user.is_active = req.is_active
    db.commit()
    return {"ok": True, "message": f"用户 {user.username} 已{'启用' if req.is_active else '禁用'}"}


@router.post("/users/reset-password")
def admin_reset_password(
    req: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """重置用户密码"""
    if len(req.new_password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    user = db.get(User, req.user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"ok": True, "message": f"用户 {user.username} 密码已重置"}


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除用户"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, "不能删除自己")
    if user.is_admin:
        raise HTTPException(400, "不能删除管理员账号")
    db.delete(user)
    db.commit()
    return {"ok": True, "message": f"用户 {user.username} 已删除"}
