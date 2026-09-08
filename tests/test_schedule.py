from datetime import UTC, datetime

import pytest

from bot.domain.schedule import (
    KST,
    clamp_day,
    format_schedule_time,
    month_period_key,
    next_occurrence,
    parse_date,
    period_key,
    to_kst,
    to_utc,
    week_period_key,
    weekly_reset_anchor,
)

MON, TUE, WED, THU, FRI, SAT, SUN = 1, 2, 3, 4, 5, 6, 7


def kst(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=KST)


# --- 주간 리셋 경계 -----------------------------------------------------------


def test_weekly_reset_boundary_splits_wednesday_and_thursday():
    # 주간 리셋은 목요일 KST 00:00. 수요일 23:59와 목요일 00:01은 다른 주다.
    before = week_period_key(kst(2026, 9, 9, 23, 59))
    after = week_period_key(kst(2026, 9, 10, 0, 1))
    assert before != after
    assert before == "2026-W36"
    assert after == "2026-W37"


def test_weekly_reset_anchor_is_most_recent_thursday_midnight():
    assert weekly_reset_anchor(kst(2026, 9, 9, 23, 59)) == kst(2026, 9, 3)
    assert weekly_reset_anchor(kst(2026, 9, 10, 0, 1)) == kst(2026, 9, 10)
    # 목요일 00:00 정각은 그 주의 시작이다.
    assert weekly_reset_anchor(kst(2026, 9, 10, 0, 0)) == kst(2026, 9, 10)


def test_week_period_key_is_stable_within_one_week():
    keys = {
        week_period_key(kst(2026, 9, 10, 0, 0)),
        week_period_key(kst(2026, 9, 13, 12, 30)),
        week_period_key(kst(2026, 9, 16, 23, 59)),
    }
    assert keys == {"2026-W37"}


def test_week_period_key_uses_kst_not_utc():
    # UTC 2026-09-09 15:30 == KST 2026-09-10 00:30 이므로 목요일 주차다.
    moment = datetime(2026, 9, 9, 15, 30, tzinfo=UTC)
    assert week_period_key(moment) == "2026-W37"


def test_month_period_key():
    assert month_period_key(kst(2026, 9, 1, 0, 0)) == "2026-09"
    assert month_period_key(kst(2026, 9, 30, 23, 59)) == "2026-09"
    assert month_period_key(kst(2026, 10, 1, 0, 0)) == "2026-10"


def test_period_key_dispatches_on_repeat_type():
    moment = kst(2026, 9, 13, 12, 0)
    assert period_key("weekly", moment) == "2026-W37"
    assert period_key("monthly", moment) == "2026-09"


# --- 일 clamp ----------------------------------------------------------------


def test_clamp_day_handles_short_months():
    assert clamp_day(2026, 2, 31) == 28
    assert clamp_day(2024, 2, 31) == 29  # 윤년
    assert clamp_day(2026, 4, 31) == 30
    assert clamp_day(2026, 1, 31) == 31
    assert clamp_day(2026, 3, 15) == 15


# --- 다음 실행 시각 ------------------------------------------------------------


def test_weekly_next_occurrence_moves_to_next_week_when_time_passed_today():
    # 목요일 21:00 일정인데 지금이 목요일 21:30이면 다음 주 목요일이다.
    now = kst(2026, 9, 10, 21, 30)
    result = next_occurrence(now, repeat_type="weekly", weekday=THU, hour=21, minute=0)
    assert result == kst(2026, 9, 17, 21, 0)


def test_weekly_next_occurrence_is_today_when_time_not_passed():
    now = kst(2026, 9, 10, 20, 0)
    result = next_occurrence(now, repeat_type="weekly", weekday=THU, hour=21, minute=0)
    assert result == kst(2026, 9, 10, 21, 0)


def test_weekly_next_occurrence_exact_same_minute_moves_to_next_week():
    # 정확히 같은 시각이면 '뒤'가 아니므로 7일을 더한다.
    now = kst(2026, 9, 10, 21, 0)
    result = next_occurrence(now, repeat_type="weekly", weekday=THU, hour=21, minute=0)
    assert result == kst(2026, 9, 17, 21, 0)


def test_weekly_next_occurrence_finds_upcoming_weekday():
    now = kst(2026, 9, 8, 12, 0)  # 화요일
    result = next_occurrence(now, repeat_type="weekly", weekday=SUN, hour=9, minute=30)
    assert result == kst(2026, 9, 13, 9, 30)


def test_monthly_next_occurrence_clamps_day_to_end_of_month():
    # 매월 31일 일정이 2월에는 28일로 떨어진다.
    now = kst(2026, 2, 1, 0, 0)
    result = next_occurrence(now, repeat_type="monthly", month_day=31, hour=20, minute=0)
    assert result == kst(2026, 2, 28, 20, 0)


