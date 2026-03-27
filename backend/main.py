# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.screener import router as screener_router
from backend.api.company import router as company_router
from backend.api.report import router as report_router
from backend.api.backtest import router as backtest_router
from backend.api.auth import router as auth_router
from backend.api.admin import router as admin_router
from backend.api.backtest_v2 import router as backtest_v2_router

settings = get_settings()

app = FastAPI(
    title="Darwen - AI进化论股票筛选系统",
    description="基于达尔文进化论投资方法论的股票筛选系统，覆盖美股与A股",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(screener_router)
app.include_router(company_router)
app.include_router(report_router)
app.include_router(backtest_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(backtest_v2_router)


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
