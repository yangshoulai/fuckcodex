from typing import Any


class BaseSmsService:
    """短信服务。"""

    def generate_phone_number(
            self,
            *,
            service_id: str | None = None,
            country: int = 0,
            max_price: float | None = None,
            phone_number_prefix: str | None = None,
    ) -> dict[str, Any] | None:
        """获取新的手机号。"""
        raise NotImplementedError

    def get_activation_code(self, phone_number: dict[str, Any]) -> str:
        """获取手机验证码。"""
        raise NotImplementedError
