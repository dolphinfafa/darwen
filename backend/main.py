# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.screener import router as screener_router
from backend.api.company import router as company_router
from backend.api.report import router as report_router
from backend.api.backtest import router as backtest_router

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
