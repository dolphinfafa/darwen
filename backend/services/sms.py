# -*- coding: utf-8 -*-
"""阿里云短信验证码服务"""
import json
import random
import time

from loguru import logger
from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_models
from alibabacloud_tea_util import models as util_models

# 阿里云 SMS 配置：运行时从 settings 读取，避免模块加载时 os.getenv 求值
# （pydantic-settings 从 .env 加载到 Settings 实例，不会同时写入 os.environ）
import os
ENDPOINT = "dysmsapi.aliyuncs.com"


def _get_sms_config() -> tuple[str, str, str, str]:
    """运行时返回 (access_key_id, access_key_secret, sign_name, template_code)。

    优先 backend.config.Settings（从 .env 加载），回退到 os.environ。
    """
    try:
        from backend.config import get_settings
        s = get_settings()
        return (
            s.aliyun_sms_key_id or os.getenv("ALIYUN_SMS_KEY_ID", ""),
            s.aliyun_sms_key_secret or os.getenv("ALIYUN_SMS_KEY_SECRET", ""),
            s.aliyun_sms_sign or os.getenv("ALIYUN_SMS_SIGN", "武汉有易思网络科技"),
            s.aliyun_sms_template or os.getenv("ALIYUN_SMS_TEMPLATE", "SMS_205245667"),
        )
    except Exception:
        return (
            os.getenv("ALIYUN_SMS_KEY_ID", ""),
            os.getenv("ALIYUN_SMS_KEY_SECRET", ""),
            os.getenv("ALIYUN_SMS_SIGN", "武汉有易思网络科技"),
            os.getenv("ALIYUN_SMS_TEMPLATE", "SMS_205245667"),
        )

# 内存缓存：phone -> (code, expire_ts)
_code_cache: dict[str, tuple[str, float]] = {}
# 发送频率限制：phone -> last_send_ts
_rate_limit: dict[str, float] = {}

RATE_LIMIT_SECONDS = 60  # 同一手机号 60 秒内只能发一次
CODE_EXPIRE_SECONDS = 300  # 验证码 5 分钟有效


def _create_client() -> DysmsapiClient:
    key_id, key_secret, _, _ = _get_sms_config()
    config = open_api_models.Config(
        access_key_id=key_id,
        access_key_secret=key_secret,
    )
    config.endpoint = ENDPOINT
    return DysmsapiClient(config)


def generate_code() -> str:
    return f"{random.randint(100000, 999999)}"


def send_verification_code(phone: str) -> tuple[bool, str]:
    """发送短信验证码，返回 (success, message)"""
    now = time.time()

    # 频率限制
    last_send = _rate_limit.get(phone, 0)
    if now - last_send < RATE_LIMIT_SECONDS:
        wait = int(RATE_LIMIT_SECONDS - (now - last_send))
        return False, f"发送过于频繁，请 {wait} 秒后重试"

    code = generate_code()

    try:
        _, _, sign_name, template_code = _get_sms_config()
        client = _create_client()
        request = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=sign_name,
            template_code=template_code,
            template_param=json.dumps({"code": code}),
        )
        runtime = util_models.RuntimeOptions()
        response = client.send_sms_with_options(request, runtime)

        if response.body.code == "OK":
            _code_cache[phone] = (code, now + CODE_EXPIRE_SECONDS)
            _rate_limit[phone] = now
            logger.info(f"短信验证码已发送至 {phone[:3]}****{phone[-4:]}")
            return True, "验证码已发送"
        else:
            logger.warning(f"短信发送失败: {response.body.code} - {response.body.message}")
            return False, f"短信发送失败: {response.body.message}"

    except Exception as e:
        logger.error(f"短信服务异常: {e}")
        return False, "短信服务暂时不可用，请稍后重试"


def verify_code(phone: str, code: str) -> bool:
    """验证短信验证码"""
    cached = _code_cache.get(phone)
    if not cached:
        return False

    stored_code, expire_ts = cached
    if time.time() > expire_ts:
        _code_cache.pop(phone, None)
        return False

    if stored_code == code:
        _code_cache.pop(phone, None)
        return True

    return False
