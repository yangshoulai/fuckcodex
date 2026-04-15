import json
from typing import Any, Tuple

from service.base_sms_service import BaseSmsService
from service.config.models import HeroSmsConfig
from service.http_service import HttpService
from util.logger import get_logger

LOGGER = get_logger("HeroSmsService")


class HeroSmsService(BaseSmsService):
    """HeroSMS 服务封装。"""

    def __init__(self, config: HeroSmsConfig, http_service: HttpService, register_sms_config: dict[str, Any] = {}):
        self._config = config
        self._register_sms_config = register_sms_config
        self._http_service = http_service

    def generate_phone_number(self) -> dict[str, Any] | None:
        service_id = self._register_sms_config.get("herosms_service_id")
        if not service_id:
            raise ValueError("generate_phone_number 缺少 herosms_service_id")
        country = self._register_sms_config.get("herosms_country")
        if not country:
            raise ValueError("generate_phone_number 缺少 herosms_country")
        max_price = self._register_sms_config.get("herosms_max_price", "")

        try:
            _params = {
                "action": "getNumberV2",
                "service": service_id,
                "country": country,
            }
            if max_price is not None:
                _params["maxPrice"] = max_price

            phone_number = self._get(params=_params)
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
            resp = self._get(params=_params)
            if resp and "sms" in resp and "code" in resp["sms"]:
                return self._get(params=_params).get("sms").get("code")
            return ""
        except Exception as exc:
            LOGGER.warning(f"获取激活短信异常：{str(exc)}")
            return ""

    def cancel_activation(self, phone_number: dict[str, Any]):
        """取消手机验证码。"""
        activation_id = phone_number.get("activationId")
        try:
            _params = {
                "action": "setStatus",
                "id": activation_id,
                "status": "8"
            }
            status = self._get(params=_params, expect_json=False)
            LOGGER.info(f"取消激活[activation_id={activation_id}], response text = {status}")
        except Exception as exc:
            LOGGER.warning(f"取消激活短信[activation_id={activation_id}]异常：{str(exc)}")

    def _get(self, params: dict[str, Any] | None = None, expect_json: bool = True) -> dict[str, Any] | str:
        _params = params or {}
        _params["api_key"] = self._config.api_key
        resp = self._http_service.get(self._config.api_url, params=_params, raise_for_status=True)

        if expect_json:
            if not self.is_json(resp.text)[0]:
                raise ValueError(resp.text)
            return resp.json()
        else:
            return resp.text

    @staticmethod
    def is_json(s: str) -> Tuple[bool, dict[str, Any] | None]:
        try:
            o = json.loads(s)
            return True, o
        except (TypeError, json.JSONDecodeError):
            return False, None
