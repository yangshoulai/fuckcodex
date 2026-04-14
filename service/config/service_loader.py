from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import DEFAULT_HTTP_IMPERSONATE, DEFAULT_HTTP_USER_AGENT
from .errors import ConfigError
from .models import (
    CpaConfig,
    DuckMailConfig,
    FirefoxRelayConfig,
    FreeMailConfig,
    GmailApiConfig,
    GmailConfig,
    HttpConfig,
    LuckMailConfig, HeroSmsConfig,
)
from .parse_utils import (
    parse_email,
    parse_non_negative_int,
    parse_nullable_str,
    parse_optional_any_dict,
    parse_optional_bool,
    parse_optional_nullable_str,
    parse_optional_str,
    parse_optional_str_dict,
    parse_positive_int,
    parse_required_path,
    parse_required_str,
    parse_scopes,
    parse_token_dir,
    require_table,
)
from .validators import normalize_base_url


def parse_gmail_config_from_gmail_table(
        services_table: dict[str, Any],
        base_dir: Path,
        config_prefix: str = "services",
) -> GmailConfig:
    gmail_table = require_table(services_table, "gmail", full_name=f"{config_prefix}.gmail")
    gmail_api_table = require_table(gmail_table, "api", full_name=f"{config_prefix}.gmail.api")
    raw_email = gmail_table.get("email")
    gmail_email = parse_email(raw_email, field_name=f"{config_prefix}.gmail.email")
    email_length = parse_positive_int(gmail_table.get("email_length"), f"{config_prefix}.gmail.email_length", default=8)
    gmail_api_config = GmailApiConfig(
        credentials_file=parse_required_path(
            gmail_api_table.get("credentials_file"),
            field_name=f"{config_prefix}.gmail.api.credentials_file",
            base_dir=base_dir,
        ),
        token_dir=parse_token_dir(gmail_api_table, base_dir),
        scopes=parse_scopes(gmail_api_table.get("scopes")),
    )

    return GmailConfig(
        email=gmail_email,
        api=gmail_api_config,
        email_length=email_length,
        default_max_results=parse_positive_int(
            gmail_table.get("default_max_results"),
            field_name=f"{config_prefix}.gmail.default_max_results",
            default=20,
        ),
        proxy=parse_optional_nullable_str(
            gmail_table.get("proxy"),
            field_name=f"{config_prefix}.gmail.proxy",
            default=None,
        ),
    )


def parse_gmail_config(services_table: dict[str, Any], base_dir: Path) -> GmailConfig:
    return parse_gmail_config_from_gmail_table(services_table, base_dir, "services")


def parse_luckmail_config(services_table: dict[str, Any]) -> LuckMailConfig | None:
    luckmail_table = services_table.get("luckmail")
    if luckmail_table is None:
        return None
    if not isinstance(luckmail_table, dict):
        raise ConfigError("[services.luckmail] 必须是表结构")

    base_url = normalize_base_url(
        parse_optional_str(
            luckmail_table.get("base_url"),
            field_name="services.luckmail.base_url",
            default="https://mails.luckyous.com",
        ),
        "services.luckmail.base_url",
    )

    return LuckMailConfig(
        base_url=base_url,
        api_key=parse_required_str(
            luckmail_table.get("api_key"),
            field_name="services.luckmail.api_key",
        ),
        project_code=parse_required_str(
            luckmail_table.get("project_code"),
            field_name="services.luckmail.project_code",
        ),
        email_type=parse_required_str(
            luckmail_table.get("email_type"),
            field_name="services.luckmail.email_type",
        ),
        variant_mode=parse_nullable_str(
            luckmail_table.get("variant_mode"),
            field_name="services.luckmail.variant_mode",
        ),
        domain=parse_nullable_str(
            luckmail_table.get("domain"),
            field_name="services.luckmail.domain",
        ),
    )


def parse_herosms_config(services_table: dict[str, Any]) -> HeroSmsConfig | None:
    herosms_table = services_table.get("herosms")
    max_price = parse_optional_nullable_str(
        herosms_table.get("max_price"),
        field_name="services.herosms.max_price",
        default=None,
    )

    max_price = float(max_price) if max_price else None

    return HeroSmsConfig(
        api_key=parse_required_str(
            herosms_table.get("api_key"),
            field_name="services.herosms.api_key",
        ),
        api_url=normalize_base_url(
            parse_required_str(
                herosms_table.get("api_url"),
                field_name="services.herosms.api_url",
            ),
            "services.herosms.api_url",
        ),
        service_id=parse_required_str(
            herosms_table.get("service_id"),
            field_name="services.herosms.service_id",
        ),
        country=parse_non_negative_int(
            herosms_table.get("country"),
            field_name="services.herosms.country",
            default=0,
        ),
        max_price=max_price,
    )


def parse_freemail_config(services_table: dict[str, Any]) -> FreeMailConfig | None:
    freemail_table = services_table.get("freemail")
    if freemail_table is None:
        return None
    if not isinstance(freemail_table, dict):
        raise ConfigError("[services.freemail] 必须是表结构")

    max_probe_emails = parse_positive_int(
        freemail_table.get("max_probe_emails"),
        field_name="services.freemail.max_probe_emails",
        default=10,
    )
    if max_probe_emails > 50:
        raise ConfigError("字段 `services.freemail.max_probe_emails` 不能大于 50")

    return FreeMailConfig(
        base_url=normalize_base_url(
            parse_required_str(
                freemail_table.get("base_url"),
                field_name="services.freemail.base_url",
            ),
            "services.freemail.base_url",
        ),
        admin_token=parse_required_str(
            freemail_table.get("admin_token"),
            field_name="services.freemail.admin_token",
        ),
        domain_index=parse_non_negative_int(
            freemail_table.get("domain_index"),
            field_name="services.freemail.domain_index",
            default=0,
        ),
        max_probe_emails=max_probe_emails,
        email_length=parse_positive_int(
            freemail_table.get("email_length"),
            field_name="services.freemail.email_length",
            default=8,
        ),
    )


