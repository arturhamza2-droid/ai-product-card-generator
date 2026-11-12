"""Настройки из переменных окружения / файла .env (ключ в коде не хранится)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """Не заданы обязательные настройки."""


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    timeout: float = 90.0


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    values = {
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "").strip(),
        "LLM_API_KEY": os.getenv("LLM_API_KEY", "").strip(),
        "LLM_MODEL": os.getenv("LLM_MODEL", "").strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(
            "Не заданы настройки: " + ", ".join(missing) + ". "
            "Скопируйте .env.example в .env и заполните значения (см. README)."
        )
    return Settings(
        base_url=values["LLM_BASE_URL"],
        api_key=values["LLM_API_KEY"],
        model=values["LLM_MODEL"],
    )