def test_monthly_next_occurrence_clamps_to_leap_day():
    now = kst(2024, 2, 1, 0, 0)
    result = next_occurrence(now, repeat_type="monthly", month_day=31, hour=20, minute=0)
    assert result == kst(2024, 2, 29, 20, 0)


def test_monthly_next_occurrence_rolls_into_next_month_when_passed():
    now = kst(2026, 1, 31, 21, 0)
    result = next_occurrence(now, repeat_type="monthly", month_day=31, hour=20, minute=0)
    assert result == kst(2026, 2, 28, 20, 0)


def test_monthly_next_occurrence_rolls_over_year_end():
    now = kst(2026, 12, 25, 21, 0)
    result = next_occurrence(now, repeat_type="monthly", month_day=1, hour=20, minute=0)
    assert result == kst(2027, 1, 1, 20, 0)


def test_next_occurrence_requires_matching_arguments():
    now = kst(2026, 9, 8, 12, 0)
    with pytest.raises(ValueError):
        next_occurrence(now, repeat_type="weekly", hour=21, minute=0)
    with pytest.raises(ValueError):
        next_occurrence(now, repeat_type="monthly", hour=21, minute=0)
    with pytest.raises(ValueError):
        next_occurrence(now, repeat_type="yearly", weekday=THU, hour=21, minute=0)


# --- 타임존 왕복 --------------------------------------------------------------


def test_utc_kst_roundtrip():
    moment = kst(2026, 9, 10, 21, 0)
    stored = to_utc(moment)
    assert stored.tzinfo is UTC
    assert stored.hour == 12  # KST 21:00 == UTC 12:00
    assert to_kst(stored) == moment


def test_to_kst_treats_naive_datetime_as_utc():
    # DB에서 tz 정보가 떨어진 채로 올라오는 경우를 대비한다.
    naive = datetime(2026, 9, 10, 12, 0)
    assert to_kst(naive) == kst(2026, 9, 10, 21, 0)


# --- 고정이 아닌 일정 -----------------------------------------------------------


def test_once_occurrence_returns_the_stored_moment():
    now = kst(2026, 9, 8, 12, 0)
    target = kst(2026, 9, 10, 21, 0)
    result = next_occurrence(now, repeat_type="once", hour=21, minute=0, once_at=target)
    assert result == target


def test_once_occurrence_does_not_roll_forward_when_passed():
    # 고정이 아닌 일정은 반복하지 않으므로 지난 시각이어도 그대로 둔다.
    now = kst(2026, 9, 11, 12, 0)
    target = kst(2026, 9, 10, 21, 0)
    result = next_occurrence(now, repeat_type="once", hour=21, minute=0, once_at=target)
    assert result == target


def test_once_occurrence_requires_once_at():
    with pytest.raises(ValueError):
        next_occurrence(kst(2026, 9, 8, 12, 0), repeat_type="once", hour=21, minute=0)


# --- 날짜 파싱 -----------------------------------------------------------------


def test_parse_date_accepts_full_date():
    assert parse_date("2026-09-10", now=kst(2026, 9, 8)) == kst(2026, 9, 10)
    assert parse_date("2026/09/10", now=kst(2026, 9, 8)) == kst(2026, 9, 10)
    assert parse_date("2026.09.10", now=kst(2026, 9, 8)) == kst(2026, 9, 10)


def test_parse_date_fills_in_current_year():
    assert parse_date("09-10", now=kst(2026, 9, 8)) == kst(2026, 9, 10)
    assert parse_date("9/10", now=kst(2026, 9, 8)) == kst(2026, 9, 10)


def test_parse_date_rolls_to_next_year_when_already_passed():
    # 연도를 생략했고 올해 날짜가 이미 지났으면 내년으로 본다.
    assert parse_date("01-05", now=kst(2026, 9, 8)) == kst(2027, 1, 5)


def test_parse_date_keeps_today():
    assert parse_date("09-08", now=kst(2026, 9, 8, 15, 0)) == kst(2026, 9, 8)


def test_parse_date_rejects_bad_input():
    now = kst(2026, 9, 8)
    assert parse_date("내일", now=now) is None
    assert parse_date("2026-13-01", now=now) is None
    assert parse_date("2026-02-30", now=now) is None
    assert parse_date("10", now=now) is None


# --- 일정 표기 -----------------------------------------------------------------


def test_format_schedule_time_by_repeat_type():
    assert format_schedule_time("weekly", 4, None, 21, 0) == "매주 목 21:00"
    assert format_schedule_time("monthly", None, 15, 20, 30) == "매월 15일 20:30"
    assert (
        format_schedule_time("once", None, None, 21, 0, once_at=kst(2026, 9, 10, 21, 0))
        == "2026-09-10(목) 21:00"
    )
