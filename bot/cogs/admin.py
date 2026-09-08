"""서버별 설정."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..domain.boss_data import canonical_boss_name
from ..models import BossImage, GuildConfig
from .common import EMBED_COLOR, boss_autocomplete, open_session

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
            f"🔔 파티 알림을 {채널.mention} 에 보냅니다. 일정 30분 전과 정시에 한 번씩 알립니다.",
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

    @app_commands.command(name="보스사진", description="알림에 띄울 보스 사진을 등록합니다.")
    @app_commands.describe(보스="보스 이름", 주소="이미지 URL. 비우면 등록된 사진을 지웁니다")
    @app_commands.autocomplete(보스=boss_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_boss_image(
        self, interaction: discord.Interaction, 보스: str, 주소: str | None = None
    ) -> None:
        boss_name = canonical_boss_name(보스)
        if boss_name is None:
            await interaction.response.send_message(
                f"❓ `{보스}` 는 등록된 보스가 아닙니다.", ephemeral=True
            )
            return

        url = (주소 or "").strip()
        if url and not url.startswith(("http://", "https://")):
            await interaction.response.send_message(
                "❓ 이미지 주소는 `http://` 또는 `https://` 로 시작해야 합니다.", ephemeral=True
            )
            return
        if len(url) > 500:
            await interaction.response.send_message(
                "❓ 이미지 주소가 너무 깁니다 (500자 이하).", ephemeral=True
            )
            return

        with open_session(interaction) as session:
            row = session.get(BossImage, (interaction.guild_id, boss_name))
            if not url:
                if row is None:
                    await interaction.response.send_message(
                        f"❓ **{boss_name}** 에 등록된 사진이 없습니다.", ephemeral=True
                    )
                    return
                session.delete(row)
                await interaction.response.send_message(
                    f"🗑️ **{boss_name}** 사진을 지웠습니다.", ephemeral=True
                )
                return

            if row is None:
                session.add(
                    BossImage(guild_id=interaction.guild_id, boss_name=boss_name, image_url=url)
                )
            else:
                row.image_url = url

        embed = discord.Embed(title=f"🖼️ {boss_name} 사진을 등록했습니다", color=EMBED_COLOR)
        embed.set_thumbnail(url=url)
        embed.set_footer(text="사진이 안 보이면 주소가 이미지 파일을 직접 가리키는지 확인하세요.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="보스사진목록", description="등록된 보스 사진을 봅니다.")
    async def list_boss_images(self, interaction: discord.Interaction) -> None:
        with open_session(interaction) as session:
            rows = session.scalars(
                select(BossImage)
                .where(BossImage.guild_id == interaction.guild_id)
                .order_by(BossImage.boss_name)
            ).all()
            등록 = [(row.boss_name, row.image_url) for row in rows]

        if not 등록:
            await interaction.response.send_message(
                "등록된 보스 사진이 없습니다. `/보스사진` 으로 등록하면 알림에 썸네일이 붙습니다.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🖼️ 등록된 보스 사진",
            description="\n".join(f"・**{name}** — {url}" for name, url in 등록)[:4000],
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_notify_channel.error
    @set_boss_image.error
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
