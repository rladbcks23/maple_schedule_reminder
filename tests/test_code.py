from bot.domain.boss_data import BOSS_DIFFICULTIES
from bot.domain.code import (
    ALPHABET,
    BODY,
    BOSS_PREFIXES,
    CODE_LENGTH,
    boss_prefix,
    generate_code,
    normalize_code,
)


def test_every_boss_has_a_prefix():
    missing = [name for name in BOSS_DIFFICULTIES if name not in BOSS_PREFIXES]
    assert missing == []


def test_prefixes_are_unique_per_boss():
    # 접두사가 겹치면 목록에서 보스를 짐작하기 어려워진다. '메이린'은 별칭이라 뺀다.
    prefixes = [prefix for name, prefix in BOSS_PREFIXES.items() if name != "메이린"]
    assert len(prefixes) == len(set(prefixes))


def test_boss_prefix_ignores_spacing():
    assert boss_prefix("반 레온") == "VL"
    assert boss_prefix("반레온") == "VL"
    assert boss_prefix("검은 마법사") == "BM"


def test_boss_prefix_falls_back_for_unknown_boss():
    prefix = boss_prefix("듣보보스")
    assert len(prefix) == 2
    assert all(character in ALPHABET for character in prefix)


def test_generated_code_starts_with_boss_prefix():
    code = generate_code("스우", taken=set())
    assert code.startswith("SU")
    assert len(code) == CODE_LENGTH


def test_generated_code_uses_safe_alphabet_only():
    # 0/O, 1/I 처럼 헷갈리는 글자가 섞이면 받아적다 틀린다.
    for _ in range(200):
        code = generate_code("카링", taken=set())
        assert all(character in BODY for character in code)
    assert "O" not in BODY and "0" not in BODY
    assert "I" not in BODY and "1" not in BODY


def test_generated_code_avoids_taken_codes():
    taken = set()
    for _ in range(50):
        code = generate_code("스우", taken)
        assert code not in taken
        taken.add(code)
    assert len(taken) == 50


def test_generate_code_survives_exhausted_prefix():
    # 'SU' 로 시작하는 조합을 전부 막아도 코드를 만들어낸다.
    taken = {f"SU{a}{b}" for a in BODY for b in BODY}
    code = generate_code("스우", taken)
    assert code not in taken


def test_normalize_code():
    assert normalize_code("su4k") == "SU4K"
    assert normalize_code(" SU4K ") == "SU4K"
    assert normalize_code("[SU4K]") == "SU4K"
    assert normalize_code("su 4k") == "SU4K"
