from typing import Any

from service.base_sms_service import BaseSmsService
from service.config import AppConfig, HttpConfig
from service.http_service import HttpService
from service.sms.herosms_service import HeroSmsService


def create_sms_service(app_config: AppConfig, provider: str, register_sms_config: dict[str, Any] = {},
                       http_service: HttpService | None = None) -> BaseSmsService:
    """创建短信服务。"""
    http_service = http_service if http_service else _create_default_http_service(app_config.http)

    if provider == "herosms":
        if app_config.herosms is None:
            raise RuntimeError("provider=herosms 时缺少 [services.herosms] 配置")
        return HeroSmsService(app_config.herosms, http_service, register_sms_config)

    raise RuntimeError(f"暂不支持的短信服务 provider: {provider}")


def _create_default_http_service(http_config: HttpConfig | None = None) -> HttpService:
    http_config = http_config if http_config else HttpConfig()
    return HttpService(config=http_config)
