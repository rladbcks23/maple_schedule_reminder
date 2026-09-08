"""결정석 수익 계산. discord 의존성 없는 순수 로직.

분배는 전부 정수 나눗셈(내림)이다. 원본 Flutter 앱과 결과가 같아야 한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .boss_data import get_reward, is_season_boss, normalize, normalize_difficulty
from .formatting import difficulty_tag, format_meso

MISSING_PRICE_TEXT = "시세 정보 없음"


@dataclass(frozen=True)
class PartyInfo:
    """수익 계산에 필요한 만큼만 추린 파티 일정."""

    boss_name: str
    difficulty: str
    member_count: int
    member_character_ids: frozenset[int] = field(default_factory=frozenset)

    def matches(self, boss_name: str, difficulty: str) -> bool:
        return normalize(self.boss_name) == normalize(boss_name) and normalize_difficulty(
            self.difficulty
        ) == normalize_difficulty(difficulty)


@dataclass(frozen=True)
class ClearInput:
    """한 캐릭터의 보스 클리어 한 건."""

    boss_name: str
    difficulty: str
    character_id: int


@dataclass(frozen=True)
class IncomeLine:
    """정산 임베드에 한 줄로 들어가는 항목."""

    boss_name: str
    difficulty: str
    party_size: int
    total_meso: int | None
    total_sol_erda: int | None

    @property
    def has_price(self) -> bool:
        return self.total_meso is not None

    @property
    def share_meso(self) -> int:
        return 0 if self.total_meso is None else self.total_meso // self.party_size

    @property
    def share_sol_erda(self) -> int:
        return 0 if self.total_sol_erda is None else self.total_sol_erda // self.party_size

    def render(self) -> str:
        """'HARD 스우: 1287만 / 4인 분배' 형태. 시세가 없으면 그 사실을 남긴다."""
        head = f"{difficulty_tag(self.difficulty)} {self.boss_name}"
        if not self.has_price:
            return f"{head}: {MISSING_PRICE_TEXT}"
        return f"{head}: {format_meso(self.share_meso)} / {self.party_size}인 분배"


@dataclass(frozen=True)
class IncomeReport:
    lines: tuple[IncomeLine, ...]
    total_meso: int
    total_sol_erda: int

    @property
    def missing_lines(self) -> list[IncomeLine]:
        """시세를 몰라 합계에서 빠진 항목. 조용히 사라지면 안 되므로 따로 노출한다."""
        return [line for line in self.lines if not line.has_price]


@dataclass(frozen=True)
class PartyIncome:
    """파티 일정 하나의 총 결정석값과 1인 분배액."""

    boss_name: str
    difficulty: str
    member_count: int
    total_meso: int
    total_sol_erda: int

    @property
    def share_meso(self) -> int:
        return self.total_meso // self.member_count

    @property
    def share_sol_erda(self) -> int:
        return self.total_sol_erda // self.member_count


def resolve_party_size(
    boss_name: str,
    difficulty: str,
    character_id: int | None,
    parties: Sequence[PartyInfo],
) -> int:
    """이 클리어를 몇 인으로 나눌지 정한다.

    1. 시즌 보스는 파티 일정이 있어도 항상 1인 분배.
    2. 대상 캐릭터가 파티원에 포함된 일정이 있으면 그 일정의 인원수.
    3. 없으면 같은 보스·난이도 일정 중 첫 번째의 인원수.
    4. 아무 일정도 없으면 솔로(1인).
    """
    if is_season_boss(boss_name):
        return 1

    matching = [party for party in parties if party.matches(boss_name, difficulty)]
    if not matching:
        return 1

    if character_id is not None:
        for party in matching:
            if character_id in party.member_character_ids:
                return max(1, party.member_count)

    return max(1, matching[0].member_count)


def build_line(boss_name: str, difficulty: str, party_size: int) -> IncomeLine:
    reward = get_reward(boss_name, difficulty)
    total_meso, total_sol_erda = reward if reward is not None else (None, None)
    return IncomeLine(
        boss_name=boss_name,
        difficulty=difficulty,
        party_size=max(1, party_size),
        total_meso=total_meso,
        total_sol_erda=total_sol_erda,
    )


def calculate_income(clears: Sequence[ClearInput], parties: Sequence[PartyInfo]) -> IncomeReport:
    """클리어 기록을 모아 분배 후 수익을 합산한다.

    시세를 모르는 보스는 합계에서 빼되 항목 자체는 남긴다.
    """
    lines: list[IncomeLine] = []
    total_meso = 0
    total_sol_erda = 0

    for clear in clears:
        party_size = resolve_party_size(
            clear.boss_name, clear.difficulty, clear.character_id, parties
        )
        line = build_line(clear.boss_name, clear.difficulty, party_size)
        lines.append(line)
        if line.has_price:
            total_meso += line.share_meso
            total_sol_erda += line.share_sol_erda

    return IncomeReport(lines=tuple(lines), total_meso=total_meso, total_sol_erda=total_sol_erda)


def party_income(boss_name: str, difficulty: str, member_count: int) -> PartyIncome | None:
    """파티 일정 하나의 수익. 시세를 모르면 None."""
    reward = get_reward(boss_name, difficulty)
    if reward is None:
        return None

    total_meso, total_sol_erda = reward
    size = 1 if is_season_boss(boss_name) else max(1, member_count)
    return PartyIncome(
        boss_name=boss_name,
        difficulty=difficulty,
        member_count=size,
        total_meso=total_meso,
        total_sol_erda=total_sol_erda,
    )
