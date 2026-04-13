from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import DEFAULT_GMAIL_SCOPES
from .errors import ConfigError
from .validators import normalize_email


def require_table(data: dict[str, Any], key: str, full_name: str | None = None) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        table_name = full_name or key
        raise ConfigError(f"缺少配置表: [{table_name}]")
    return value


def parse_email(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"字段 `{field_name}` 必须是字符串")
    return normalize_email(value, field_name)


def parse_required_path(value: Any, field_name: str, base_dir: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"字段 `{field_name}` 必须是非空字符串")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def parse_optional_path(value: Any, field_name: str, base_dir: Path, default: Path) -> Path:
    if value is None:
        return default.resolve()
    if not isinstance(value, str):
        raise ConfigError(f"字段 `{field_name}` 必须是字符串")
    cleaned = value.strip()
    if not cleaned:
        return default.resolve()
    path = Path(cleaned).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def parse_required_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"字段 `{field_name}` 必须是非空字符串")
    return value.strip()


def parse_optional_str(value: Any, field_name: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"字段 `{field_name}` 必须是非空字符串")
    return value.strip()


def parse_nullable_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"字段 `{field_name}` 必须是字符串")
    cleaned = value.strip()
    return cleaned or None


def parse_optional_nullable_str(value: Any, field_name: str, default: str | None) -> str | None:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"字段 `{field_name}` 必须是字符串")
    cleaned = value.strip()
    return cleaned or None


def parse_positive_int(value: Any, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"字段 `{field_name}` 必须是大于 0 的整数")
    return value


def parse_non_negative_int(value: Any, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value < 0:
        raise ConfigError(f"字段 `{field_name}` 必须是大于等于 0 的整数")
    return value


def parse_optional_bool(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"字段 `{field_name}` 必须是布尔值")
    return value


def parse_optional_str_dict(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"字段 `{field_name}` 必须是表结构")

    output: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"`{field_name}` 的 key 必须是字符串")
        if not isinstance(item, str):
            raise ConfigError(f"`{field_name}.{key}` 必须是字符串")
        output[key] = item
    return output


def parse_optional_any_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"字段 `{field_name}` 必须是表结构")

    output: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"`{field_name}` 的 key 必须是字符串")
        output[key] = item
    return output


def parse_scopes(value: Any, api_field_name_prefix: str = "services.gmail.api") -> tuple[str, ...]:
    if value is None:
        return DEFAULT_GMAIL_SCOPES

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list) or not value:
        raise ConfigError(f"字段 `{api_field_name_prefix}.scopes` 必须是字符串数组或字符串")

    scopes: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"`{api_field_name_prefix}.scopes` 中每个元素都必须是非空字符串")
        scopes.append(item)

    return tuple(scopes)


def parse_token_dir(api_table: dict[str, Any], base_dir: Path, api_field_name_prefix: str = "services.gmail.api") -> Path:
    """解析 token 目录，兼容旧字段 token_file。"""

    token_dir_raw = api_table.get("token_dir")
    if token_dir_raw is not None:
        return parse_required_path(
            token_dir_raw,
            field_name=f"{api_field_name_prefix}.token_dir",
            base_dir=base_dir,
        )

    token_file_raw = api_table.get("token_file")
    if token_file_raw is not None:
        token_file = parse_required_path(
            token_file_raw,
            field_name=f"{api_field_name_prefix}.token_file",
            base_dir=base_dir,
        )
        return token_file.parent

    raise ConfigError(f"字段 `{api_field_name_prefix}.token_dir` 必填")


__all__ = [
    "require_table",
    "parse_email",
    "parse_required_path",
    "parse_optional_path",
    "parse_required_str",
    "parse_optional_str",
    "parse_nullable_str",
    "parse_optional_nullable_str",
    "parse_positive_int",
    "parse_non_negative_int",
    "parse_optional_bool",
    "parse_optional_str_dict",
    "parse_optional_any_dict",
    "parse_scopes",
    "parse_token_dir",
]
