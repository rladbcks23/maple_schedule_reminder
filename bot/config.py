"""환경변수 로딩과 검증."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_DATABASE_URL = "sqlite:///maple_boss_bot.db"
DEFAULT_LOG_LEVEL = "INFO"
VALID_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")


class ConfigError(RuntimeError):
    """환경변수가 비었거나 값이 잘못된 경우."""


@dataclass(frozen=True)
class Config:
    discord_token: str
    database_url: str
    log_level: str
    guild_id: int | None


def load_config(*, dotenv: bool = True) -> Config:
    """.env를 읽어 설정을 만든다. 필수 값이 없으면 ConfigError."""
    if dotenv:
        load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "DISCORD_TOKEN이 비어 있습니다. .env.example을 .env로 복사해 채워주세요."
        )

    log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper() or DEFAULT_LOG_LEVEL
    if log_level not in VALID_LOG_LEVELS:
        raise ConfigError(
            f"LOG_LEVEL 값이 잘못됐습니다: {log_level} (가능한 값: {', '.join(VALID_LOG_LEVELS)})"
        )

    raw_guild_id = os.getenv("GUILD_ID", "").strip()
    if raw_guild_id and not raw_guild_id.isdigit():
        raise ConfigError(f"GUILD_ID는 숫자여야 합니다: {raw_guild_id}")

    return Config(
        discord_token=token,
        database_url=os.getenv("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL,
        log_level=log_level,
        guild_id=int(raw_guild_id) if raw_guild_id else None,
    )


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
