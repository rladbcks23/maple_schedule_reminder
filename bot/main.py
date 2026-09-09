"""봇 엔트리포인트. 코그를 로드하고 슬래시 커맨드를 동기화한다."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands
from sqlalchemy import inspect

from .config import Config, ConfigError, load_config, setup_logging
from .db import build_engine, build_session_factory

log = logging.getLogger("maple")

EXTENSIONS = (
    "bot.cogs.help",
    "bot.cogs.character",
    "bot.cogs.party",
    "bot.cogs.income",
    "bot.cogs.admin",
    "bot.scheduler",
)

REQUIRED_TABLES = (
    "guild_config",
    "character",
    "party_schedule",
    "party_member",
    "notification_log",
)


class MapleBossBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        # 슬래시 커맨드만 쓰므로 특권 인텐트는 필요 없다.
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.config = config
        self.engine = build_engine(config.database_url)
        self.session_factory = build_session_factory(self.engine)

    def check_schema(self) -> None:
        """마이그레이션을 안 돌린 채 켠 경우를 초반에 잡아준다."""
        existing = set(inspect(self.engine).get_table_names())
        missing = [name for name in REQUIRED_TABLES if name not in existing]
        if missing:
            raise ConfigError(
                "DB 테이블이 없습니다: "
                + ", ".join(missing)
                + "\n먼저 `alembic upgrade head` 를 실행해주세요."
            )

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.info("확장 로드: %s", extension)

        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("길드 %s에 슬래시 커맨드 %d개 동기화", self.config.guild_id, len(synced))
        else:
            synced = await self.tree.sync()
            log.info("전역 슬래시 커맨드 %d개 동기화 (반영까지 최대 1시간)", len(synced))

    async def on_ready(self) -> None:
        log.info("로그인 완료: %s (id=%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="보스 파티 일정")
        )

    async def close(self) -> None:
        await super().close()
        self.engine.dispose()


async def run() -> None:
    config = load_config()
    setup_logging(config.log_level)

    bot = MapleBossBot(config)
    bot.check_schema()
    async with bot:
        await bot.start(config.discord_token)


def main() -> None:
    try:
        asyncio.run(run())
    except ConfigError as error:
        raise SystemExit(str(error)) from error
    except KeyboardInterrupt:
        log.info("종료합니다.")


if __name__ == "__main__":
    main()
