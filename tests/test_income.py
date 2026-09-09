from bot.domain.income import party_income

SUU_HARD_MESO = 51_500_000
SUU_HARD_SOL = 40


def test_solo_keeps_full_reward():
    result = party_income("스우", "hard", 1)
    assert result is not None
    assert result.total_meso == SUU_HARD_MESO
    assert result.share_meso == SUU_HARD_MESO
    assert result.share_sol_erda == SUU_HARD_SOL


def test_party_splits_by_member_count_with_floor_division():
    result = party_income("스우", "hard", 4)
    assert result.total_meso == SUU_HARD_MESO
    assert result.share_meso == SUU_HARD_MESO // 4
    assert result.total_sol_erda == SUU_HARD_SOL
    assert result.share_sol_erda == SUU_HARD_SOL // 4


def test_korean_difficulty_is_normalized():
    assert party_income("스우", "하드", 1).total_meso == SUU_HARD_MESO


def test_boss_name_spacing_is_ignored():
    # 이름은 넣은 그대로 담기지만 시세는 같은 값을 찾아야 한다.
    붙임 = party_income("반레온", "hard", 1)
    띄움 = party_income("반 레온", "hard", 1)
    assert 붙임 is not None and 띄움 is not None
    assert 붙임.total_meso == 띄움.total_meso == 1_070_000


def test_season_boss_is_always_solo_share():
    # 시즌 보스는 6인이 가도 나누지 않는다.
    result = party_income("시즌 보스 메이린", "hard", 6)
    assert result.member_count == 1
    assert result.share_meso == 600_000_000
    assert party_income("메이린", "hard", 6).share_meso == 600_000_000


def test_zero_reward_boss_is_known_not_missing():
    # 발록 easy는 시세가 0으로 '알려진' 값이다. 정보 없음과 구분해야 한다.
    result = party_income("발록", "easy", 1)
    assert result is not None
    assert result.total_meso == 0


def test_unknown_boss_returns_none():
    assert party_income("아무개", "normal", 4) is None


def test_unknown_difficulty_returns_none():
    # 스우에는 카오스가 없다.
    assert party_income("스우", "chaos", 1) is None


def test_member_count_is_clamped_to_at_least_one():
    assert party_income("스우", "hard", 0).member_count == 1
