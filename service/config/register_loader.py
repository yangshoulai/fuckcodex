from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_HTTP_USER_AGENT,
    DEFAULT_OPENAI_REGISTER_CLIENT_ID,
    DEFAULT_QWEN_REGISTER_CLIENT_ID,
)
from .errors import ConfigError
from .models import GrokRegisterConfig, OpenAIRegisterConfig, QwenRegisterConfig
from .parse_utils import (
    parse_optional_bool,
    parse_optional_nullable_str,
    parse_optional_path,
    parse_optional_str,
    parse_positive_int,
    parse_required_str,
)


def parse_openai_register_config(registers_table: dict[str, Any], base_dir: Path) -> OpenAIRegisterConfig:
    openai_register_table = registers_table.get("openai")
    if openai_register_table is None:
        raise ConfigError("[registers.openai] 配置项缺失")
    if not isinstance(openai_register_table, dict):
        raise ConfigError("[registers.openai] 必须是表结构")

    return OpenAIRegisterConfig(
        sms_provider=parse_required_str(
            openai_register_table.get("sms_provider"),
            field_name="registers.openai.sms_provider",
        ),
        mail_provider=parse_required_str(
            openai_register_table.get("mail_provider"),
            field_name="registers.openai.mail_provider",
        ),
        oauth_client_id=parse_optional_str(
            openai_register_table.get("oauth_client_id"),
            field_name="registers.openai.oauth_client_id",
            default=DEFAULT_OPENAI_REGISTER_CLIENT_ID,
        ),
        upload_cpa_auth_file=parse_optional_bool(
            openai_register_table.get("upload_cpa_auth_file"),
            field_name="registers.openai.upload_cpa_auth_file",
            default=True,
        ),
        save_screenshot_on_error=parse_optional_bool(
            openai_register_table.get("save_screenshot_on_error"),
            field_name="registers.openai.save_screenshot_on_error",
            default=True,
        ),
        default_timeout_seconds=parse_positive_int(
            openai_register_table.get("default_timeout_seconds"),
            field_name="registers.openai.default_timeout_seconds",
            default=60,
        ),
        email_timeout_seconds=parse_positive_int(
            openai_register_table.get("email_timeout_seconds"),
            field_name="registers.openai.email_timeout_seconds",
            default=60,
        ),
        email_retries=parse_positive_int(
            openai_register_table.get("email_retries"),
            field_name="registers.openai.email_retries",
            default=3,
        ),
        callback_server_port=parse_positive_int(
            openai_register_table.get("callback_server_port"),
            field_name="registers.openai.callback_server_port",
            default=1455,
        ),
        chrome_binary_path=parse_optional_nullable_str(
            openai_register_table.get("chrome_binary_path"),
            field_name="registers.openai.chrome_binary_path",
            default=None,
        ),
        chrome_proxy=parse_optional_nullable_str(
            openai_register_table.get("chrome_proxy"),
            field_name="registers.openai.chrome_proxy",
            default=None,
        ),
        headless=parse_optional_bool(
            openai_register_table.get("headless"),
            field_name="registers.openai.headless",
            default=False,
        ),
        user_agent=parse_optional_nullable_str(
            openai_register_table.get("user_agent"),
            field_name="registers.openai.user_agent",
            default=DEFAULT_HTTP_USER_AGENT,
        ),
        default_account_password=parse_optional_nullable_str(
            openai_register_table.get("default_account_password"),
            field_name="registers.openai.default_account_password",
            default=None,
        ),
        auth_file_dir=parse_optional_path(
            openai_register_table.get("auth_file_dir"),
            field_name="registers.openai.auth_file_dir",
            base_dir=base_dir,
            default=(base_dir / "accounts").resolve(),
        ),
    )


