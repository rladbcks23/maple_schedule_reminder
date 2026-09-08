"""서버별 설정."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..models import GuildConfig
from .common import EMBED_COLOR, open_session

log = logging.getLogger("maple.admin")


@app_commands.guild_only()
class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="알림채널", description="파티 알림을 보낼 채널을 지정합니다.")
    @app_commands.describe(채널="알림을 보낼 텍스트 채널")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_notify_channel(
        self, interaction: discord.Interaction, 채널: discord.TextChannel
    ) -> None:
        with open_session(interaction) as session:
            config = session.get(GuildConfig, interaction.guild_id)
            if config is None:
                config = GuildConfig(guild_id=interaction.guild_id)
                session.add(config)
            config.notify_channel_id = 채널.id

        await interaction.response.send_message(
            f"🔔 파티 알림을 {채널.mention} 에 보냅니다. "
            "일정 30분 전과 정시에 한 번씩 알립니다.",
            ephemeral=True,
        )

    @app_commands.command(name="알림설정확인", description="현재 알림 채널 설정을 봅니다.")
    async def show_notify_channel(self, interaction: discord.Interaction) -> None:
        with open_session(interaction) as session:
            config = session.get(GuildConfig, interaction.guild_id)
            channel_id = config.notify_channel_id if config else None

        embed = discord.Embed(title="⚙️ 알림 설정", color=EMBED_COLOR)
        embed.add_field(
            name="알림 채널",
            value=f"<#{channel_id}>" if channel_id else "설정 안 됨 (`/알림채널` 로 지정)",
            inline=False,
        )
        embed.add_field(name="알림 시점", value="일정 30분 전 · 일정 정시", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_notify_channel.error
    async def on_permission_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "⛔ 서버 관리 권한이 있어야 사용할 수 있습니다.", ephemeral=True
            )
            return
        raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
