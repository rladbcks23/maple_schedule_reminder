"""커맨드 목록 안내.

목록을 손으로 적어두면 커맨드를 늘릴 때마다 어긋나므로, 실제로 등록된
커맨드 트리를 읽어 코그별로 묶어 보여준다.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .common import EMBED_COLOR

log = logging.getLogger("maple.help")

# 코그 클래스명 -> (제목, 한 줄 설명). 여기 없는 코그는 '기타'로 묶인다.
CATEGORIES: dict[str, tuple[str, str]] = {
    "Characters": ("🧙 캐릭터", "캐릭터를 등록해야 파티에 넣고 알림에서 멘션됩니다."),
    "Party": ("🗓️ 파티 일정", "고정 파티는 매주 반복하고, 고정이 아닌 파티는 알림이 나가면 사라집니다."),
    "Income": ("💰 수익 · 결정석", "주간 리셋은 목요일 00:00(KST) 기준입니다."),
    "Admin": ("⚙️ 관리", "알림을 받으려면 채널부터 지정해야 합니다."),
    "Help": ("❓ 도움말", ""),
}

FALLBACK_CATEGORY = ("📌 기타", "")


def signature(command: app_commands.Command) -> str:
    """'/파티등록 보스 난이도 시각 [고정]' 형태. 대괄호는 선택 옵션."""
    parts = [
        parameter.name if parameter.required else f"[{parameter.name}]"
        for parameter in command.parameters
    ]
    return " ".join([f"/{command.name}", *parts])


def needs_manage_guild(command: app_commands.Command) -> bool:
    """has_permissions 체크가 걸린 커맨드인지. 배지 표시용이라 틀려도 치명적이지 않다."""
    return any("has_permissions" in getattr(check, "__qualname__", "") for check in command.checks)


@app_commands.guild_only()
class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="명령어", description="쓸 수 있는 커맨드를 전부 보여줍니다. 공개를 켜면 채널에 올립니다.")
    @app_commands.describe(공개="채널에 모두가 보이게 올립니다 (기본: 나만 보기)")
    async def help_command(self, interaction: discord.Interaction, 공개: bool = False) -> None:
        grouped: dict[str, list[app_commands.Command]] = {}
        for command in self.bot.tree.get_commands():
            if not isinstance(command, app_commands.Command):
                continue
            key = command.binding.__class__.__name__ if command.binding else ""
            grouped.setdefault(key, []).append(command)

        embed = discord.Embed(
            title="📖 메이플 보스 파티 봇 커맨드",
            description="대괄호 `[ ]` 는 생략할 수 있는 옵션입니다.",
            color=EMBED_COLOR,
        )

        # CATEGORIES에 적어둔 순서를 먼저, 나머지는 뒤에 붙인다.
        keys = [key for key in CATEGORIES if key in grouped]
        keys += [key for key in grouped if key not in CATEGORIES]

        total = 0
        for key in keys:
            title, note = CATEGORIES.get(key, FALLBACK_CATEGORY)
            lines = []
            for command in grouped[key]:
                배지 = " `관리자`" if needs_manage_guild(command) else ""
                lines.append(f"**`{signature(command)}`**{배지}\n　{command.description}")
                total += 1
            if note:
                lines.append(f"_{note}_")
            embed.add_field(name=title, value="\n".join(lines)[:1024], inline=False)

        embed.set_footer(text=f"커맨드 {total}개 · 모든 시각은 한국 시간(KST) 기준")
        await interaction.response.send_message(embed=embed, ephemeral=not 공개)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
