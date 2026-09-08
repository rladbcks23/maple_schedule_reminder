import pytest

from bot.domain.formatting import difficulty_ko, difficulty_tag, format_meso, format_sol_erda


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "-"),
        (-1, "-"),
        (-123_456, "-"),
        (9_999, "9999"),
        (10_000, "1만"),
        (100_000_000, "1억"),
        (123_450_000, "1억 2345만"),
    ],
)
def test_format_meso_spec_cases(value, expected):
    assert format_meso(value) == expected


def test_format_meso_drops_change_under_ten_thousand():
    # 만 미만 잔돈은 버린다.
    assert format_meso(12_875_000) == "1287만"
    assert format_meso(100_009_999) == "1억"


def test_format_meso_keeps_raw_number_under_ten_thousand():
    assert format_meso(1) == "1"
    assert format_meso(354) == "354"


def test_format_sol_erda():
    assert format_sol_erda(0) == "-"
    assert format_sol_erda(-5) == "-"
    assert format_sol_erda(250) == "250기운"


def test_difficulty_labels():
    assert difficulty_ko("hard") == "하드"
    assert difficulty_ko("chaos") == "카오스"
    assert difficulty_ko("모름") == "모름"
    assert difficulty_tag("hard") == "HARD"
