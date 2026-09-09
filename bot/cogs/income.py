"""결정석 수익 계산.

이 봇은 클리어 여부를 추적하지 않는다. 수익은 그때그때 적어준 보스 목록으로
계산만 한다.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..domain.boss_data import default_boss_image, is_monthly_boss
from ..domain.bosslist import parse_boss_list
from ..domain.formatting import difficulty_tag, format_meso, format_sol_erda
from ..domain.income import party_income
from .common import (
    EMBED_COLOR,
    boss_autocomplete,
    difficulty_autocomplete,
    open_session,
    resolve_schedule,
    schedule_autocomplete,
    schedule_tag,
    validate_boss_and_difficulty,
)

log = logging.getLogger("maple.income")

FOOTER = "부가 수익을 제외한 결정석값입니다."
MAX_LINES = 25


@app_commands.guild_only()
class Income(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="수익",
        description="보스 목록의 결정석 수익을 합산합니다. 예: 노말 스우 3, 하드 카링 4",
    )
    @app_commands.describe(보스목록="`난이도 보스 인원` 을 콤마로 구분. 인원을 빼면 1인입니다")
    async def income(self, interaction: discord.Interaction, 보스목록: str) -> None:
        entries, errors = parse_boss_list(보스목록)

        if not entries:
            안내 = "\n".join(f"· {message}" for message in errors[:10]) or (
                "· 보스를 한 개 이상 적어주세요."
            )
            await interaction.response.send_message(
                f"❓ 읽을 수 있는 보스가 없습니다.\n{안내}\n\n예: `노말 스우 3, 하드 카링 4`",
                ephemeral=True,
            )
            return

        줄 = []
        총메소 = 0
        총기운 = 0
        시세없음 = []

        for entry in entries[:MAX_LINES]:
            result = party_income(entry.boss_name, entry.difficulty, entry.party_size)
            머리 = f"{difficulty_tag(entry.difficulty)} {entry.boss_name}"
            if result is None:
                시세없음.append(머리)
                줄.append(f"{머리}: 시세 정보 없음")
                continue

            총메소 += result.share_meso
            총기운 += result.share_sol_erda
            꼬리 = f" · {format_sol_erda(result.share_sol_erda)}" if result.share_sol_erda else ""
            줄.append(
                f"{머리}: {format_meso(result.share_meso)} / {result.member_count}인 분배{꼬리}"
            )

        embed = discord.Embed(title="💰 결정석 수익", color=EMBED_COLOR)
        embed.add_field(name=f"상세 ({len(줄)}건)", value="\n".join(줄)[:1024], inline=False)
        embed.add_field(name="합계 메소", value=format_meso(총메소), inline=True)
        embed.add_field(name="솔 에르다 기운", value=format_sol_erda(총기운), inline=True)

        if 시세없음:
            embed.add_field(
                name="합계에서 제외됨",
                value=f"{', '.join(시세없음)} — 시세 정보가 없습니다.",
                inline=False,
            )
        if errors:
            embed.add_field(
                name="읽지 못한 항목",
                value="\n".join(f"· {message}" for message in errors[:5])[:1024],
                inline=False,
            )

        더보기 = f" 앞의 {MAX_LINES}건만 계산했습니다." if len(entries) > MAX_LINES else ""
        embed.set_footer(text=FOOTER + 더보기)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="결정석",
        description="보스 결정석 시세를 봅니다. 인원을 비우면 1인 기준으로 계산합니다.",
    )
    @app_commands.describe(보스="보스 이름", 난이도="난이도", 인원="나눌 인원 수 (1~6, 기본 1)")
    @app_commands.autocomplete(보스=boss_autocomplete, 난이도=difficulty_autocomplete)
    async def crystal(
        self,
        interaction: discord.Interaction,
        보스: str,
        난이도: str,
        인원: app_commands.Range[int, 1, 6] = 1,
    ) -> None:
        validated = validate_boss_and_difficulty(보스, 난이도)
        if isinstance(validated, str):
            await interaction.response.send_message(f"❓ {validated}", ephemeral=True)
            return
        boss_name, difficulty = validated

        result = party_income(boss_name, difficulty, 인원)
        if result is None:
            await interaction.response.send_message(
                f"❓ **{difficulty_tag(difficulty)} {boss_name}** 은 시세 정보가 없습니다.",
                ephemeral=True,
            )
            return

        image_url = default_boss_image(boss_name)
        embed = discord.Embed(
            title=f"💎 {difficulty_tag(difficulty)} {boss_name}",
            description="월간 보스" if is_monthly_boss(boss_name) else "주간 보스",
            color=EMBED_COLOR,
        )
        if image_url:
            embed.set_thumbnail(url=image_url)

        embed.add_field(name="결정석 (총액)", value=format_meso(result.total_meso), inline=True)
        embed.add_field(
            name=f"{result.member_count}인 분배", value=format_meso(result.share_meso), inline=True
        )
        if result.total_sol_erda > 0:
            embed.add_field(
                name="솔 에르다 기운",
                value=f"총 {format_sol_erda(result.total_sol_erda)}"
                f" · 1인 {format_sol_erda(result.share_sol_erda)}",
                inline=False,
            )
        if result.member_count != 인원:
            embed.add_field(
                name="참고", value="시즌 보스는 항상 1인 분배로 계산합니다.", inline=False
            )

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="파티수익",
        description="파티의 총 결정석값과 1인 분배액을 봅니다. 파티코드는 /파티목록 에서 확인하세요.",
    )
    @app_commands.describe(파티코드="확인할 파티의 코드 (예: SU4K)")
    @app_commands.autocomplete(파티코드=schedule_autocomplete)
    async def party_income_command(self, interaction: discord.Interaction, 파티코드: str) -> None:
        with open_session(interaction) as session:
            schedule = resolve_schedule(session, interaction.guild_id, 파티코드)
            if schedule is None:
                await interaction.response.send_message(
                    f"❓ `{파티코드}` 코드의 파티가 없습니다. `/파티목록` 에서 확인해주세요.",
                    ephemeral=True,
                )
                return

            label = schedule_tag(schedule)
            member_names = [member.character.display_name for member in schedule.members]
            result = party_income(schedule.boss_name, schedule.difficulty, len(schedule.members))

        if result is None:
            await interaction.response.send_message(
                f"❓ **{label}** 은 시세 정보가 없어 계산할 수 없습니다.", ephemeral=True
            )
            return

        embed = discord.Embed(title=f"💎 {label}", color=EMBED_COLOR)
        embed.add_field(name="총 결정석", value=format_meso(result.total_meso), inline=True)
        embed.add_field(
            name=f"1인 분배 ({result.member_count}인)",
            value=format_meso(result.share_meso),
            inline=True,
        )
        if result.total_sol_erda > 0:
            embed.add_field(
                name="솔 에르다 기운",
                value=f"총 {format_sol_erda(result.total_sol_erda)}"
                f" · 1인 {format_sol_erda(result.share_sol_erda)}",
                inline=False,
            )
        embed.add_field(
            name=f"파티원 ({len(member_names)}명)",
            value=", ".join(member_names) or "(없음)",
            inline=False,
        )
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Income(bot))
