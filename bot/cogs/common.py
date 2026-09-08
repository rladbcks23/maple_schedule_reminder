"""코그들이 공유하는 조회 헬퍼와 자동완성 콜백.

사양의 파일 목록에는 없지만, party/income/admin 세 코그가 같은 조회 로직을
쓰기 때문에 중복을 피하려고 따로 뒀다. discord 의존성이 있으므로
domain/ 이 아니라 cogs/ 아래에 둔다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import discord
from discord import app_commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..domain.boss_data import (
    DIFFICULTY_KO,
    canonical_boss_name,
    default_boss_image,
    difficulties_for,
    normalize,
    search_boss_names,
)
from ..domain.income import PartyInfo
from ..domain.schedule import format_schedule_time, next_occurrence, now_kst
from ..models import BossImage, Character, PartySchedule

EMBED_COLOR = 0xF39C12
EMBED_COLOR_WARN = 0xE74C3C

MAX_CHOICES = 25


@contextmanager
def open_session(interaction: discord.Interaction) -> Iterator[Session]:
    """인터랙션에서 봇의 세션 팩토리를 꺼내 세션을 연다."""
    with session_scope(interaction.client.session_factory) as session:
        yield session


# --- 자동완성 ------------------------------------------------------------------


async def boss_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=name, value=name) for name in search_boss_names(current)]


async def difficulty_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """선택한 보스에 실제로 있는 난이도만 제안한다."""
    boss = getattr(interaction.namespace, "보스", None)
    options = difficulties_for(boss) if boss else []
    if not options:
        # 보스를 아직 안 골랐으면 전체 난이도를 보여준다.
        options = list(DIFFICULTY_KO)

    needle = normalize(current)
    return [
        app_commands.Choice(name=f"{DIFFICULTY_KO.get(value, value)} ({value})", value=value)
        for value in options
        if not needle or needle in normalize(value) or needle in DIFFICULTY_KO.get(value, "")
    ][:MAX_CHOICES]


async def schedule_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """활성 파티 일정을 고르는 자동완성. value는 일정 id 문자열."""
    if interaction.guild_id is None:
        return []

    needle = normalize(current)
    with open_session(interaction) as session:
        schedules = active_schedules(session, interaction.guild_id)
        choices = []
        for schedule in schedules:
            label = schedule_label(schedule)
            if needle and needle not in normalize(label):
                continue
            choices.append(app_commands.Choice(name=label[:100], value=str(schedule.id)))
        return choices[:MAX_CHOICES]


async def character_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []

    needle = normalize(current)
    with open_session(interaction) as session:
        rows = session.scalars(
            select(Character)
            .where(Character.guild_id == interaction.guild_id)
            .order_by(Character.is_main.desc(), Character.name)
        ).all()
        return [
            app_commands.Choice(name=row.display_name[:100], value=row.name)
            for row in rows
            if not needle or needle in normalize(row.name)
        ][:MAX_CHOICES]


# --- 조회 헬퍼 -----------------------------------------------------------------


def active_schedules(session: Session, guild_id: int) -> list[PartySchedule]:
    rows = session.scalars(
        select(PartySchedule).where(
            PartySchedule.guild_id == guild_id, PartySchedule.is_active.is_(True)
        )
    ).all()
    return sorted(rows, key=next_run)


def get_schedule(session: Session, guild_id: int, schedule_id: int) -> PartySchedule | None:
    schedule = session.get(PartySchedule, schedule_id)
    if schedule is None or schedule.guild_id != guild_id or not schedule.is_active:
        return None
    return schedule


def next_run(schedule: PartySchedule, now: datetime | None = None) -> datetime:
    return next_occurrence(
        now or now_kst(),
        repeat_type=schedule.repeat_type,
        weekday=schedule.weekday,
        month_day=schedule.month_day,
        hour=schedule.hour,
        minute=schedule.minute,
        once_at=schedule.once_at,
    )


def schedule_when(schedule: PartySchedule) -> str:
    return format_schedule_time(
        schedule.repeat_type,
        schedule.weekday,
        schedule.month_day,
        schedule.hour,
        schedule.minute,
        once_at=schedule.once_at,
    )


def schedule_label(schedule: PartySchedule) -> str:
    표시 = "고정" if schedule.is_recurring else "1회"
    return (
        f"[{표시}] {schedule.difficulty.upper()} {schedule.boss_name} · {schedule_when(schedule)}"
    )


def boss_image_url(session: Session, guild_id: int, boss_name: str) -> str | None:
    """서버가 등록한 보스 사진. 없으면 boss_data의 기본값을 쓴다."""
    row = session.get(BossImage, (guild_id, boss_name))
    if row is not None:
        return row.image_url
    return default_boss_image(boss_name)


def schedules_of_character(
    session: Session, guild_id: int, character_id: int
) -> list[PartySchedule]:
    """해당 캐릭터가 파티원으로 들어가 있는 활성 일정."""
    return [
        schedule
        for schedule in active_schedules(session, guild_id)
        if any(member.character_id == character_id for member in schedule.members)
    ]


class ConfirmView(discord.ui.View):
    """되돌리기 어려운 동작 앞에 두는 확인 버튼."""

    def __init__(self, user_id: int, label: str = "삭제") -> None:
        super().__init__(timeout=60)
        self.user_id = user_id
        self.confirmed: bool | None = None
        self.confirm.label = label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "⛔ 명령을 실행한 사람만 누를 수 있습니다.", ephemeral=True
        )
        return False

    @discord.ui.button(label="삭제", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        await interaction.response.defer()
        self.stop()


def party_infos(session: Session, guild_id: int) -> list[PartyInfo]:
    """수익 계산에 넘길 파티 정보로 변환한다."""
    return [
        PartyInfo(
            boss_name=schedule.boss_name,
            difficulty=schedule.difficulty,
            member_count=len(schedule.members),
            member_character_ids=frozenset(m.character_id for m in schedule.members),
        )
        for schedule in active_schedules(session, guild_id)
    ]


def find_character(session: Session, guild_id: int, name: str) -> Character | None:
    """이름으로 캐릭터를 찾는다. 공백 차이는 무시한다."""
    rows = session.scalars(select(Character).where(Character.guild_id == guild_id)).all()
    needle = normalize(name)
    for row in rows:
        if normalize(row.name) == needle:
            return row
    return None


def get_or_create_character(
    session: Session, guild_id: int, name: str, discord_user_id: int | None = None
) -> Character:
    """없으면 만든다. discord_user_id가 비면 '미연결 캐릭터'가 된다."""
    existing = find_character(session, guild_id, name)
    if existing is not None:
        if discord_user_id is not None and existing.discord_user_id is None:
            existing.discord_user_id = discord_user_id
        return existing

    character = Character(
        guild_id=guild_id, name=name, discord_user_id=discord_user_id, is_main=False
    )
    session.add(character)
    session.flush()
    return character


def guild_characters(session: Session, guild_id: int) -> list[Character]:
    """서버에 등록된 캐릭터 전부. 대표 캐릭터가 앞에 온다."""
    return list(
        session.scalars(
            select(Character)
            .where(Character.guild_id == guild_id)
            .order_by(Character.is_main.desc(), Character.name)
        ).all()
    )


def characters_of_user(session: Session, guild_id: int, user_id: int) -> list[Character]:
    return list(
        session.scalars(
            select(Character)
            .where(Character.guild_id == guild_id, Character.discord_user_id == user_id)
            .order_by(Character.is_main.desc(), Character.id)
        ).all()
    )


def resolve_target_characters(
    session: Session, guild_id: int, user_id: int, name: str | None
) -> tuple[list[Character], str | None]:
    """정산 대상 캐릭터를 정한다.

    이름을 주면 그 캐릭터 하나, 없으면 호출자의 대표 캐릭터,
    대표가 없으면 호출자에게 연결된 전 캐릭터를 쓴다.
    반환값의 두 번째 항목은 실패 사유 메시지다.
    """
    if name:
        character = find_character(session, guild_id, name)
        if character is None:
            return [], f"`{name}` 캐릭터를 찾을 수 없습니다."
        return [character], None

    mine = characters_of_user(session, guild_id, user_id)
    if not mine:
        return [], "연결된 캐릭터가 없습니다. `/캐릭터등록` 으로 먼저 등록해주세요."

    mains = [character for character in mine if character.is_main]
    return (mains or mine), None


# --- 입력 파싱 -----------------------------------------------------------------


def parse_clock(text: str) -> tuple[int, int] | None:
    """'21:30' / '2130' / '21' 을 (시, 분)으로. 잘못된 값이면 None."""
    cleaned = text.strip().replace("시", ":").replace("분", "").replace(" ", "").rstrip(":")
    try:
        if ":" in cleaned:
            hour_text, minute_text = cleaned.split(":", 1)
            hour, minute = int(hour_text), int(minute_text or 0)
        elif len(cleaned) == 4:
            hour, minute = int(cleaned[:2]), int(cleaned[2:])
        else:
            hour, minute = int(cleaned), 0
    except ValueError:
        return None

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_member_names(raw: str) -> list[str]:
    """콤마로 구분된 캐릭터명을 정리한다. 순서를 유지하고 중복은 뺀다."""
    names: list[str] = []
    seen: set[str] = set()
    for chunk in raw.replace("，", ",").split(","):
        name = chunk.strip()
        if not name:
            continue
        key = normalize(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def validate_boss_and_difficulty(boss: str, difficulty: str) -> tuple[str, str] | str:
    """정식 보스명과 난이도를 돌려준다. 잘못된 조합이면 안내 문자열을 돌려준다."""
    canonical = canonical_boss_name(boss)
    if canonical is None:
        return f"`{boss}` 는 등록된 보스가 아닙니다. 자동완성 목록에서 골라주세요."

    options = difficulties_for(canonical)
    if difficulty not in options:
        joined = ", ".join(options)
        return f"`{canonical}` 의 난이도는 {joined} 중에서 골라야 합니다."

    return canonical, difficulty