def parse_grok_register_config(registers_table: dict[str, Any], base_dir: Path) -> GrokRegisterConfig:
    grok_register_table = registers_table.get("grok")
    if grok_register_table is None:
        raise ConfigError("[registers.grok] 配置项缺失")
    if not isinstance(grok_register_table, dict):
        raise ConfigError("[registers.grok] 必须是表结构")

    return GrokRegisterConfig(
        mail_provider=parse_required_str(
            grok_register_table.get("mail_provider"),
            field_name="registers.grok.mail_provider",
        ),
        save_screenshot_on_error=parse_optional_bool(
            grok_register_table.get("save_screenshot_on_error"),
            field_name="registers.grok.save_screenshot_on_error",
            default=True,
        ),
        default_timeout_seconds=parse_positive_int(
            grok_register_table.get("default_timeout_seconds"),
            field_name="registers.grok.default_timeout_seconds",
            default=60,
        ),
        email_timeout_seconds=parse_positive_int(
            grok_register_table.get("email_timeout_seconds"),
            field_name="registers.grok.email_timeout_seconds",
            default=60,
        ),
        chrome_binary_path=parse_optional_nullable_str(
            grok_register_table.get("chrome_binary_path"),
            field_name="registers.grok.chrome_binary_path",
            default=None,
        ),
        chrome_proxy=parse_optional_nullable_str(
            grok_register_table.get("chrome_proxy"),
            field_name="registers.grok.chrome_proxy",
            default=None,
        ),
        headless=parse_optional_bool(
            grok_register_table.get("headless"),
            field_name="registers.grok.headless",
            default=False,
        ),
        user_agent=parse_optional_nullable_str(
            grok_register_table.get("user_agent"),
            field_name="registers.grok.user_agent",
            default=DEFAULT_HTTP_USER_AGENT,
        ),
        default_account_password=parse_optional_nullable_str(
            grok_register_table.get("default_account_password"),
            field_name="registers.grok.default_account_password",
            default=None,
        ),
        account_file_dir=parse_optional_path(
            grok_register_table.get("account_file_dir"),
            field_name="registers.grok.account_file_dir",
            base_dir=base_dir,
            default=(base_dir / "accounts").resolve(),
        ),
    )


def parse_qwen_register_config(registers_table: dict[str, Any], base_dir: Path) -> QwenRegisterConfig:
    qwen_register_table = registers_table.get("qwen")
    if qwen_register_table is None:
        raise ConfigError("[registers.qwen] 配置项缺失")
    if not isinstance(qwen_register_table, dict):
        raise ConfigError("[registers.qwen] 必须是表结构")

    return QwenRegisterConfig(
        oauth_client_id=parse_optional_str(
            qwen_register_table.get("oauth_client_id"),
            field_name="registers.qwen.oauth_client_id",
            default=DEFAULT_QWEN_REGISTER_CLIENT_ID,
        ),
        upload_cpa_auth_file=parse_optional_bool(
            qwen_register_table.get("upload_cpa_auth_file"),
            field_name="registers.qwen.upload_cpa_auth_file",
            default=True,
        ),
        mail_provider=parse_required_str(
            qwen_register_table.get("mail_provider"),
            field_name="registers.qwen.mail_provider",
        ),
        save_screenshot_on_error=parse_optional_bool(
            qwen_register_table.get("save_screenshot_on_error"),
            field_name="registers.qwen.save_screenshot_on_error",
            default=True,
        ),
        default_timeout_seconds=parse_positive_int(
            qwen_register_table.get("default_timeout_seconds"),
            field_name="registers.qwen.default_timeout_seconds",
            default=60,
        ),
        email_timeout_seconds=parse_positive_int(
            qwen_register_table.get("email_timeout_seconds"),
            field_name="registers.qwen.email_timeout_seconds",
            default=60,
        ),
        chrome_binary_path=parse_optional_nullable_str(
            qwen_register_table.get("chrome_binary_path"),
            field_name="registers.qwen.chrome_binary_path",
            default=None,
        ),
        chrome_proxy=parse_optional_nullable_str(
            qwen_register_table.get("chrome_proxy"),
            field_name="registers.qwen.chrome_proxy",
            default=None,
        ),
        headless=parse_optional_bool(
            qwen_register_table.get("headless"),
            field_name="registers.qwen.headless",
            default=False,
        ),
        user_agent=parse_optional_nullable_str(
            qwen_register_table.get("user_agent"),
            field_name="registers.qwen.user_agent",
            default=DEFAULT_HTTP_USER_AGENT,
        ),
        default_account_password=parse_optional_nullable_str(
            qwen_register_table.get("default_account_password"),
            field_name="registers.qwen.default_account_password",
            default=None,
        ),
        auth_file_dir=parse_optional_path(
            qwen_register_table.get("auth_file_dir"),
            field_name="registers.qwen.auth_file_dir",
            base_dir=base_dir,
            default=(base_dir / "accounts").resolve(),
        ),
    )


__all__ = [
    "parse_openai_register_config",
    "parse_grok_register_config",
    "parse_qwen_register_config",
]
