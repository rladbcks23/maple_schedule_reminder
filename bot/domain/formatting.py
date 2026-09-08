"""메소·솔 에르다 기운 표기. 원본 Flutter 앱(maple_daily_log)과 결과가 같아야 한다."""

from __future__ import annotations

from .boss_data import DIFFICULTY_KO

EOK = 100_000_000
MAN = 10_000


def format_meso(value: int) -> str:
    """억/만 단위로 쪼갠 표기.

    0 이하는 '-', 만 미만은 원본 숫자 그대로. 만 미만 잔돈은 버린다.
    123_450_000 -> '1억 2345만'
    """
    if value <= 0:
        return "-"

    eok = value // EOK
    man = (value % EOK) // MAN

    if eok and man:
        return f"{eok}억 {man}만"
    if eok:
        return f"{eok}억"
    if man:
        return f"{man}만"
    return str(value)


def format_sol_erda(value: int) -> str:
    """솔 에르다 기운 표기. 0 이하는 '-'."""
    if value <= 0:
        return "-"
    return f"{value}기운"


def difficulty_ko(difficulty: str) -> str:
    """영문 난이도를 한글로. 모르는 값은 그대로 돌려준다."""
    return DIFFICULTY_KO.get(difficulty.lower(), difficulty)


def difficulty_tag(difficulty: str) -> str:
    """상세 라인 앞에 붙는 대문자 난이도 태그. 'hard' -> 'HARD'"""
    return difficulty.upper()
