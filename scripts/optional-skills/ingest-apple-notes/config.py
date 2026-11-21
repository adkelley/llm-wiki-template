from __future__ import annotations

from pathlib import Path

import tomllib
from errors import ConfigError
from models import NotesConfig


def require_int(data: dict, key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    if value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def require_str(data: dict, key: str) -> str:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def require_list_str(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, list):
        raise ConfigError(f"{key} must be a list")
    if not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return value


def optional_path_str(data: dict, key: str) -> str | None:
    value = require_str(data, key)
    return value or None


def load_config(skill_dir: Path) -> NotesConfig:
    config_path = skill_dir / "config.toml"
    if not config_path.exists():
        raise ConfigError(f"Missing config file: {config_path}")

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    return NotesConfig(
        lookback_days=require_int(data, "lookback_days"),
        raw_output_dir=require_str(data, "raw_output_dir"),
        accounts=require_list_str(data, "accounts"),
        folders=require_list_str(data, "folders"),
        include_tags=require_list_str(data, "include_tags"),
        exclude_tags=require_list_str(data, "exclude_tags"),
        max_notes=require_int(data, "max_notes"),
        database_path=optional_path_str(data, "database_path"),
        wiki=require_str(data, "wiki") if "wiki" in data else None,
    )
