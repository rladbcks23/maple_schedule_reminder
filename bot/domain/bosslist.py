"""'노말 스우 3, 하드 카링 4' 같은 보스 목록 파싱. discord 의존성 없는 순수 로직.

한 항목은 `난이도 보스명 [인원]` 꼴이다. 인원을 빼면 1인으로 본다.
보스명에 공백이 있어도(반 레온, 선택받은 세렌) 난이도와 인원을 먼저 떼어내면
가운데 남는 게 곧 보스명이라 그대로 붙여 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .boss_data import (
    DIFFICULTIES,
    DIFFICULTY_KO,
    canonical_boss_name,
    difficulties_for,
    normalize_difficulty,
)

MAX_PARTY_SIZE = 6


@dataclass(frozen=True)
class BossEntry:
    """수익을 계산할 보스 한 건."""

    boss_name: str
    difficulty: str
    party_size: int


def _parse_item(item: str) -> BossEntry | str:
    """항목 하나를 해석한다. 잘못됐으면 안내 문자열."""
    tokens = item.split()
    if not tokens:
        return f"`{item}` 을 읽을 수 없습니다."

    party_size = 1
    if len(tokens) > 1 and tokens[-1].isdigit():
        party_size = int(tokens.pop())
        if not 1 <= party_size <= MAX_PARTY_SIZE:
            return f"`{item}` 의 인원은 1~{MAX_PARTY_SIZE} 사이여야 합니다."

    if len(tokens) < 2:
        예시 = " ".join(tokens) or "스우"
        return f"`{item}` 에 난이도가 없습니다. `하드 {예시}` 처럼 적어주세요."

    difficulty = normalize_difficulty(tokens[0])
    if difficulty not in DIFFICULTIES:
        가능 = " / ".join(DIFFICULTY_KO.values())
        return f"`{tokens[0]}` 은 난이도가 아닙니다. 앞에 {가능} 중 하나를 적어주세요."

    boss_name = canonical_boss_name(" ".join(tokens[1:]))
    if boss_name is None:
        return f"`{' '.join(tokens[1:])}` 는 등록된 보스가 아닙니다."

    options = difficulties_for(boss_name)
    if difficulty not in options:
        가능 = ", ".join(DIFFICULTY_KO.get(option, option) for option in options)
        return f"`{boss_name}` 는 {가능} 만 있습니다."

    return BossEntry(boss_name=boss_name, difficulty=difficulty, party_size=party_size)


def parse_boss_list(text: str) -> tuple[list[BossEntry], list[str]]:
    """콤마로 구분된 목록을 해석한다. (읽어낸 항목, 오류 안내) 를 돌려준다.

    일부가 잘못돼도 나머지는 계산할 수 있게, 실패한 항목만 따로 모은다.
    """
    entries: list[BossEntry] = []
    errors: list[str] = []

    for chunk in text.replace("，", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        result = _parse_item(item)
        if isinstance(result, str):
            errors.append(result)
        else:
            entries.append(result)

    return entries, errors
