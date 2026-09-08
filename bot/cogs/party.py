"""파티 일정 등록/조회/수정/삭제와 캐릭터 등록."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..domain.boss_data import is_monthly_boss
from ..domain.formatting import format_meso, format_sol_erda
from ..domain.income import party_income
from ..domain.schedule import (
    REPEAT_MONTHLY,
    REPEAT_WEEKLY,
    WEEKDAY_NAMES,
    discord_timestamp,
    format_schedule_time,
    now_kst,
)
from ..models import PartyMember, PartySchedule
from .common import (
    EMBED_COLOR,
    active_schedules,
    boss_autocomplete,
    characters_of_user,
    difficulty_autocomplete,
    find_character,
    get_or_create_character,
    get_schedule,
    next_run,
    open_session,
    parse_clock,
    parse_member_names,
    schedule_autocomplete,
    schedule_label,
    validate_boss_and_difficulty,
)

log = logging.getLogger("maple.party")

WEEKDAY_CHOICES = [
    app_commands.Choice(name=f"{name}요일", value=index + 1)
    for index, name in enumerate(WEEKDAY_NAMES)
]


def summarize_members(schedule: PartySchedule) -> str:
    if not schedule.members:
        return "(없음)"
    return ", ".join(member.character.display_name for member in schedule.members)


def share_text(schedule: PartySchedule) -> str:
    """일정 한 건의 예상 1인 분배 수익."""
    result = party_income(schedule.boss_name, schedule.difficulty, len(schedule.members))
    if result is None:
        return "시세 정보 없음"

    line = f"{format_meso(result.share_meso)} / {result.member_count}인"
    if result.share_sol_erda > 0:
        line += f" · {format_sol_erda(result.share_sol_erda)}"
    return line


def schedule_embed(schedule: PartySchedule, title: str) -> discord.Embed:
    when = format_schedule_time(
        schedule.repeat_type,
        schedule.weekday,
        schedule.month_day,
        schedule.hour,
        schedule.minute,
    )
    upcoming = next_run(schedule)

    embed = discord.Embed(
        title=title,
        description=f"**{schedule.difficulty.upper()} {schedule.boss_name}**",
        color=EMBED_COLOR,
    )
    embed.add_field(name="일정", value=f"{when} · {discord_timestamp(upcoming)}", inline=False)
    embed.add_field(
        name=f"파티원 ({len(schedule.members)}명)", value=summarize_members(schedule), inline=False
    )
    embed.add_field(name="예상 1인 분배", value=share_text(schedule), inline=False)
    embed.set_footer(text="부가 수익을 제외한 결정석값입니다.")
    return embed


class ConfirmView(discord.ui.View):
    """되돌리기 어려운 동작 앞에 두는 확인 버튼."""

    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=60)
        self.user_id = user_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "⛔ 명령을 실행한 사람만 누를 수 있습니다.", ephemeral=True
        )
        return False

    @discord.ui.button(label="삭제", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.confirmed = False
        await interaction.response.defer()
        self.stop()


class EditScheduleModal(discord.ui.Modal):
    """시각·요일(날짜)·파티원을 고치는 모달."""

    def __init__(self, schedule: PartySchedule) -> None:
        super().__init__(title=f"{schedule.boss_name} 일정 수정")
        self.schedule_id = schedule.id
        self.repeat_type = schedule.repeat_type

        self.clock = discord.ui.TextInput(
            label="시각 (HH:MM)",
            default=f"{schedule.hour:02d}:{schedule.minute:02d}",
            max_length=5,
        )
        if schedule.repeat_type == REPEAT_MONTHLY:
            day_label = "날짜 (1~31)"
            day_default = str(schedule.month_day or 1)
        else:
            day_label = "요일 (1=월 … 7=일)"
            day_default = str(schedule.weekday or 1)
        self.day = discord.ui.TextInput(label=day_label, default=day_default, max_length=2)
        self.members = discord.ui.TextInput(
            label="파티원 (콤마 구분)",
            default=", ".join(member.character.name for member in schedule.members),
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=400,
        )

        self.add_item(self.clock)
        self.add_item(self.day)
        self.add_item(self.members)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        clock = parse_clock(str(self.clock.value))
        if clock is None:
            await interaction.response.send_message(
                "❓ 시각은 `21:00` 처럼 24시간 표기로 적어주세요.", ephemeral=True
            )
            return

        try:
            day_value = int(str(self.day.value).strip())
        except ValueError:
            await interaction.response.send_message("❓ 숫자로 적어주세요.", ephemeral=True)
            return

        if self.repeat_type == REPEAT_MONTHLY:
            if not 1 <= day_value <= 31:
                await interaction.response.send_message(
                    "❓ 날짜는 1~31 사이여야 합니다.", ephemeral=True
                )
                return
        elif not 1 <= day_value <= 7:
            await interaction.response.send_message(
                "❓ 요일은 1(월)~7(일) 사이여야 합니다.", ephemeral=True
            )
            return

        names = parse_member_names(str(self.members.value or ""))
        hour, minute = clock

        with open_session(interaction) as session:
            schedule = get_schedule(session, interaction.guild_id, self.schedule_id)
            if schedule is None:
                await interaction.response.send_message(
                    "❓ 이미 삭제된 일정입니다.", ephemeral=True
                )
                return

            schedule.hour = hour
            schedule.minute = minute
            if self.repeat_type == REPEAT_MONTHLY:
                schedule.month_day = day_value
            else:
                schedule.weekday = day_value

            if names:
                schedule.members.clear()
                session.flush()
                for name in names:
                    character = get_or_create_character(session, interaction.guild_id, name)
                    schedule.members.append(PartyMember(character_id=character.id))
            session.flush()

            embed = schedule_embed(schedule, "✏️ 일정을 수정했습니다")

        await interaction.response.send_message(embed=embed)


@app_commands.guild_only()
class Party(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="파티등록", description="보스 파티 일정을 등록합니다.")
    @app_commands.describe(
        보스="보스 이름",
        난이도="이 보스에 있는 난이도만 고를 수 있습니다",
        시각="24시간 표기 (예: 21:00)",
        파티원="캐릭터명을 콤마로 구분 (예: 홍길동, 김철수)",
        요일="주간 보스일 때 지정",
        날짜="월간 보스(검은 마법사)일 때 지정 (1~31)",
    )
    @app_commands.autocomplete(보스=boss_autocomplete, 난이도=difficulty_autocomplete)
    @app_commands.choices(요일=WEEKDAY_CHOICES)
    async def register(
        self,
        interaction: discord.Interaction,
        보스: str,
        난이도: str,
        시각: str,
        파티원: str,
        요일: app_commands.Choice[int] | None = None,
        날짜: app_commands.Range[int, 1, 31] | None = None,
    ) -> None:
        validated = validate_boss_and_difficulty(보스, 난이도)
        if isinstance(validated, str):
            await interaction.response.send_message(f"❓ {validated}", ephemeral=True)
            return
        boss_name, difficulty = validated

        clock = parse_clock(시각)
        if clock is None:
            await interaction.response.send_message(
                "❓ 시각은 `21:00` 처럼 24시간 표기로 적어주세요.", ephemeral=True
            )
            return
        hour, minute = clock

        monthly = is_monthly_boss(boss_name)
        if monthly and 날짜 is None:
            await interaction.response.send_message(
                f"❓ `{boss_name}` 는 월간 보스입니다. `요일` 대신 `날짜`(1~31)를 지정해주세요.",
                ephemeral=True,
            )
            return
        if not monthly and 요일 is None:
            await interaction.response.send_message(
                "❓ 주간 보스는 `요일` 을 지정해주세요.", ephemeral=True
            )
            return

        names = parse_member_names(파티원)
        if not names:
            await interaction.response.send_message(
                "❓ 파티원을 한 명 이상 적어주세요.", ephemeral=True
            )
            return

        with open_session(interaction) as session:
            schedule = PartySchedule(
                guild_id=interaction.guild_id,
                boss_name=boss_name,
                difficulty=difficulty,
                repeat_type=REPEAT_MONTHLY if monthly else REPEAT_WEEKLY,
                weekday=None if monthly else 요일.value,
                month_day=날짜 if monthly else None,
                hour=hour,
                minute=minute,
                created_by=interaction.user.id,
                is_active=True,
            )
            session.add(schedule)
            session.flush()

            for name in names:
                character = get_or_create_character(session, interaction.guild_id, name)
                schedule.members.append(PartyMember(character_id=character.id))
            session.flush()

            embed = schedule_embed(schedule, "✅ 파티 일정을 등록했습니다")
            unlinked = [m.character.name for m in schedule.members if not m.character.is_linked]

        if unlinked:
            embed.add_field(
                name="미연결 캐릭터",
                value=f"{', '.join(unlinked)} — `/캐릭터등록` 으로 디스코드 계정과 연결할 수 있습니다.",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="파티목록", description="등록된 파티 일정을 봅니다.")
    async def listing(self, interaction: discord.Interaction) -> None:
        now = now_kst()
        with open_session(interaction) as session:
            schedules = active_schedules(session, interaction.guild_id)
            if not schedules:
                await interaction.response.send_message(
                    "등록된 파티 일정이 없습니다. `/파티등록` 으로 만들어보세요.", ephemeral=True
                )
                return

            embed = discord.Embed(title="🗓️ 파티 일정", color=EMBED_COLOR)
            for schedule in schedules[:25]:
                upcoming = next_run(schedule, now)
                embed.add_field(
                    name=f"#{schedule.id} · {schedule_label(schedule)}",
                    value=(
                        f"{discord_timestamp(upcoming)}\n"
                        f"파티원 {len(schedule.members)}명: {summarize_members(schedule)}\n"
                        f"1인 분배: {share_text(schedule)}"
                    ),
                    inline=False,
                )
            if len(schedules) > 25:
                embed.set_footer(text=f"이 외에 {len(schedules) - 25}개가 더 있습니다.")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="파티수정", description="파티 일정의 시각·요일·파티원을 고칩니다.")
    @app_commands.describe(일정="고칠 파티 일정")
    @app_commands.autocomplete(일정=schedule_autocomplete)
    async def edit(self, interaction: discord.Interaction, 일정: str) -> None:
        if not 일정.isdigit():
            await interaction.response.send_message(
                "❓ 자동완성 목록에서 일정을 골라주세요.", ephemeral=True
            )
            return

        with open_session(interaction) as session:
            schedule = get_schedule(session, interaction.guild_id, int(일정))
            if schedule is None:
                await interaction.response.send_message(
                    "❓ 해당 일정을 찾을 수 없습니다.", ephemeral=True
                )
                return
            modal = EditScheduleModal(schedule)

        await interaction.response.send_modal(modal)

    @app_commands.command(name="파티삭제", description="파티 일정을 삭제합니다.")
    @app_commands.describe(일정="삭제할 파티 일정")
    @app_commands.autocomplete(일정=schedule_autocomplete)
    async def delete(self, interaction: discord.Interaction, 일정: str) -> None:
        if not 일정.isdigit():
            await interaction.response.send_message(
                "❓ 자동완성 목록에서 일정을 골라주세요.", ephemeral=True
            )
            return

        schedule_id = int(일정)
        with open_session(interaction) as session:
            schedule = get_schedule(session, interaction.guild_id, schedule_id)
            if schedule is None:
                await interaction.response.send_message(
                    "❓ 해당 일정을 찾을 수 없습니다.", ephemeral=True
                )
                return
            label = schedule_label(schedule)

        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"🗑️ **{label}** 일정을 삭제할까요?", view=view, ephemeral=True
        )
        await view.wait()

        if not view.confirmed:
            await interaction.edit_original_response(content="취소했습니다.", view=None)
            return

        with open_session(interaction) as session:
            schedule = get_schedule(session, interaction.guild_id, schedule_id)
            if schedule is None:
                await interaction.edit_original_response(
                    content="❓ 이미 삭제된 일정입니다.", view=None
                )
                return
            schedule.is_active = False

        await interaction.edit_original_response(
            content=f"🗑️ **{label}** 일정을 삭제했습니다.", view=None
        )

    @app_commands.command(name="캐릭터등록", description="내 디스코드 계정에 캐릭터를 연결합니다.")
    @app_commands.describe(이름="캐릭터명", 대표="정산 기본 대상으로 삼을 대표 캐릭터인지")
    async def register_character(
        self, interaction: discord.Interaction, 이름: str, 대표: bool = False
    ) -> None:
        name = 이름.strip()
        if not name:
            await interaction.response.send_message("❓ 캐릭터명을 적어주세요.", ephemeral=True)
            return

        with open_session(interaction) as session:
            existing = find_character(session, interaction.guild_id, name)
            if existing is not None and existing.discord_user_id not in (
                None,
                interaction.user.id,
            ):
                await interaction.response.send_message(
                    f"⛔ `{name}` 은 이미 다른 사람의 캐릭터로 등록돼 있습니다.", ephemeral=True
                )
                return

            character = get_or_create_character(
                session, interaction.guild_id, name, interaction.user.id
            )
            was_unlinked = existing is not None and existing.discord_user_id is None

            if 대표:
                for other in characters_of_user(session, interaction.guild_id, interaction.user.id):
                    other.is_main = other.id == character.id
                character.is_main = True
            session.flush()

        머리말 = "🔗 미연결 캐릭터를 계정에 연결했습니다" if was_unlinked else "✅ 캐릭터를 등록했습니다"
        꼬리말 = " (대표 캐릭터)" if 대표 else ""
        await interaction.response.send_message(f"{머리말}: **{name}**{꼬리말}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Party(bot))
