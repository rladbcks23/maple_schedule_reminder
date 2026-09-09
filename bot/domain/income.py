"""결정석 수익 계산. discord 의존성 없는 순수 로직.

분배는 전부 정수 나눗셈(내림)이다. 원본 Flutter 앱과 결과가 같아야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .boss_data import get_reward, is_season_boss


@dataclass(frozen=True)
class PartyIncome:
    """보스 한 건의 총 결정석값과 1인 분배액."""

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


def party_income(boss_name: str, difficulty: str, member_count: int) -> PartyIncome | None:
    """보스 한 건의 수익. 시세를 모르면 None.

    시즌 보스는 몇 명이 가든 1인 분배로 본다.
    """
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
