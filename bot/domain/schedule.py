"""주기 경계와 다음 실행 시각 계산. discord 의존성 없는 순수 로직."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 주간 리셋은 목요일 KST 00:00. datetime.weekday() 기준 월=0 이므로 목=3.
WEEKLY_RESET_WEEKDAY = 3

WEEKDAY_NAMES = ("월", "화", "수", "목", "금", "토", "일")

REPEAT_WEEKLY = "weekly"
REPEAT_MONTHLY = "monthly"
# 고정 파티가 아닌 1회성 일정. 알림이 나간 뒤 비활성화된다.
REPEAT_ONCE = "once"
REPEAT_TYPES = (REPEAT_WEEKLY, REPEAT_MONTHLY, REPEAT_ONCE)


# --- 타임존 -------------------------------------------------------------------


def to_kst(moment: datetime) -> datetime:
    """KST로 변환. tz 정보가 없으면 UTC로 저장된 값으로 본다."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(KST)


def to_utc(moment: datetime) -> datetime:
    """DB 저장용 UTC aware datetime으로 변환."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    return moment.astimezone(UTC)


def now_kst() -> datetime:
    return datetime.now(KST)


def now_utc() -> datetime:
    return datetime.now(UTC)


# --- 주기 키 ------------------------------------------------------------------


def weekly_reset_anchor(moment: datetime) -> datetime:
    """moment가 속한 주의 시작, 즉 가장 최근에 지난 목요일 KST 00:00.

    목요일 00:00 정각은 그 주의 시작으로 본다.
    """
    local = to_kst(moment)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_reset = (local.weekday() - WEEKLY_RESET_WEEKDAY) % 7
    return midnight - timedelta(days=days_since_reset)


def week_period_key(moment: datetime) -> str:
    """'2026-W37' 형태의 주차 키.

    ISO 주차를 그대로 쓰지 않고 목요일 리셋으로 자른 주의 시작일을 기준으로 삼는다.
    ISO 주차는 그 주의 목요일이 결정하므로, 리셋 기준일(목요일)의 ISO 주차가
    곧 이 주의 번호가 된다.
    """
    anchor = weekly_reset_anchor(moment)
    iso = anchor.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def month_period_key(moment: datetime) -> str:
    """'2026-09' 형태의 월 키. 월간 리셋은 매월 1일 KST 00:00."""
    local = to_kst(moment)
    return f"{local.year:04d}-{local.month:02d}"


def period_key(repeat_type: str, moment: datetime) -> str:
    if repeat_type == REPEAT_MONTHLY:
        return month_period_key(moment)
    if repeat_type == REPEAT_WEEKLY:
        return week_period_key(moment)
    raise ValueError(f"알 수 없는 반복 주기: {repeat_type}")


# --- 다음 실행 시각 ------------------------------------------------------------


def clamp_day(year: int, month: int, day: int) -> int:
    """해당 월에 없는 날짜는 그 달의 마지막 날로 맞춘다. (31일 지정 + 2월 -> 28/29일)"""
    last_day = calendar.monthrange(year, month)[1]
    return min(day, last_day)


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def next_occurrence(
    now: datetime,
    *,
    repeat_type: str,
    hour: int,
    minute: int,
    weekday: int | None = None,
    month_day: int | None = None,
    once_at: datetime | None = None,
) -> datetime:
    """다음 실행 시각(KST aware).

    weekday는 1=월 … 7=일. 계산 결과가 현재 시각보다 뒤가 아니면 다음 주기로 넘긴다.
    once는 반복하지 않으므로 지정된 시각을 그대로 돌려준다(지난 시각이어도).
    """
    local = to_kst(now)

    if repeat_type == REPEAT_ONCE:
        if once_at is None:
            raise ValueError("once 일정에는 once_at이 필요합니다.")
        return to_kst(once_at)

    if repeat_type == REPEAT_WEEKLY:
        if weekday is None:
            raise ValueError("weekly 일정에는 weekday가 필요합니다.")
        target_weekday = weekday - 1  # 월=0 기준으로 맞춘다.
        days_ahead = (target_weekday - local.weekday()) % 7
        candidate = (local + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate

    if repeat_type == REPEAT_MONTHLY:
        if month_day is None:
            raise ValueError("monthly 일정에는 month_day가 필요합니다.")
        year, month = local.year, local.month
        candidate = local.replace(
            day=clamp_day(year, month, month_day),
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if candidate <= local:
            year, month = _add_month(year, month)
            candidate = candidate.replace(
                year=year, month=month, day=clamp_day(year, month, month_day)
            )
        return candidate

    raise ValueError(f"알 수 없는 반복 주기: {repeat_type}")


def occurrence_key(moment: datetime) -> str:
    """알림 중복 방지에 쓰는 회차 식별자. 예정 시각을 분 단위로 찍는다."""
    return to_kst(moment).strftime("%Y-%m-%dT%H:%M")


def parse_date(text: str, now: datetime | None = None) -> datetime | None:
    """'2026-09-10' / '09-10' / '9/10' 을 그 날 00:00 KST로.

    연도를 생략하면 올해로 보되, 이미 지난 날짜면 내년으로 넘긴다.
    """
    local = to_kst(now or now_kst())
    cleaned = text.strip().replace("/", "-").replace(".", "-")
    parts = [chunk for chunk in cleaned.split("-") if chunk]

    try:
        if len(parts) == 3:
            year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
        elif len(parts) == 2:
            year, month, day = (local.year, int(parts[0]), int(parts[1]))
        else:
            return None
        parsed = datetime(year, month, day, tzinfo=KST)
    except ValueError:
        return None

    if len(parts) == 2 and parsed.date() < local.date():
        try:
            parsed = parsed.replace(year=year + 1)
        except ValueError:  # 2월 29일 같은 경우
            return None
    return parsed


def format_schedule_time(
    repeat_type: str,
    weekday: int | None,
    month_day: int | None,
    hour: int,
    minute: int,
    once_at: datetime | None = None,
) -> str:
    """'매주 목 21:00' / '매월 15일 21:00' / '2026-09-10(목) 21:00' 표기."""
    clock = f"{hour:02d}:{minute:02d}"
    if repeat_type == REPEAT_ONCE and once_at is not None:
        local = to_kst(once_at)
        return f"{local:%Y-%m-%d}({WEEKDAY_NAMES[local.weekday()]}) {clock}"
    if repeat_type == REPEAT_MONTHLY and month_day is not None:
        return f"매월 {month_day}일 {clock}"
    if repeat_type == REPEAT_WEEKLY and weekday is not None:
        return f"매주 {WEEKDAY_NAMES[weekday - 1]} {clock}"
    return clock


def format_kst(moment: datetime) -> str:
    local = to_kst(moment)
    return f"{local:%Y-%m-%d}({WEEKDAY_NAMES[local.weekday()]}) {local:%H:%M}"


def discord_timestamp(moment: datetime, style: str = "R") -> str:
    """디스코드가 보는 사람 로컬 시간대로 렌더링해주는 타임스탬프 마크업."""
    return f"<t:{int(to_utc(moment).timestamp())}:{style}>"
