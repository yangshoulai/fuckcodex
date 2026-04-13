from __future__ import annotations

DEFAULT_GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)
DEFAULT_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)
DEFAULT_HTTP_IMPERSONATE = "chrome136"
DEFAULT_OPENAI_REGISTER_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_QWEN_REGISTER_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"

__all__ = [
    "DEFAULT_GMAIL_SCOPES",
    "DEFAULT_HTTP_USER_AGENT",
    "DEFAULT_HTTP_IMPERSONATE",
    "DEFAULT_OPENAI_REGISTER_CLIENT_ID",
    "DEFAULT_QWEN_REGISTER_CLIENT_ID",
]
