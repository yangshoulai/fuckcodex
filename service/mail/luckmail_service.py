from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from service.base_mail_service import MailFilter, BaseMailService, MailBox, Mail
from service.config_service import LuckMailConfig
from service.http_service import HttpService, HttpServiceError


@dataclass(frozen=True)
class LuckMailHttpResult:
    """LuckMail HTTP 调用结果。"""

    status_code: int
    payload: Any


class LuckMailApiError(RuntimeError):
    """LuckMail 接口调用异常。"""

    def __init__(
            self,
            message: str,
            *,
            http_status: int | None = None,
            business_code: int | None = None,
            response: Any = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.business_code = business_code
        self.response = response


class LuckMailService(BaseMailService):
    """LuckMail 服务封装（用户 OpenAPI）。"""

    def __init__(self, config: LuckMailConfig, http_service: HttpService):
        self._config = config
        self._http_service = http_service

    def query_balance(self) -> float:
        """查询账户余额。"""
        return self._request_json(
            method="GET",
            path="/balance",
            use_api_key=True,
        ).get("balance", 0.0)

    def generate_mail_box(self) -> MailBox:
        """购买邮箱。"""

        body: dict[str, Any] = {
            "project_code": self._config.project_code.strip(),
            "quantity": 1,
        }
        if self._config.email_type:
            body["email_type"] = self._config.email_type
        if self._config.domain:
            body["domain"] = self._config.domain
        if self._config.variant_mode:
            body["variant_mode"] = self._config.variant_mode

        purchases = self._request_json(method="POST", path="/email/purchase", body=body, use_api_key=True).get("purchases", [])

        if len(purchases) == 0:
            raise LuckMailApiError("购买邮箱失败：无邮箱返回")

        email = purchases[0].get("email_address", "")
        return MailBox(email=email, extras=purchases[0])

    # def get_latest_verification_code(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> str:
    #     """通过 Token 获取最新验证码。"""
    #
    #     messages = self.get_latest_emails(mail_box=mail_box, mail_filter=mail_filter)
    #     if messages:
    #         for mail in messages:
    #             if mail.verification_code:
    #                 return mail.verification_code
    #     return ""

    def get_latest_emails(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        """获取最新邮件。"""

        if mail_filter and not callable(mail_filter):
            raise ValueError("mail_filter 必须是可调用对象")

        clean_token = mail_box.extras.get("token", "")
        if not clean_token:
            raise ValueError("token 不能为空")

        data = self._request_json(method="GET", path=f"/email/token/{clean_token}/mails", use_api_key=False)
        mails = data.get("mails", [])
        messages: list[Mail] = []
        for mail in mails:
            parsed_mail = Mail(
                sender=mail.get("from"),
                subject=mail.get("subject"),
                receive_at=mail.get("received_at"),
                content=mail.get("body"),
                verification_code=self.extract_verification_code([mail.get("subject"), mail.get("body")], verification_code_regex),
            )
            if (not mail_filter) or mail_filter(parsed_mail):
                messages.append(parsed_mail)
        return messages

    def _request_json(
            self,
            *,
            method: str,
            path: str,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
            use_api_key: bool,
    ) -> dict[str, Any]:
        """发送请求并返回 JSON 结构。"""

        result = self._request(
            method=method,
            path=path,
            query=query,
            body=body,
            use_api_key=use_api_key,
        )

        if not isinstance(result.payload, dict):
            raise LuckMailApiError(
                "接口返回非 JSON 对象",
                http_status=result.status_code,
                response=result.payload,
            )

        business_code = result.payload.get("code")
        if business_code is not None and business_code != 0:
            raise LuckMailApiError(
                message=result.payload.get("message") or "LuckMail 业务错误",
                http_status=result.status_code,
                business_code=business_code,
                response=result.payload,
            )

        return result.payload.get("data", {})

    def _request(
            self,
            *,
            method: str,
            path: str,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
            use_api_key: bool,
    ) -> LuckMailHttpResult:
        """底层 HTTP 请求。"""

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if use_api_key:
            headers["X-API-Key"] = self._config.api_key

        try:
            response = self._http_service.request(
                method=method,
                url=f"{self._config.base_url}{path}",
                params=query,
                json_body=body,
                headers=headers,
                raise_for_status=False,
            )
        except HttpServiceError as error:
            raise LuckMailApiError(
                message=str(error),
                http_status=error.status_code,
                response=error.response_text,
            ) from error

        parsed = response.json()
        if response.status_code >= 400:
            raise LuckMailApiError(
                message=f"LuckMail HTTP 错误: {response.status_code}",
                http_status=response.status_code,
                response=parsed,
            )

        return LuckMailHttpResult(status_code=response.status_code, payload=parsed)
