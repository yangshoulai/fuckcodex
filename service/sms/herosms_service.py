import json
from typing import Any, Tuple

from service.base_sms_service import BaseSmsService
from service.config.models import HeroSmsConfig
from service.http_service import HttpService
from util.logger import get_logger

LOGGER = get_logger("HeroSmsService")


class HeroSmsService(BaseSmsService):
    """HeroSMS 服务封装。"""

    def __init__(self, config: HeroSmsConfig, http_service: HttpService):
        self._config = config
        self._http_service = http_service

    def generate_phone_number(self) -> dict[str, Any] | None:
        try:
            _params = {
                "action": "getNumberV2",
                "service": self._config.service_Id,
                "country": self._config.country,
            }
            if self._config.max_price:
                _params["maxPrice"] = self._config.max_price
            return self._get(params=_params)
        except Exception as exc:
            LOGGER.warning(f"购买手机号异常：{str(exc)}")
            return None

    def get_activation_code(self, phone_number: dict[str, Any]) -> str:
        activation_id = phone_number.get("activationId")
        try:
            _params = {
                "action": "getStatusV2",
                "id": activation_id
            }
            return self._get(params=_params).get("sms", {}).get("code", "")
        except Exception as exc:
            LOGGER.warning(f"获取激活短信异常：{str(exc)}")
            return ""

    def _get(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        _params = params or {}
        _params["api_key"] = self._config.api_key
        resp = self._http_service.get(self._config.api_url, params=_params, raise_for_status=True)
        if self.is_json(resp.text):
            return resp.json()
        raise ValueError(resp.text)

    @staticmethod
    def is_json(s: str) -> Tuple[bool, dict[str, Any] | None]:
        try:
            o = json.loads(s)
            return True, o
        except (TypeError, json.JSONDecodeError):
            return False, None
