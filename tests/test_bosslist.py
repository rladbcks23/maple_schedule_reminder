from bot.domain.bosslist import BossEntry, parse_boss_list


def only(text):
    entries, errors = parse_boss_list(text)
    assert errors == [], errors
    return entries


def test_single_entry_defaults_to_solo():
    assert only("노말 스우") == [BossEntry("스우", "normal", 1)]


def test_entry_with_party_size():
    assert only("노말 스우 3") == [BossEntry("스우", "normal", 3)]


def test_multiple_entries():
    assert only("노말 스우 3, 노말 진 힐라 4") == [
        BossEntry("스우", "normal", 3),
        BossEntry("진 힐라", "normal", 4),
    ]


def test_boss_name_with_spaces():
    # 난이도와 인원을 떼어내면 가운데가 곧 보스명이다.
    assert only("하드 반 레온 2") == [BossEntry("반 레온", "hard", 2)]
    assert only("익스트림 선택받은 세렌 6") == [BossEntry("선택받은 세렌", "extreme", 6)]


def test_difficulty_aliases():
    assert only("노멀 스우")[0].difficulty == "normal"
    assert only("노말 스우")[0].difficulty == "normal"
    assert only("hard 스우")[0].difficulty == "hard"
    assert only("카오스 자쿰")[0].difficulty == "chaos"


def test_extra_whitespace_and_empty_items():
    assert only("  노말 스우 3 ,, 하드 카링  ") == [
        BossEntry("스우", "normal", 3),
        BossEntry("카링", "hard", 1),
    ]


def test_empty_input():
    assert parse_boss_list("") == ([], [])
    assert parse_boss_list("  ,  ") == ([], [])


# --- 잘못된 입력 ---------------------------------------------------------------


def test_missing_difficulty_is_reported():
    entries, errors = parse_boss_list("스우")
    assert entries == []
    assert len(errors) == 1 and "난이도가 없습니다" in errors[0]


def test_unknown_difficulty_is_reported():
    entries, errors = parse_boss_list("초하드 스우")
    assert entries == []
    assert len(errors) == 1 and "난이도가 아닙니다" in errors[0]


def test_unknown_boss_is_reported():
    entries, errors = parse_boss_list("노말 아무개")
    assert entries == []
    assert len(errors) == 1 and "등록된 보스가 아닙니다" in errors[0]


def test_difficulty_the_boss_does_not_have_is_reported():
    # 스우에는 카오스가 없다.
    entries, errors = parse_boss_list("카오스 스우")
    assert entries == []
    assert len(errors) == 1 and "만 있습니다" in errors[0]


def test_party_size_out_of_range_is_reported():
    entries, errors = parse_boss_list("노말 스우 9")
    assert entries == []
    assert len(errors) == 1 and "1~6" in errors[0]


def test_bad_item_does_not_drop_the_good_ones():
    entries, errors = parse_boss_list("노말 스우 3, 노말 아무개, 하드 카링")
    assert entries == [BossEntry("스우", "normal", 3), BossEntry("카링", "hard", 1)]
    assert len(errors) == 1
