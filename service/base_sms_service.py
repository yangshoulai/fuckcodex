from typing import Any


class BaseSmsService:
    """短信服务。"""

    def generate_phone_number(self) -> dict[str, Any] | None:
        """获取新的手机号。"""
        raise NotImplementedError

    def get_activation_code(self, phone_number: dict[str, Any]) -> str:
        """获取手机验证码。"""
        raise NotImplementedError

    def cancel_activation(self, phone_number: dict[str, Any]):
        """取消手机验证码。"""
        raise NotImplementedError
