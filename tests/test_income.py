from bot.domain.income import (
    ClearInput,
    PartyInfo,
    calculate_income,
    party_income,
    resolve_party_size,
)

SUU_HARD_MESO = 51_500_000
SUU_HARD_SOL = 40


def party(boss, difficulty, count, members=()):
    return PartyInfo(
        boss_name=boss,
        difficulty=difficulty,
        member_count=count,
        member_character_ids=frozenset(members),
    )


# --- 분배 인원수 결정 ---------------------------------------------------------


def test_party_size_uses_schedule_containing_the_character():
    parties = [
        party("스우", "hard", 6, members=[10, 11, 12, 13, 14, 15]),
        party("스우", "hard", 4, members=[1, 2, 3, 4]),
    ]
    assert resolve_party_size("스우", "hard", 1, parties) == 4


def test_party_size_falls_back_to_first_matching_schedule():
    parties = [party("스우", "hard", 4, members=[1, 2, 3, 4])]
    assert resolve_party_size("스우", "hard", 99, parties) == 4


def test_party_size_is_one_when_no_schedule_exists():
    assert resolve_party_size("스우", "hard", 1, []) == 1


def test_party_size_matches_on_normalized_names():
    # '반 레온' -> '반레온'. 공백 차이로 매칭이 깨지면 안 된다.
    parties = [party("반레온", "HARD", 3, members=[1])]
    assert resolve_party_size("반 레온", "hard", 1, parties) == 3


def test_party_size_ignores_other_bosses_and_difficulties():
    parties = [party("스우", "normal", 4, members=[1]), party("데미안", "hard", 5, members=[1])]
    assert resolve_party_size("스우", "hard", 1, parties) == 1


def test_season_boss_is_always_solo_share():
    parties = [party("시즌 보스 메이린", "hard", 6, members=[1, 2, 3, 4, 5, 6])]
    assert resolve_party_size("시즌 보스 메이린", "hard", 1, parties) == 1
    assert resolve_party_size("메이린", "hard", 1, parties) == 1


# --- 수익 계산 ----------------------------------------------------------------


def test_four_member_hard_suu_uses_floor_division():
    parties = [party("스우", "hard", 4, members=[1, 2, 3, 4])]
    report = calculate_income([ClearInput("스우", "hard", 1)], parties)

    assert report.total_meso == SUU_HARD_MESO // 4
    assert report.total_sol_erda == SUU_HARD_SOL // 4
    assert len(report.lines) == 1
    assert report.lines[0].render() == "HARD 스우: 1287만 / 4인 분배"


def test_solo_clear_keeps_full_reward():
    report = calculate_income([ClearInput("스우", "hard", 1)], [])
    assert report.total_meso == SUU_HARD_MESO
    assert report.total_sol_erda == SUU_HARD_SOL
    assert report.lines[0].render() == "HARD 스우: 5150만 / 1인 분배"


def test_season_boss_income_is_not_divided():
    parties = [party("시즌 보스 메이린", "hard", 6, members=[1, 2, 3, 4, 5, 6])]
    report = calculate_income([ClearInput("시즌 보스 메이린", "hard", 1)], parties)
    assert report.total_meso == 600_000_000
    assert report.total_sol_erda == 550


def test_multiple_clears_are_summed():
    parties = [party("스우", "hard", 4, members=[1, 2, 3, 4])]
    report = calculate_income(
        [ClearInput("스우", "hard", 1), ClearInput("데미안", "hard", 1)], parties
    )
    assert report.total_meso == SUU_HARD_MESO // 4 + 48_900_000
    assert report.total_sol_erda == SUU_HARD_SOL // 4 + 40


def test_missing_price_is_excluded_from_total_but_kept_in_lines():
    report = calculate_income(
        [ClearInput("스우", "hard", 1), ClearInput("아무개", "normal", 1)], []
    )
    assert report.total_meso == SUU_HARD_MESO
    assert len(report.lines) == 2

    missing = report.missing_lines
    assert len(missing) == 1
    assert missing[0].boss_name == "아무개"
    assert missing[0].render() == "NORMAL 아무개: 시세 정보 없음"


def test_korean_difficulty_is_normalized():
    report = calculate_income([ClearInput("스우", "하드", 1)], [])
    assert report.total_meso == SUU_HARD_MESO


def test_zero_reward_boss_is_not_treated_as_missing():
    # 발록 easy는 시세가 0으로 '알려진' 값이다. 정보 없음과 구분해야 한다.
    report = calculate_income([ClearInput("발록", "easy", 1)], [])
    assert report.total_meso == 0
    assert report.missing_lines == []


# --- 파티 단위 수익 ------------------------------------------------------------


def test_party_income_splits_total_by_member_count():
    result = party_income("스우", "hard", 4)
    assert result is not None
    assert result.total_meso == SUU_HARD_MESO
    assert result.share_meso == SUU_HARD_MESO // 4
    assert result.total_sol_erda == SUU_HARD_SOL
    assert result.share_sol_erda == SUU_HARD_SOL // 4


def test_party_income_treats_season_boss_as_solo():
    result = party_income("시즌 보스 메이린", "hard", 6)
    assert result is not None
    assert result.share_meso == 600_000_000


def test_party_income_returns_none_without_price():
    assert party_income("아무개", "normal", 4) is None
