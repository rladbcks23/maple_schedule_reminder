"""결정석 수익 정산과 클리어 기록."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..domain.boss_data import default_boss_image, is_monthly_boss
from ..domain.formatting import difficulty_tag, format_meso, format_sol_erda
from ..domain.income import ClearInput, calculate_income, party_income
from ..domain.schedule import (
    REPEAT_MONTHLY,
    REPEAT_WEEKLY,
    month_period_key,
    now_kst,
    now_utc,
    week_period_key,
)
from ..models import ClearRecord
from .common import (
    EMBED_COLOR,
    boss_autocomplete,
    difficulty_autocomplete,
    my_character_autocomplete,
    open_session,
    party_infos,
    resolve_schedule,
    resolve_target_characters,
    schedule_autocomplete,
    schedule_tag,
    validate_boss_and_difficulty,
)

log = logging.getLogger("maple.income")

FOOTER = "부가 수익을 제외한 결정석값입니다."


def current_period_keys() -> tuple[str, str]:
    """지금 주기의 주차 키와 월 키.

    주간 보스는 주차 키로, 월간 보스(검은 마법사)는 월 키로 기록되므로
    한 번의 정산에서 두 키를 함께 본다.
    """
    moment = now_kst()
    return week_period_key(moment), month_period_key(moment)


def period_key_for_boss(boss_name: str) -> str:
    moment = now_kst()
    repeat_type = REPEAT_MONTHLY if is_monthly_boss(boss_name) else REPEAT_WEEKLY
    return month_period_key(moment) if repeat_type == REPEAT_MONTHLY else week_period_key(moment)


@app_commands.guild_only()
class Income(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="수익", description="이번 주기에 번 결정석 수익을 정산합니다.")
    @app_commands.describe(캐릭터="비우면 대표 캐릭터, 대표가 없으면 내 전 캐릭터")
    @app_commands.autocomplete(캐릭터=my_character_autocomplete)
    async def income(self, interaction: discord.Interaction, 캐릭터: str | None = None) -> None:
        week_key, month_key = current_period_keys()

        with open_session(interaction) as session:
            targets, error = resolve_target_characters(
                session, interaction.guild_id, interaction.user.id, 캐릭터
            )
            if error:
                await interaction.response.send_message(f"❓ {error}", ephemeral=True)
                return

            target_ids = [character.id for character in targets]
            records = session.scalars(
                select(ClearRecord)
                .where(
                    ClearRecord.guild_id == interaction.guild_id,
                    ClearRecord.character_id.in_(target_ids),
                    ClearRecord.period_key.in_([week_key, month_key]),
                )
                .order_by(ClearRecord.cleared_at)
            ).all()

            clears = [
                ClearInput(
                    boss_name=record.boss_name,
                    difficulty=record.difficulty,
                    character_id=record.character_id,
                )
                for record in records
            ]
            report = calculate_income(clears, party_infos(session, interaction.guild_id))
            target_names = ", ".join(character.display_name for character in targets)

        embed = discord.Embed(
            title=f"💰 {target_names} · 결정석 정산",
            description=f"주간 `{week_key}` · 월간 `{month_key}`",
            color=EMBED_COLOR,
        )

        if not report.lines:
            embed.add_field(
                name="기록 없음",
                value="아직 클리어 기록이 없습니다. `/클리어` 로 남겨주세요.",
                inline=False,
            )
        else:
            상세 = "\n".join(line.render() for line in report.lines)
            embed.add_field(name=f"상세 ({len(report.lines)}건)", value=상세[:1024], inline=False)
            embed.add_field(name="합계 메소", value=format_meso(report.total_meso), inline=True)
            embed.add_field(
                name="솔 에르다 기운", value=format_sol_erda(report.total_sol_erda), inline=True
            )
            if report.missing_lines:
                embed.add_field(
                    name="합계에서 제외됨",
                    value=f"{len(report.missing_lines)}건은 시세 정보가 없어 합계에 넣지 않았습니다.",
                    inline=False,
                )

        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="클리어", description="이번 주기 보스 클리어를 기록합니다.")
    @app_commands.describe(보스="보스 이름", 난이도="난이도", 캐릭터="비우면 대표 캐릭터")
    @app_commands.autocomplete(
        보스=boss_autocomplete, 난이도=difficulty_autocomplete, 캐릭터=my_character_autocomplete
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        보스: str,
        난이도: str,
        캐릭터: str | None = None,
    ) -> None:
        validated = validate_boss_and_difficulty(보스, 난이도)
        if isinstance(validated, str):
            await interaction.response.send_message(f"❓ {validated}", ephemeral=True)
            return
        boss_name, difficulty = validated
        key = period_key_for_boss(boss_name)

        with open_session(interaction) as session:
            targets, error = resolve_target_characters(
                session, interaction.guild_id, interaction.user.id, 캐릭터
            )
            if error:
                await interaction.response.send_message(f"❓ {error}", ephemeral=True)
                return

            character = targets[0]
            existing = session.scalars(
                select(ClearRecord).where(
                    ClearRecord.character_id == character.id,
                    ClearRecord.boss_name == boss_name,
                    ClearRecord.difficulty == difficulty,
                    ClearRecord.period_key == key,
                )
            ).first()

            if existing is not None:
                await interaction.response.send_message(
                    f"ℹ️ **{character.display_name}** 의 `{key}` 주기 "
                    f"**{difficulty_tag(difficulty)} {boss_name}** 은 이미 기록돼 있습니다.",
                    ephemeral=True,
                )
                return

            session.add(
                ClearRecord(
                    guild_id=interaction.guild_id,
                    schedule_id=None,
                    character_id=character.id,
                    boss_name=boss_name,
                    difficulty=difficulty,
                    cleared_at=now_utc(),
                    period_key=key,
                )
            )
            name = character.display_name

        await interaction.response.send_message(
            f"✅ **{name}** · {difficulty_tag(difficulty)} {boss_name} 클리어를 기록했습니다. (`{key}`)"
        )

    @app_commands.command(name="클리어취소", description="이번 주기 클리어 기록을 지웁니다.")
    @app_commands.describe(보스="보스 이름", 난이도="난이도", 캐릭터="비우면 대표 캐릭터")
    @app_commands.autocomplete(
        보스=boss_autocomplete, 난이도=difficulty_autocomplete, 캐릭터=my_character_autocomplete
    )
    async def unclear(
        self,
        interaction: discord.Interaction,
        보스: str,
        난이도: str,
        캐릭터: str | None = None,
    ) -> None:
        validated = validate_boss_and_difficulty(보스, 난이도)
        if isinstance(validated, str):
            await interaction.response.send_message(f"❓ {validated}", ephemeral=True)
            return
        boss_name, difficulty = validated
        key = period_key_for_boss(boss_name)

        with open_session(interaction) as session:
            targets, error = resolve_target_characters(
                session, interaction.guild_id, interaction.user.id, 캐릭터
            )
            if error:
                await interaction.response.send_message(f"❓ {error}", ephemeral=True)
                return

            character = targets[0]
            record = session.scalars(
                select(ClearRecord).where(
                    ClearRecord.character_id == character.id,
                    ClearRecord.boss_name == boss_name,
                    ClearRecord.difficulty == difficulty,
                    ClearRecord.period_key == key,
                )
            ).first()

            if record is None:
                await interaction.response.send_message(
                    f"❓ **{character.display_name}** 의 `{key}` 주기에 "
                    f"**{difficulty_tag(difficulty)} {boss_name}** 기록이 없습니다.",
                    ephemeral=True,
                )
                return

            session.delete(record)
            name = character.display_name

        await interaction.response.send_message(
            f"🗑️ **{name}** · {difficulty_tag(difficulty)} {boss_name} 기록을 지웠습니다."
        )

    @app_commands.command(name="결정석", description="보스 결정석 시세와 인원별 분배액을 봅니다.")
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
        name="파티수익", description="파티 일정의 총 결정석값과 1인 분배액을 봅니다."
    )
    @app_commands.describe(일정="확인할 파티 (코드 또는 자동완성)")
    @app_commands.autocomplete(일정=schedule_autocomplete)
    async def party_income_command(self, interaction: discord.Interaction, 일정: str) -> None:
        with open_session(interaction) as session:
            schedule = resolve_schedule(session, interaction.guild_id, 일정)
            if schedule is None:
                await interaction.response.send_message(
                    f"❓ `{일정}` 코드의 파티가 없습니다. `/파티목록` 에서 확인해주세요.",
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
