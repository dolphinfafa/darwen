# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.auth import router as auth_router
from backend.api.admin import router as admin_router
from backend.api.user_settings import router as user_settings_router
from backend.api.screening import router as screening_router
from backend.api.backtest import router as backtest_router
from backend.api.companies import router as companies_router

settings = get_settings()

app = FastAPI(
    title="Darwen V2 - 三层漏斗股票筛选系统",
    description="基于 Pulak Prasad《What I Learned About Investing from Darwin》方法论的股票筛选系统：ROCE 质量门槛 → 风险过滤 → 价格闸门",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(user_settings_router)
app.include_router(screening_router)
app.include_router(backtest_router)
app.include_router(companies_router)


@app.on_event("startup")
def init_db_and_admin():
    """建表 + 创建 admin 账号"""
    from backend.database import engine, SessionLocal
    from backend.models.user import User
    from backend.services.auth import hash_password
    from sqlalchemy import select

    User.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == "admin")).scalar()
        if not admin:
            db.add(User(
                username="admin",
                phone="13121813950",
                password_hash=hash_password("wangyi4sb"),
                is_admin=True,
                phone_verified=True,
            ))
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
