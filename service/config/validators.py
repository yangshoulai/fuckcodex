from __future__ import annotations

from .errors import ConfigError


def normalize_email(email: str, field_name: str) -> str:
    """标准化邮箱字符串。"""

    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ConfigError(f"字段 `{field_name}` 必须是合法的邮箱地址")
    return normalized


def normalize_base_url(value: str, field_name: str) -> str:
    """标准化 Base URL，去除结尾斜杠。"""

    text = value.strip()
    if not text:
        raise ConfigError(f"字段 `{field_name}` 必须是非空字符串")
    if not (text.startswith("http://") or text.startswith("https://")):
        raise ConfigError(f"字段 `{field_name}` 必须以 http:// 或 https:// 开头")
    return text.rstrip("/")


def normalize_path_prefix(value: str, field_name: str) -> str:
    """标准化 API 前缀，保证以 / 开头。"""

    text = value.strip()
    if not text:
        raise ConfigError(f"字段 `{field_name}` 必须是非空字符串")
    if not text.startswith("/"):
        text = f"/{text}"
    return text.rstrip("/")


__all__ = [
    "normalize_email",
    "normalize_base_url",
    "normalize_path_prefix",
]
