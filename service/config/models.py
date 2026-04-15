from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_GMAIL_SCOPES,
    DEFAULT_HTTP_IMPERSONATE,
    DEFAULT_HTTP_USER_AGENT,
    DEFAULT_OPENAI_REGISTER_CLIENT_ID,
    DEFAULT_QWEN_REGISTER_CLIENT_ID,
)
from .validators import normalize_email


@dataclass(frozen=True)
class HeroSmsConfig:
    """HeroSMS 配置。"""
    api_key: str
    api_url: str = "https://hero-sms.com/stubs/handler_api.php"


@dataclass(frozen=True)
class OpenAIHeroSmsConfig:
    """OpenAI 场景下 HeroSMS 业务参数。"""

    service_id: str
    country: int = 0
    max_price: float | None = None
    phone_number_prefix: str | None = None


@dataclass(frozen=True)
class GmailApiConfig:
    """Gmail API 配置（单 client_secret，多 token）。"""

    credentials_file: Path
    token_dir: Path
    scopes: tuple[str, ...] = DEFAULT_GMAIL_SCOPES

    def resolve_token_file(self, email: str) -> Path:
        """按规则生成 token 文件路径：<邮箱>.json。"""

        normalized_email = normalize_email(email, "services.gmail.email")
        return self.token_dir / f"{normalized_email}.json"


@dataclass(frozen=True)
class GmailConfig:
    """Gmail 服务业务配置。"""

    api: GmailApiConfig
    email: str
    email_length: int = 8
    default_max_results: int = 20
    proxy: str | None = None

    def resolve_token_file(self) -> Path:
        """获取当前邮箱对应的 token 文件路径。"""

        return self.api.resolve_token_file(self.email)

    def resolve_credentials_file(self) -> Path:
        """获取 OAuth 凭证文件路径（全局唯一）。"""

        return self.api.credentials_file


@dataclass(frozen=True)
class LuckMailConfig:
    """LuckMail API 配置。"""

    base_url: str
    api_key: str
    project_code: str
    email_type: str | None = None
    variant_mode: str | None = None
    domain: str | None = None


@dataclass(frozen=True)
class FreeMailConfig:
    """FreeMail API 配置。"""

    base_url: str
    admin_token: str
    email_length: int = 8
    domain_index: int = 0
    max_probe_emails: int = 10


@dataclass(frozen=True)
class DuckMailConfig:
    """DuckMail API 配置。"""

    base_url: str
    authorization_token: str
    forward_gmail: str


@dataclass(frozen=True)
class FirefoxRelayConfig:
    """Firefox Relay API 配置。"""

    session_id: str
    csrf_token: str
    forward_gmail: str
    base_url: str = "https://relay.firefox.com"


@dataclass(frozen=True)
class HttpConfig:
    """通用 HTTP 客户端配置。"""

    timeout_seconds: int = 60
    verify_ssl: bool = True
    user_agent: str = DEFAULT_HTTP_USER_AGENT
    proxy: str | None = None
    http_proxy: str | None = None
    https_proxy: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    impersonate: str | None = DEFAULT_HTTP_IMPERSONATE
    ja3: str | None = None
    akamai: str | None = None
    extra_fp: dict[str, Any] = field(default_factory=dict)
    default_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CpaConfig:
    """CPA 服务配置。"""

    base_url: str
    management_password: str


@dataclass(frozen=True)
class OpenAIRegisterConfig:
    """OpenAI 注册服务配置。"""

    mail_provider: str
    sms_provider: str | None = None
    sms_config: dict[str, Any] = field(default_factory=dict)
    oauth_client_id: str = DEFAULT_OPENAI_REGISTER_CLIENT_ID
    upload_cpa_auth_file: bool = True
    save_screenshot_on_error: bool = True
    default_timeout_seconds: int = 60
    email_timeout_seconds: int = 60
    email_retries: int = 3
    callback_server_port: int = 1455
    chrome_binary_path: str | None = None
    chrome_proxy: str | None = None
    headless: bool = False
    user_agent: str = DEFAULT_HTTP_USER_AGENT
    default_account_password: str | None = None
    auth_file_dir: Path = field(default_factory=lambda: (Path.cwd() / "accounts").resolve())


@dataclass(frozen=True)
class GrokRegisterConfig:
    """Grok 注册服务配置。"""

    mail_provider: str
    save_screenshot_on_error: bool = True
    default_timeout_seconds: int = 60
    email_timeout_seconds: int = 60
    chrome_binary_path: str | None = None
    chrome_proxy: str | None = None
    headless: bool = False
    user_agent: str = DEFAULT_HTTP_USER_AGENT
    default_account_password: str | None = None
    account_file_dir: Path = field(default_factory=lambda: (Path.cwd() / "accounts").resolve())


@dataclass(frozen=True)
class QwenRegisterConfig:
    """千问注册服务配置。"""

    mail_provider: str
    oauth_client_id: str = DEFAULT_QWEN_REGISTER_CLIENT_ID
    upload_cpa_auth_file: bool = True
    save_screenshot_on_error: bool = True
    default_timeout_seconds: int = 60
    email_timeout_seconds: int = 60
    chrome_binary_path: str | None = None
    chrome_proxy: str | None = None
    headless: bool = False
    user_agent: str = DEFAULT_HTTP_USER_AGENT
    default_account_password: str | None = None
    auth_file_dir: Path = field(default_factory=lambda: (Path.cwd() / "accounts").resolve())


@dataclass(frozen=True)
class AppConfig:
    """应用结构化配置对象。"""

    openai_register: OpenAIRegisterConfig
    grok_register: GrokRegisterConfig
    qwen_register: QwenRegisterConfig
    gmail: GmailConfig | None = None
    luckmail: LuckMailConfig | None = None
    freemail: FreeMailConfig | None = None
    duckmail: DuckMailConfig | None = None
    firefoxrelay: FirefoxRelayConfig | None = None

    herosms: HeroSmsConfig | None = None

    http: HttpConfig = field(default_factory=HttpConfig)
    cpa: CpaConfig | None = None


__all__ = [
    "HeroSmsConfig",
    "OpenAIHeroSmsConfig",
    "GmailApiConfig",
    "GmailConfig",
    "LuckMailConfig",
    "FreeMailConfig",
    "DuckMailConfig",
    "FirefoxRelayConfig",
    "HttpConfig",
    "CpaConfig",
    "OpenAIRegisterConfig",
    "GrokRegisterConfig",
    "QwenRegisterConfig",
    "AppConfig",
]