def parse_duckmail_config(services_table: dict[str, Any]) -> DuckMailConfig | None:
    duckmail_table = require_table(services_table, "duckmail", "services.duckmail")
    return DuckMailConfig(
        base_url=normalize_base_url(
            parse_required_str(
                duckmail_table.get("base_url"),
                field_name="services.duckmail.base_url",
            ),
            "services.duckmail.base_url",
        ),
        authorization_token=parse_required_str(
            duckmail_table.get("authorization_token"),
            field_name="services.duckmail.authorization_token",
        ),
        forward_gmail=parse_required_str(
            duckmail_table.get("forward_gmail"),
            field_name="services.duckmail.forward_gmail",
        ),
    )


def parse_firefoxrelay_config(services_table: dict[str, Any]) -> FirefoxRelayConfig | None:
    firefoxrelay_table = require_table(services_table, "firefoxrelay", "services.firefoxrelay")
    return FirefoxRelayConfig(
        base_url=normalize_base_url(
            parse_required_str(
                firefoxrelay_table.get("base_url"),
                field_name="services.firefoxrelay.base_url",
            ),
            "services.firefoxrelay.base_url",
        ),
        session_id=parse_required_str(
            firefoxrelay_table.get("session_id"),
            field_name="services.firefoxrelay.session_id",
        ),
        csrf_token=parse_required_str(
            firefoxrelay_table.get("csrf_token"),
            field_name="services.firefoxrelay.csrf_token",
        ),
        forward_gmail=parse_required_str(
            firefoxrelay_table.get("forward_gmail"),
            field_name="services.firefoxrelay.forward_gmail",
        ),
    )


def parse_http_config(services_table: dict[str, Any]) -> HttpConfig:
    http_table = services_table.get("http")
    if http_table is None:
        return HttpConfig()
    if not isinstance(http_table, dict):
        raise ConfigError("[services.http] 必须是表结构")

    return HttpConfig(
        timeout_seconds=parse_positive_int(
            http_table.get("timeout_seconds"),
            field_name="services.http.timeout_seconds",
            default=60,
        ),
        verify_ssl=parse_optional_bool(
            http_table.get("verify_ssl"),
            field_name="services.http.verify_ssl",
            default=True,
        ),
        user_agent=parse_optional_str(
            http_table.get("user_agent"),
            field_name="services.http.user_agent",
            default=DEFAULT_HTTP_USER_AGENT,
        ),
        proxy=parse_optional_nullable_str(
            http_table.get("proxy"),
            field_name="services.http.proxy",
            default=None,
        ),
        http_proxy=parse_optional_nullable_str(
            http_table.get("http_proxy"),
            field_name="services.http.http_proxy",
            default=None,
        ),
        https_proxy=parse_optional_nullable_str(
            http_table.get("https_proxy"),
            field_name="services.http.https_proxy",
            default=None,
        ),
        proxy_username=parse_optional_nullable_str(
            http_table.get("proxy_username"),
            field_name="services.http.proxy_username",
            default=None,
        ),
        proxy_password=parse_optional_nullable_str(
            http_table.get("proxy_password"),
            field_name="services.http.proxy_password",
            default=None,
        ),
        impersonate=parse_optional_nullable_str(
            http_table.get("impersonate"),
            field_name="services.http.impersonate",
            default=DEFAULT_HTTP_IMPERSONATE,
        ),
        ja3=parse_optional_nullable_str(
            http_table.get("ja3"),
            field_name="services.http.ja3",
            default=None,
        ),
        akamai=parse_optional_nullable_str(
            http_table.get("akamai"),
            field_name="services.http.akamai",
            default=None,
        ),
        extra_fp=parse_optional_any_dict(
            http_table.get("extra_fp"),
            field_name="services.http.extra_fp",
        ),
        default_headers=parse_optional_str_dict(
            http_table.get("default_headers"),
            field_name="services.http.default_headers",
        ),
    )


def parse_cpa_config(services_table: dict[str, Any]) -> CpaConfig | None:
    cpa_table = services_table.get("cpa")
    if cpa_table is None:
        return None
    if not isinstance(cpa_table, dict):
        raise ConfigError("[services.cpa] 必须是表结构")

    return CpaConfig(
        base_url=normalize_base_url(
            parse_required_str(cpa_table.get("base_url", ""), "services.cpa.base_url"),
            "services.cpa.base_url",
        ),
        management_password=parse_required_str(
            cpa_table.get("management_password", ""),
            field_name="services.cpa.management_password",
        ),
    )


__all__ = [
    "parse_gmail_config_from_gmail_table",
    "parse_gmail_config",
    "parse_luckmail_config",
    "parse_freemail_config",
    "parse_duckmail_config",
    "parse_firefoxrelay_config",
    "parse_http_config",
    "parse_cpa_config",
]
