"""Configuration loading.

Settings are loaded in priority order (highest first):
  1. Environment variables  (PROCONTEXT__SERVER__TRANSPORT=http)
  2. procontext.yaml        (searched in cwd, then platform config dir)
  3. Hardcoded defaults

The config file is optional — all fields have sensible defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_DEFAULT_DATA_DIR = platformdirs.user_data_dir("procontext")
_DEFAULT_DB_PATH = str(Path(_DEFAULT_DATA_DIR) / "cache.db")


def _find_config_file() -> str | None:
    """Return the path of the first procontext.yaml found, or None."""
    candidates = [
        Path("procontext.yaml"),
        Path(platformdirs.user_config_dir("procontext")) / "procontext.yaml",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


class ServerSettings(BaseModel):
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8080
    auth_enabled: bool = False
    auth_key: str = ""


class RegistrySettings(BaseModel):
    url: str = "https://procontext.github.io/known-libraries.json"
    metadata_url: str = "https://procontext.github.io/registry_metadata.json"
    poll_interval_hours: int = 24


class CacheSettings(BaseModel):
    ttl_hours: int = 24
    db_path: str = _DEFAULT_DB_PATH
    cleanup_interval_hours: int = 6


class FetcherSettings(BaseModel):
    ssrf_private_ip_check: bool = True
    ssrf_domain_check: bool = True
    allowlist_depth: Literal[0, 1, 2] = 0
    extra_allowed_domains: list[str] = ["github.com", "githubusercontent.com"]
    request_timeout_seconds: float = 30.0


class ResolverSettings(BaseModel):
    fuzzy_score_cutoff: int = 70
    fuzzy_max_results: int = 5


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "text"] = "json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Double-underscore separates nesting: PROCONTEXT__SERVER__PORT=9090
        env_prefix="PROCONTEXT__",
        env_nested_delimiter="__",
        yaml_file=_find_config_file(),
        yaml_file_encoding="utf-8",
    )

    data_dir: str = _DEFAULT_DATA_DIR
    server: ServerSettings = ServerSettings()
    registry: RegistrySettings = RegistrySettings()
    cache: CacheSettings = CacheSettings()
    fetcher: FetcherSettings = FetcherSettings()
    resolver: ResolverSettings = ResolverSettings()
    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
        **kwargs: Any,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,  # Constructor args (highest priority)
            env_settings,  # Environment variables
            YamlConfigSettingsSource(settings_cls),  # YAML file
            # dotenv and file secrets intentionally excluded
        )
