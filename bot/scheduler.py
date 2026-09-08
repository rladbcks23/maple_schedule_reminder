"""파티 일정 알림 루프.

APScheduler 대신 discord.ext.tasks를 쓴다. 봇 라이프사이클(연결 대기, 종료 시
정리)에 그대로 얹히고 의존성이 하나 줄어드는데, 1분 간격 폴링이면 충분하기 때문이다.

중복 발송 방지는 NotificationLog의 (schedule_id, kind, occurrence_key) 유니크
제약에만 의존한다. 기록을 먼저 남기고 그게 성공했을 때만 메시지를 보내므로,
루프가 겹쳐 돌거나 봇이 재시작돼도 같은 회차는 한 번만 나간다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .cogs.common import EMBED_COLOR, active_schedules, next_run
from .db import session_scope
from .domain.boss_data import default_boss_image
from .domain.formatting import difficulty_ko, difficulty_tag, format_meso
from .domain.income import party_income
from .domain.schedule import (
    REPEAT_MONTHLY,
    REPEAT_ONCE,
    clamp_day,
    discord_timestamp,
    format_kst,
    now_kst,
    now_utc,
    occurrence_key,
    to_kst,
)
from .models import GuildConfig, NotificationLog, PartySchedule

log = logging.getLogger("maple.scheduler")

KIND_PRE30 = "pre30"
KIND_ONTIME = "ontime"

PRE_ALERT_WINDOW = timedelta(minutes=30)
# 정시 알림은 예정 시각 ±2분 안에서만. 봇이 꺼져 있던 동안 밀린 회차는 되살리지 않는다.
ONTIME_TOLERANCE = timedelta(minutes=2)
# 이만큼 지난 1회성 일정은 알림 없이 목록에서만 치운다.
STALE_ONCE_GRACE = timedelta(hours=1)


def current_occurrence(schedule: PartySchedule, now: datetime) -> datetime | None:
    """지금 시각이 속한 '오늘의 예정 시각'. 해당 요일/날짜가 아니면 None."""
    local = to_kst(now)

    if schedule.repeat_type == REPEAT_MONTHLY:
        if schedule.month_day is None:
            return None
        target_day = clamp_day(local.year, local.month, schedule.month_day)
        if local.day != target_day:
            return None
    else:
        if schedule.weekday is None or local.weekday() != schedule.weekday - 1:
            return None

    return local.replace(hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0)


class Scheduler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.alert_loop.start()

    async def cog_unload(self) -> None:
        self.alert_loop.cancel()

    @tasks.loop(minutes=1)
    async def alert_loop(self) -> None:
        now = now_kst()
        try:
            plans = self._collect_alerts(now)
        except Exception:
            log.exception("알림 대상 조회 실패")
            return

        for channel_id, schedule_id, kind, target, embed, mentions, retire in plans:
            sent = await self._send(channel_id, schedule_id, kind, target, embed, mentions)
            if sent and retire:
                self._deactivate(schedule_id)

        try:
            self._expire_stale_once_schedules(now)
        except Exception:
            log.exception("지난 1회성 일정 정리 실패")

    def _collect_alerts(self, now: datetime):
        """보낼 알림 목록을 만든다. DB 접근은 이 안에서 끝낸다."""
        plans = []
        with session_scope(self.bot.session_factory) as session:
            configs = session.scalars(
                select(GuildConfig).where(GuildConfig.notify_channel_id.is_not(None))
            ).all()

            for config in configs:
                for schedule in active_schedules(session, config.guild_id):
                    image_url = default_boss_image(schedule.boss_name)
                    upcoming = next_run(schedule, now)

                    if timedelta(0) < upcoming - now <= PRE_ALERT_WINDOW:
                        plans.append(
                            (
                                config.notify_channel_id,
                                schedule.id,
                                KIND_PRE30,
                                occurrence_key(upcoming),
                                self._build_embed(schedule, upcoming, KIND_PRE30, now, image_url),
                                self._mentions(schedule),
                                False,
                            )
                        )

                    current = self._ontime_moment(schedule, now, upcoming)
                    if current is not None:
                        plans.append(
                            (
                                config.notify_channel_id,
                                schedule.id,
                                KIND_ONTIME,
                                occurrence_key(current),
                                self._build_embed(schedule, current, KIND_ONTIME, now, image_url),
                                self._mentions(schedule),
                                # 1회성 파티는 정시 알림을 보내고 나면 없앤다.
                                not schedule.is_recurring,
                            )
                        )
        return plans

    def _ontime_moment(
        self, schedule: PartySchedule, now: datetime, upcoming: datetime
    ) -> datetime | None:
        """지금이 정시 알림을 보낼 순간이면 그 예정 시각, 아니면 None."""
        if schedule.repeat_type == REPEAT_ONCE:
            # 1회성은 예정 시각이 하나뿐이라 그것과만 비교한다.
            return upcoming if abs(now - upcoming) <= ONTIME_TOLERANCE else None

        current = current_occurrence(schedule, now)
        if current is not None and abs(now - current) <= ONTIME_TOLERANCE:
            return current
        return None

    def _expire_stale_once_schedules(self, now: datetime) -> None:
        """봇이 꺼져 있는 동안 지나가 버린 1회성 일정을 정리한다.

        되살려 알림을 보내지는 않고, 목록에서만 치운다.
        """
        cutoff = now - STALE_ONCE_GRACE
        with session_scope(self.bot.session_factory) as session:
            stale = session.scalars(
                select(PartySchedule).where(
                    PartySchedule.repeat_type == REPEAT_ONCE,
                    PartySchedule.is_active.is_(True),
                    PartySchedule.once_at.is_not(None),
                )
            ).all()
            for schedule in stale:
                if to_kst(schedule.once_at) < cutoff:
                    schedule.is_active = False
                    log.info("지나간 1회성 일정 정리: #%s", schedule.id)

    def _deactivate(self, schedule_id: int) -> None:
        with session_scope(self.bot.session_factory) as session:
            schedule = session.get(PartySchedule, schedule_id)
            if schedule is not None:
                schedule.is_active = False

    def _mentions(self, schedule: PartySchedule) -> str:
        """디스코드 계정이 연결된 파티원만 멘션한다."""
        user_ids = {
            member.character.discord_user_id
            for member in schedule.members
            if member.character.discord_user_id is not None
        }
        return " ".join(f"<@{user_id}>" for user_id in sorted(user_ids))

    def _member_lines(self, schedule: PartySchedule) -> str:
        """캐릭터명 + 등록할 때 연결한 사람 태그."""
        if not schedule.members:
            return "(없음)"

        줄 = []
        for member in schedule.members:
            character = member.character
            꼬리 = f" — <@{character.discord_user_id}>" if character.is_linked else " — (미연결)"
            줄.append(f"・**{character.name}**{꼬리}")
        return "\n".join(줄)

    def _build_embed(
        self,
        schedule: PartySchedule,
        target: datetime,
        kind: str,
        now: datetime,
        image_url: str | None,
    ) -> discord.Embed:
        """보스 사진 + 이름/난이도 + 시간 + 캐릭터 태그."""
        if kind == KIND_PRE30:
            남은 = int((target - now).total_seconds() // 60)
            머리 = f"⏰ {남은}분 뒤 보스 파티"
        else:
            머리 = "🚨 보스 파티 시작 시각입니다"

        embed = discord.Embed(
            title=f"{difficulty_tag(schedule.difficulty)} {schedule.boss_name}",
            description=머리,
            color=EMBED_COLOR,
        )
        if image_url:
            embed.set_thumbnail(url=image_url)

        embed.add_field(
            name="난이도",
            value=f"{difficulty_ko(schedule.difficulty)} ({difficulty_tag(schedule.difficulty)})",
            inline=True,
        )
        embed.add_field(
            name="반복", value="고정 파티" if schedule.is_recurring else "1회성", inline=True
        )
        embed.add_field(
            name="시간",
            value=f"{format_kst(target)}\n{discord_timestamp(target, 'R')}",
            inline=False,
        )
        embed.add_field(
            name=f"파티원 ({len(schedule.members)}명)",
            value=self._member_lines(schedule)[:1024],
            inline=False,
        )

        result = party_income(schedule.boss_name, schedule.difficulty, len(schedule.members))
        if result is not None:
            embed.add_field(
                name="예상 1인 분배", value=format_meso(result.share_meso), inline=False
            )
        embed.set_footer(text="부가 수익을 제외한 결정석값입니다.")
        return embed

    async def _send(
        self,
        channel_id: int,
        schedule_id: int,
        kind: str,
        target: str,
        embed: discord.Embed,
        mentions: str,
    ) -> bool:
        """실제로 보냈으면 True. 이미 보낸 회차면 False."""
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            log.warning("알림 채널 %s 을 찾을 수 없어 건너뜁니다.", channel_id)
            return False

        # 기록을 먼저 남긴다. 유니크 제약에 걸리면 이미 보낸 회차다.
        try:
            with session_scope(self.bot.session_factory) as session:
                session.add(
                    NotificationLog(
                        schedule_id=schedule_id,
                        kind=kind,
                        occurrence_key=target,
                        sent_at=now_utc(),
                    )
                )
        except IntegrityError:
            return False

        try:
            await channel.send(content=mentions or None, embed=embed)
        except discord.Forbidden:
            log.warning("채널 %s 에 메시지를 보낼 권한이 없습니다.", channel_id)
        except discord.HTTPException:
            log.exception("알림 발송 실패 (schedule=%s, kind=%s)", schedule_id, kind)
        return True

    @alert_loop.before_loop
    async def before_alert_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Scheduler(bot))
