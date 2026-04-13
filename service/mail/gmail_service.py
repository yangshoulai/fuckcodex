from __future__ import annotations

import base64
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import google_auth_httplib2
import httplib2
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from service.base_mail_service import MailFilter, BaseMailService, MailBox, Mail
from service.config_service import GmailConfig

MessageFormat = Literal["minimal", "full", "raw", "metadata"]
DEFAULT_USER_ID = "me"


@dataclass(frozen=True)
class MessageRef:
    """邮件引用信息。"""

    id: str
    thread_id: str


class GmailService(BaseMailService):
    """Gmail 业务服务，负责邮件查询与删除。"""

    def __init__(self, config: GmailConfig, client: Resource | None = None):
        self._config = config
        self._client = client or self._build_client(config)

    def generate_mail_box(self) -> MailBox:
        """
        基于当前配置邮箱生成新的 Gmail 别名邮箱。

        默认使用 plus addressing，例如：
        user@gmail.com -> user+abc123xy@gmail.com
        """

        base_email = self._normalize_email(self._config.email)
        local_part, domain = base_email.split("@", 1)
        base_local = local_part.split("+", 1)[0]

        clean_alias = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(self._config.email_length))

        return MailBox(email=f"{base_local}+{clean_alias}@{domain}")

    def get_latest_verification_code(self, mail_box: MailBox, mail_filter: MailFilter | None = None, client: Resource | None = None,
                                     verification_code_regex: re.Pattern | None = None) -> str:
        """
        获取最近一次验证码。
        """
        messages = self.get_latest_emails(mail_box, mail_filter, client, verification_code_regex)
        if messages:
            for message in messages:
                if message.verification_code:
                    return message.verification_code
        return ""

    def get_latest_emails(self, mail_box: MailBox, mail_filter: MailFilter | None = None, client: Resource | None = None,
                          verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        """获取最新邮件。"""
        if mail_filter and not callable(mail_filter):
            raise ValueError("mail_filter 必须是可调用对象")

        client = client or self._client

        message_refs = self._list_messages(query=f"to:{mail_box.email}", client=client)
        messages = []
        if message_refs:
            for item in message_refs:
                message = self._get_message(item.id, fmt="full", client=client)
                mail_from = self._extract_from(message)
                subject = self._extract_subject(message)
                receive_at = self._format_receive_at(message)
                content = self.extract_text_from_message(message)
                verification_code = self._extract_verification_code(message, verification_code_regex)
                mail = Mail(
                    sender=mail_from,
                    subject=subject,
                    receive_at=receive_at,
                    content=content,
                    verification_code=verification_code,
                )
                if mail_filter and not mail_filter(mail):
                    continue
                messages.append(mail)
        return messages

    def get_target_mailbox_latest_verification_code(self, target_mail_box: str, mail_box: MailBox, mail_filter: MailFilter | None = None,
                                                    verification_code_regex: re.Pattern | None = None) -> str:
        conf: GmailConfig = GmailConfig(email=target_mail_box, email_length=self._config.email_length, default_max_results=self._config.default_max_results,
                                        proxy=self._config.proxy, api=self._config.api)
        client = self._build_client(conf)
        return self.get_latest_verification_code(mail_box, mail_filter, client, verification_code_regex)

    def get_target_mailbox_latest_emails(self, target_mail_box: str, mail_box: MailBox, mail_filter: MailFilter | None = None,
                                         verification_code_regex: re.Pattern | None = None) -> list[Mail]:
        conf: GmailConfig = GmailConfig(email=target_mail_box, email_length=self._config.email_length, default_max_results=self._config.default_max_results,
                                        proxy=self._config.proxy, api=self._config.api)
        client = self._build_client(conf)
        return self.get_latest_emails(mail_box, mail_filter, client, verification_code_regex)

    def _list_messages(self, query: str | None = None, client: Resource | None = None) -> list[MessageRef]:
        """获取邮件列表（仅返回邮件 ID 与线程 ID）。"""
        client = client or self._client

        request_kwargs: dict[str, Any] = {
            "userId": DEFAULT_USER_ID,
            "maxResults": self._config.default_max_results,
            "includeSpamTrash": True,
        }
        if query:
            request_kwargs["q"] = query

        response = client.users().messages().list(**request_kwargs).execute()
        return [
            MessageRef(id=item["id"], thread_id=item["threadId"])
            for item in response.get("messages", [])
        ]

    def _get_message(self, message_id: str, fmt: MessageFormat = "full", client: Resource | None = None) -> dict[str, Any]:
        """根据邮件 ID 获取邮件详情。"""
        client = client or self._client
        return (
            client.users()
            .messages()
            .get(userId=DEFAULT_USER_ID, id=message_id, format=fmt)
            .execute()
        )

    @staticmethod
    def extract_text_from_message(message: dict) -> str:
        payload = message.get("payload", {})

        def _decode_base64url(data: str) -> str:
            padding = "=" * (-len(data) % 4)
            return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")

        def walk(part: dict) -> str | None:
            mime = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")

            # 优先 text/plain
            if mime.startswith("text/plain") and data:
                return _decode_base64url(data)

            for child in part.get("parts", []) or []:
                text = walk(child)
                if text:
                    return text

            # 兜底 text/html
            if mime.startswith("text/html") and data:
                return _decode_base64url(data)
            return None

        return walk(payload) or message.get("snippet", "")

    @staticmethod
    def _extract_headers(message: dict[str, Any]) -> dict[str, str]:
        payload = message.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        result: dict[str, str] = {}
        for item in headers:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = str(item.get("value") or "").strip()
            if name:
                result[name.lower()] = value
        return result

    def _extract_from(self, message: dict[str, Any]) -> str:
        return self._extract_headers(message).get("from", "")

    def _extract_subject(self, message: dict[str, Any]) -> str:
        return self._extract_headers(message).get("subject", "")

    def _format_receive_at(self, message: dict[str, Any]) -> str:
        timestamp = self._extract_internal_timestamp(message)
        if timestamp > 0:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        raw_date = self._extract_headers(message).get("date", "")
        if raw_date:
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, IndexError):
                pass

        return "1970-01-01 00:00:00"

    @staticmethod
    def _extract_internal_timestamp(message: dict[str, Any]) -> int:
        raw = str(message.get("internalDate") or "").strip()
        if not raw.isdigit():
            return 0
        value = int(raw)
        return value // 1000 if value > 1_000_000_000_000 else value

    def _extract_verification_code(self, message: dict[str, Any], pattern: re.Pattern) -> str | None:
        texts = [
            self._extract_headers(message).get("subject", ""),
            str(message.get("snippet") or ""),
            self.extract_text_from_message(message),
        ]
        return self.extract_verification_code(texts, pattern)

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("当前配置邮箱不是合法的 Gmail 地址")
        return normalized

    @staticmethod
    def _normalize_alias(alias: str) -> str:
        normalized = alias.strip().lower()
        if not normalized:
            raise ValueError("alias 不能为空")
        if not re.fullmatch(r"[a-z0-9._-]+", normalized):
            raise ValueError("alias 仅支持字母、数字、点、下划线和中划线")
        return normalized

    @staticmethod
    def _build_proxy_session(proxy: str | None) -> requests.Session | None:
        """根据代理地址构建 requests 会话。"""

        if not proxy:
            return None

        session = requests.Session()
        session.proxies.update({
            "http": proxy,
            "https": proxy,
        })
        return session

    @staticmethod
    def _build_google_http(proxy: str | None, creds: Credentials) -> google_auth_httplib2.AuthorizedHttp:
        """构建带鉴权的 Gmail HTTP 传输对象。"""

        proxy_info = None
        if proxy:
            if httplib2.socks is None:
                raise RuntimeError("当前环境缺少 PySocks，无法为 Gmail API 启用代理")
            proxy_info = httplib2.proxy_info_from_url(proxy, method="https")

        http = httplib2.Http(proxy_info=proxy_info)
        return google_auth_httplib2.AuthorizedHttp(creds, http=http)

    @staticmethod
    def _build_client(config: GmailConfig) -> Resource:
        """根据当前邮箱配置创建 Gmail API 客户端，并自动处理 token 刷新。"""

        creds: Credentials | None = None
        api_config = config.api
        proxy_session = GmailService._build_proxy_session(config.proxy)

        credentials_file = config.resolve_credentials_file()
        token_file = config.resolve_token_file()

        if token_file.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_file),
                list(api_config.scopes),
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request(session=proxy_session) if proxy_session else Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file),
                    list(api_config.scopes),
                )
                if proxy_session:
                    flow.oauth2session.proxies.update(dict(proxy_session.proxies))
                creds = flow.run_local_server(port=0)

            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json(), encoding="utf-8")

        authed_http = GmailService._build_google_http(config.proxy, creds)
        return build("gmail", "v1", http=authed_http, cache_discovery=False)
