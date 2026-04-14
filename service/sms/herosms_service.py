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

    def generate_phone_number(
            self,
            *,
            service_id: str | None = None,
            country: int = 0,
            max_price: float | None = None,
            phone_number_prefix: str | None = None,
    ) -> dict[str, Any] | None:
        if not service_id:
            raise ValueError("generate_phone_number 缺少 service_id")

        try:
            _params = {
                "action": "getNumberV2",
                "service": service_id,
                "country": country,
            }
            if max_price is not None:
                _params["maxPrice"] = max_price

            phone_number = self._get(params=_params)
            if phone_number_prefix:
                full_number = (
                        phone_number.get("phoneNumber")
                        or phone_number.get("phone_number")
                        or phone_number.get("number")
                        or ""
                )
                if full_number and not str(full_number).startswith(phone_number_prefix):
                    LOGGER.info(f"手机号前缀不匹配，期望前缀={phone_number_prefix}，实际手机号={full_number}")
                    return None
            return phone_number
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
        is_json, payload = self.is_json(resp.text)
        if is_json and isinstance(payload, dict):
            return payload
        raise ValueError(resp.text)

    @staticmethod
    def is_json(s: str) -> Tuple[bool, dict[str, Any] | None]:
        try:
            o = json.loads(s)
            return True, o
        except (TypeError, json.JSONDecodeError):
            return False, None
