from __future__ import annotations


class ConfigError(ValueError):
    """配置文件读取或校验失败。"""


__all__ = ["ConfigError"]
