from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .models import AppConfig
from .parse_utils import require_table
from .register_loader import (
    parse_grok_register_config,
    parse_openai_register_config,
    parse_qwen_register_config,
)
from .service_loader import (
    parse_cpa_config,
    parse_duckmail_config,
    parse_firefoxrelay_config,
    parse_freemail_config,
    parse_gmail_config,
    parse_http_config,
    parse_luckmail_config,
)
from .errors import ConfigError


class ConfigService:
    """负责从 config.toml 加载应用配置。"""

    @classmethod
    def load(cls, config_file: str | Path = "config.toml") -> AppConfig:
        """加载并返回应用配置对象。"""

        path = Path(config_file).expanduser()
        if not path.is_absolute():
            path = path.resolve()

        if not path.exists():
            raise ConfigError(f"配置文件不存在: {path}")

        with path.open("rb") as file:
            data = tomllib.load(file)

        return cls._parse(data=data, base_dir=path.parent)

    @classmethod
    def _parse(cls, data: dict[str, Any], base_dir: Path) -> AppConfig:
        services_table = require_table(data, "services")
        registers_table = require_table(data, "registers")

        http_config = parse_http_config(services_table)
        cpa_config = parse_cpa_config(services_table)

        openai_register_config = parse_openai_register_config(registers_table, base_dir=base_dir)
        grok_register_config = parse_grok_register_config(registers_table, base_dir=base_dir)
        qwen_register_config = parse_qwen_register_config(registers_table, base_dir=base_dir)

        selected_providers = {
            openai_register_config.mail_provider,
            grok_register_config.mail_provider,
            qwen_register_config.mail_provider,
        }

        gmail_config = None
        luckmail_config = None
        freemail_config = None
        duckmail_config = None
        firefoxrelay_config = None

        if "freemail" in selected_providers:
            freemail_config = parse_freemail_config(services_table)
        if "luckmail" in selected_providers:
            luckmail_config = parse_luckmail_config(services_table)
        if "duckmail" in selected_providers:
            duckmail_config = parse_duckmail_config(services_table)
            gmail_config = parse_gmail_config(services_table, base_dir=base_dir)
        if "gmail" in selected_providers:
            gmail_config = parse_gmail_config(services_table, base_dir=base_dir)
        if "firefoxrelay" in selected_providers:
            firefoxrelay_config = parse_firefoxrelay_config(services_table)
            gmail_config = parse_gmail_config(services_table, base_dir=base_dir)

        return AppConfig(
            gmail=gmail_config,
            luckmail=luckmail_config,
            freemail=freemail_config,
            duckmail=duckmail_config,
            firefoxrelay=firefoxrelay_config,
            http=http_config,
            cpa=cpa_config,
            openai_register=openai_register_config,
            grok_register=grok_register_config,
            qwen_register=qwen_register_config,
        )


__all__ = ["ConfigService"]
