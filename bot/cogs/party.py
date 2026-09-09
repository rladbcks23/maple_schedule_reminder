"""파티 일정 등록/조회/수정/삭제."""

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
    REPEAT_ONCE,
    REPEAT_WEEKLY,
    WEEKDAY_NAMES,
    discord_timestamp,
    now_kst,
    parse_date,
    to_utc,
)
from ..models import PartyMember, PartySchedule
from .common import (
    EMBED_COLOR,
    ConfirmView,
    active_schedules,
    boss_autocomplete,
    difficulty_autocomplete,
    get_or_create_character,
    issue_code,
    my_character_autocomplete,
    next_run,
    open_session,
    parse_clock,
    parse_member_names,
    resolve_schedule,
    resolve_target_characters,
    schedule_autocomplete,
    schedule_tag,
    schedule_when,
    schedules_of_character,
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
    upcoming = next_run(schedule)
    반복 = "고정 파티" if schedule.is_recurring else "고정이 아닌 파티 (알림 후 자동 삭제)"

    embed = discord.Embed(
        title=title,
        description=f"`{schedule.code}` · **{schedule.difficulty.upper()} {schedule.boss_name}**",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="일정",
        value=f"{schedule_when(schedule)} · {discord_timestamp(upcoming)}\n{반복}",
        inline=False,
    )
    embed.add_field(
        name=f"파티원 ({len(schedule.members)}명)",
        value=summarize_members(schedule),
        inline=False,
    )
    embed.add_field(name="예상 1인 분배", value=share_text(schedule), inline=False)
    embed.set_footer(text=f"이 파티의 코드는 {schedule.code} 입니다. 수정·삭제할 때 쓰세요.")
    return embed


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
        if schedule.repeat_type == REPEAT_ONCE:
            day_label = "날짜 (2026-09-10)"
            day_default = f"{next_run(schedule):%Y-%m-%d}"
            day_max = 10
        elif schedule.repeat_type == REPEAT_MONTHLY:
            day_label = "날짜 (1~31)"
            day_default = str(schedule.month_day or 1)
            day_max = 2
        else:
            day_label = "요일 (1=월 … 7=일)"
            day_default = str(schedule.weekday or 1)
            day_max = 2

        self.day = discord.ui.TextInput(label=day_label, default=day_default, max_length=day_max)
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
        hour, minute = clock
        raw_day = str(self.day.value).strip()

        once_at = None
        day_value = None
        if self.repeat_type == REPEAT_ONCE:
            parsed = parse_date(raw_day)
            if parsed is None:
                await interaction.response.send_message(
                    "❓ 날짜는 `2026-09-10` 형식으로 적어주세요.", ephemeral=True
                )
                return
            once_at = to_utc(parsed.replace(hour=hour, minute=minute))
        else:
            try:
                day_value = int(raw_day)
            except ValueError:
                await interaction.response.send_message("❓ 숫자로 적어주세요.", ephemeral=True)
                return

            상한 = 31 if self.repeat_type == REPEAT_MONTHLY else 7
            if not 1 <= day_value <= 상한:
                이름 = "날짜" if self.repeat_type == REPEAT_MONTHLY else "요일"
                await interaction.response.send_message(
                    f"❓ {이름}는 1~{상한} 사이여야 합니다.", ephemeral=True
                )
                return

        names = parse_member_names(str(self.members.value or ""))

        with open_session(interaction) as session:
            schedule = session.get(PartySchedule, self.schedule_id)
            if schedule is None or not schedule.is_active:
                await interaction.response.send_message(
                    "❓ 이미 삭제된 일정입니다.", ephemeral=True
                )
                return

            schedule.hour = hour
            schedule.minute = minute
            if self.repeat_type == REPEAT_ONCE:
                schedule.once_at = once_at
            elif self.repeat_type == REPEAT_MONTHLY:
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

    @app_commands.command(
        name="파티등록", description="보스 파티를 등록합니다. 고정을 끄면 이번 한 번만 모입니다."
    )
    @app_commands.describe(
        보스="보스 이름",
        난이도="이 보스에 있는 난이도만 고를 수 있습니다",
        시각="24시간 표기 (예: 21:00)",
        고정="매주 반복하면 True, 이번 한 번만 모이면 False (기본 True)",
        요일="고정 주간 파티일 때 지정",
        날짜="고정 월간 보스면 `15`, 고정이 아니면 `2026-09-10`",
        파티원="캐릭터명을 콤마로 구분 (예: 본캐, 길드원A)",
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
        고정: bool = True,
        요일: app_commands.Choice[int] | None = None,
        날짜: str | None = None,
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

        plan = self._resolve_when(boss_name, 고정, 요일, 날짜, hour, minute)
        if isinstance(plan, str):
            await interaction.response.send_message(f"❓ {plan}", ephemeral=True)
            return
        repeat_type, weekday, month_day, once_at = plan

        names = parse_member_names(파티원)
        if not names:
            await interaction.response.send_message(
                "❓ 파티원을 한 명 이상 적어주세요. 콤마로 구분합니다. (예: 본캐, 길드원A)",
                ephemeral=True,
            )
            return

        with open_session(interaction) as session:
            schedule = PartySchedule(
                guild_id=interaction.guild_id,
                boss_name=boss_name,
                difficulty=difficulty,
                repeat_type=repeat_type,
                weekday=weekday,
                month_day=month_day,
                once_at=once_at,
                hour=hour,
                minute=minute,
                created_by=interaction.user.id,
                is_active=True,
            )
            schedule.code = issue_code(session, interaction.guild_id, boss_name)
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
                value=f"{', '.join(unlinked)} — `/캐릭터등록` 으로 연결하면 알림에서 멘션됩니다.",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    def _resolve_when(
        self,
        boss_name: str,
        고정: bool,
        요일: app_commands.Choice[int] | None,
        날짜: str | None,
        hour: int,
        minute: int,
    ):
        """반복 종류와 시각 관련 컬럼을 정한다. 문제가 있으면 안내 문자열."""
        if not 고정:
            if not 날짜:
                return "고정이 아닌 파티는 `날짜` 를 `2026-09-10` 형식으로 지정해주세요."
            parsed = parse_date(날짜)
            if parsed is None:
                return "날짜는 `2026-09-10` 형식으로 적어주세요."
            moment = parsed.replace(hour=hour, minute=minute)
            if moment <= now_kst():
                return "이미 지난 시각입니다. 앞으로의 날짜와 시각을 골라주세요."
            return REPEAT_ONCE, None, None, to_utc(moment)

        if is_monthly_boss(boss_name):
            if not 날짜:
                return f"`{boss_name}` 는 월간 보스입니다. `날짜` 에 `15` 처럼 일자를 적어주세요."
            try:
                month_day = int(날짜.strip())
            except ValueError:
                return "월간 보스의 `날짜` 는 1~31 사이 숫자여야 합니다."
            if not 1 <= month_day <= 31:
                return "월간 보스의 `날짜` 는 1~31 사이여야 합니다."
            return REPEAT_MONTHLY, None, month_day, None

        if 요일 is None:
            return "고정 주간 파티는 `요일` 을 지정해주세요."
        return REPEAT_WEEKLY, 요일.value, None, None

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
                    name=schedule_tag(schedule),
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

    @app_commands.command(
        name="내일정",
        description="캐릭터가 낀 파티를 봅니다. 캐릭터를 비우면 내 캐릭터 전부를 봅니다.",
    )
    @app_commands.describe(캐릭터="비우면 내 캐릭터를 모두 봅니다")
    @app_commands.autocomplete(캐릭터=my_character_autocomplete)
    async def my_schedules(
        self, interaction: discord.Interaction, 캐릭터: str | None = None
    ) -> None:
        now = now_kst()
        with open_session(interaction) as session:
            targets, error = resolve_target_characters(
                session, interaction.guild_id, interaction.user.id, 캐릭터
            )
            if error:
                await interaction.response.send_message(f"❓ {error}", ephemeral=True)
                return

            블록 = []
            전체 = 0
            for character in targets:
                schedules = schedules_of_character(session, interaction.guild_id, character.id)
                전체 += len(schedules)
                if not schedules:
                    블록.append((character.name, ["(참여 중인 파티 없음)"]))
                    continue

                줄 = [
                    f"{schedule_tag(schedule)}\n"
                    f"　{discord_timestamp(next_run(schedule, now))}"
                    f" · {len(schedule.members)}인 · {share_text(schedule)}"
                    for schedule in schedules[:10]
                ]
                if len(schedules) > 10:
                    줄.append(f"…외 {len(schedules) - 10}개")
                블록.append((character.name, 줄))

            이름들 = ", ".join(character.display_name for character in targets)

        embed = discord.Embed(
            title=f"🗓️ {이름들} 의 파티 일정",
            description=f"총 {전체}개",
            color=EMBED_COLOR,
        )
        for 캐릭명, 줄들 in 블록[:25]:
            embed.add_field(name=f"🧙 {캐릭명}", value="\n".join(줄들)[:1024], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="파티수정",
        description="파티의 시각·요일·파티원을 고칩니다. 파티코드는 /파티목록 에서 확인하세요.",
    )
    @app_commands.describe(파티코드="고칠 파티의 코드 (예: SU4K)")
    @app_commands.autocomplete(파티코드=schedule_autocomplete)
    async def edit(self, interaction: discord.Interaction, 파티코드: str) -> None:
        with open_session(interaction) as session:
            schedule = resolve_schedule(session, interaction.guild_id, 파티코드)
            if schedule is None:
                await interaction.response.send_message(
                    f"❓ `{파티코드}` 코드의 파티가 없습니다. `/파티목록` 에서 확인해주세요.",
                    ephemeral=True,
                )
                return
            modal = EditScheduleModal(schedule)

        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="파티삭제", description="파티 일정을 삭제합니다. 파티코드는 /파티목록 에서 확인하세요."
    )
    @app_commands.describe(파티코드="삭제할 파티의 코드 (예: SU4K)")
    @app_commands.autocomplete(파티코드=schedule_autocomplete)
    async def delete(self, interaction: discord.Interaction, 파티코드: str) -> None:
        with open_session(interaction) as session:
            schedule = resolve_schedule(session, interaction.guild_id, 파티코드)
            if schedule is None:
                await interaction.response.send_message(
                    f"❓ `{파티코드}` 코드의 파티가 없습니다. `/파티목록` 에서 확인해주세요.",
                    ephemeral=True,
                )
                return
            schedule_id = schedule.id
            label = schedule_tag(schedule)

        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"🗑️ **{label}** 일정을 삭제할까요?", view=view, ephemeral=True
        )
        await view.wait()

        if not view.confirmed:
            await interaction.edit_original_response(content="취소했습니다.", view=None)
            return

        with open_session(interaction) as session:
            schedule = session.get(PartySchedule, schedule_id)
            if schedule is None or not schedule.is_active:
                await interaction.edit_original_response(
                    content="❓ 이미 삭제된 일정입니다.", view=None
                )
                return
            schedule.is_active = False

        await interaction.edit_original_response(
            content=f"🗑️ **{label}** 일정을 삭제했습니다.", view=None
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Party(bot))
