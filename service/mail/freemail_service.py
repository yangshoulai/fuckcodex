from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

from service.base_mail_service import MailFilter, MailBox, BaseMailService, Mail
from service.config_service import ConfigService, FreeMailConfig, HttpConfig
from service.http_service import HttpService, HttpServiceError

_OTP_PATTERN = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")


@dataclass(frozen=True)
class FreeMailEmailSummary:
    """邮件摘要信息。"""

    id: int
    sender: str
    subject: str
    received_at: str
    is_read: int
    preview: str
    verification_code: str


@dataclass(frozen=True)
class FreeMailEmailContent:
    """邮件详情信息。"""

    id: int
    sender: str
    to_addrs: str
    subject: str
    content: str
    html_content: str
    received_at: str
    is_read: int


class FreeMailApiError(RuntimeError):
    """FreeMail 接口调用异常。"""

    def __init__(self, message: str, *, http_status: int | None = None, response: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.response = response


class FreeMailService(BaseMailService):
    """FreeMail 服务封装。"""

    def __init__(self, config: FreeMailConfig, http_service: HttpService | None = None):
        self._config = config
        self._http_service = http_service

    def generate_mail_box(self) -> MailBox:
        """随机生成新的临时邮箱。"""
        payload = self._request_json(
            method="GET",
            path="/api/generate",
            query={"length": self._config.email_length, "domainIndex": self._config.domain_index},
        )
        email = payload.get("email")
        return MailBox(email=email)

    # def get_latest_verification_code(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> str:
    #     """
    #     获取最新验证码。
    #
    #     """
    #     messages: list[Mail] = self.get_latest_emails(mail_box, mail_filter, verification_code_regex)
    #     if messages:
    #         for message in messages:
    #             if message.verification_code:
    #                 return message.verification_code
    #     return ""

    def get_latest_emails(self, mail_box: MailBox, mail_filter: MailFilter | None = None, verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        """获取最新邮件。"""
        if mail_filter and not callable(mail_filter):
            raise ValueError("mail_filter 必须是可调用对象")

        mail_items = self._fetch_latest_emails(mail_box.email)
        messages = []
        for item in mail_items:
            verification_code = item.verification_code
            if not verification_code:
                verification_code = self.extract_verification_code([item.subject, item.preview], verification_code_regex)
            mail = Mail(
                sender=item.sender,
                subject=item.subject,
                receive_at=item.received_at,
                content=self._fetch_email_content(item.id),
                verification_code=verification_code,
            )
            if (not mail_filter) or mail_filter(mail):
                messages.append(mail)
        return messages

    def _fetch_latest_emails(self, email_address: str) -> list[FreeMailEmailSummary]:
        """获取最新邮件摘要列表。"""
        payload = self._request_json(
            method="GET",
            path="/api/emails",
            query={"mailbox": email_address, "limit": self._config.max_probe_emails},
        )

        if isinstance(payload, dict):
            data = payload.get("data", [])
        else:
            data = payload

        if not isinstance(data, list):
            raise FreeMailApiError("获取邮件列表失败：接口返回格式错误", response=payload)

        emails: list[FreeMailEmailSummary] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            mail_id = self._to_int(item.get("id"))
            if mail_id is None:
                continue

            emails.append(
                FreeMailEmailSummary(
                    id=mail_id,
                    sender=self._to_str(item.get("sender")),
                    subject=self._to_str(item.get("subject")),
                    received_at=datetime.strptime(self._to_str(item.get("received_at")), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(
                        ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
                    is_read=self._to_int(item.get("is_read"), default=0) or 0,
                    preview=self._to_str(item.get("preview")),
                    verification_code=self._to_str(item.get("verification_code")),
                )
            )
        return emails

    def _fetch_email_content(self, email_id: int) -> str:
        """获取邮件内容"""
        payload = self._request_json(method="GET", path=f"/api/email/{email_id}")
        if payload:
            return payload["html_content"]
        else:
            return ""

    def _request_json(
            self,
            *,
            method: str,
            path: str,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        response = self._request(method=method, path=path, query=query, body=body)
        return response.json()

    def _request(
            self,
            *,
            method: str,
            path: str,
            query: dict[str, Any] | None = None,
            body: dict[str, Any] | None = None,
    ):
        request_url = self._build_request_url(path)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-admin-token": self._config.admin_token,
        }

        try:
            response = self._http_service.request(
                method=method,
                url=request_url,
                params=query,
                json_body=body,
                headers=headers,
                raise_for_status=False,
            )
        except HttpServiceError as error:
            raise FreeMailApiError(
                message=str(error),
                http_status=error.status_code,
                response=error.response_text,
            ) from error

        parsed = response.json()
        if response.status_code >= 400:
            raise FreeMailApiError(
                message=f"FreeMail HTTP 错误: {response.status_code}",
                http_status=response.status_code,
                response=parsed,
            )
        return response

    def _build_request_url(self, path: str) -> str:
        clean_path = path.strip()
        if not clean_path:
            raise ValueError("path 不能为空")
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"
        return f"{self._config.base_url}{clean_path}"

    @staticmethod
    def _to_str(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _to_int(value: Any, default: int | None = None) -> int | None:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip())
            except ValueError:
                return default
        return default
