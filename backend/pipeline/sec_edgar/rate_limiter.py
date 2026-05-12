# -*- coding: utf-8 -*-
"""SEC EDGAR 限速器：强制 ≤10 req/s + User-Agent 声明（同步版）"""
import time
import threading

import httpx

from backend.config import get_settings

settings = get_settings()

SEC_BASE_URL = "https://data.sec.gov"
SEC_EFTS_URL = "https://efts.sec.gov"

# SEC 要求声明 User-Agent，限速 10 req/s
_MIN_INTERVAL = 0.12
_last_request_time = 0.0
_lock = threading.Lock()

# 复用同步 client
_client = httpx.Client(
    timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
    proxy=None,
)


def _build_headers() -> dict:
    return {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _throttle():
    global _last_request_time
    with _lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_time = time.monotonic()


def sec_get(path: str, base_url: str = SEC_BASE_URL, **kwargs) -> dict | list | None:
    """带限速的 SEC API GET 请求，自动重试"""
    url = f"{base_url}{path}"
    headers = _build_headers()
    max_retries = 3

    for attempt in range(max_retries):
        _throttle()
        try:
            resp = _client.get(url, headers=headers, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            else:
                resp.raise_for_status()
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    return None


def sec_get_raw(url: str, **kwargs) -> str | None:
    """带限速直接拉绝对 URL 的原文（HTML / 文本），返回字符串。

    用于 www.sec.gov/Archives/... 等非 JSON 资源。
    """
    headers = {
        "User-Agent": settings.sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html, text/plain, */*",
    }
    max_retries = 3
    for attempt in range(max_retries):
        _throttle()
        try:
            resp = _client.get(url, headers=headers, **kwargs)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    return None
