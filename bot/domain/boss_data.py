"""보스 참조 데이터. 시세가 바뀌면 이 파일의 BOSS_REWARDS 한 곳만 고치면 된다.

다른 모듈에서는 절대 시세 숫자를 하드코딩하지 말고 여기의 조회 함수를 쓴다.
"""

from __future__ import annotations

BOSS_DIFFICULTIES: dict[str, list[str]] = {
    "발록": ["easy"],
    "자쿰": ["normal", "chaos"],
    "매그너스": ["easy", "normal", "hard"],
    "힐라": ["normal", "hard"],
    "반 레온": ["easy", "normal", "hard"],
    "혼테일": ["easy", "normal", "chaos"],
    "아카이럼": ["easy", "normal"],
    "핑크빈": ["normal", "chaos"],
    "시그너스": ["normal"],
    "카웅": ["normal"],
    "파풀라투스": ["easy", "normal", "chaos"],
    "피에르": ["normal", "chaos"],
    "반반": ["normal", "chaos"],
    "블러디퀸": ["normal", "chaos"],
    "벨룸": ["normal", "chaos"],
    "스우": ["normal", "hard", "extreme"],
    "데미안": ["normal", "hard"],
    "가디언 엔젤 슬라임": ["normal", "chaos"],
    "루시드": ["easy", "normal", "hard"],
    "윌": ["easy", "normal", "hard"],
    "더스크": ["normal", "chaos"],
    "진 힐라": ["normal", "hard"],
    "듄켈": ["normal", "hard"],
    "검은 마법사": ["hard", "extreme"],
    "선택받은 세렌": ["normal", "hard", "extreme"],
    "감시자 칼로스": ["easy", "normal", "chaos", "extreme"],
    "카링": ["easy", "normal", "hard", "extreme"],
    "림보": ["normal", "hard"],
    "발드릭스": ["normal", "hard"],
    "최초의 대적자": ["easy", "normal", "hard", "extreme"],
    "찬란한 흉성": ["normal", "hard"],
    "유피테르": ["normal", "hard"],
    "벨로나": ["easy", "normal", "hard"],
    "시즌 보스 메이린": ["normal", "hard"],
}

# 파티 등록 autocomplete에서 위쪽에 먼저 노출할 순서 (상위 보스 먼저).
BOSS_PRIORITY_ORDER: list[str] = [
    "벨로나",
    "유피테르",
    "찬란한 흉성",
    "최초의 대적자",
    "발드릭스",
    "림보",
    "카링",
    "감시자 칼로스",
    "선택받은 세렌",
    "검은 마법사",
    "시즌 보스 메이린",
    "듄켈",
    "진 힐라",
    "더스크",
    "윌",
    "루시드",
    "가디언 엔젤 슬라임",
    "데미안",
    "스우",
    "벨룸",
    "블러디퀸",
    "반반",
    "피에르",
    "파풀라투스",
    "카웅",
    "시그너스",
    "핑크빈",
    "아카이럼",
    "혼테일",
    "반 레온",
    "힐라",
    "매그너스",
    "자쿰",
    "발록",
]

# (보스명, 난이도) -> (결정석 메소, 솔 에르다 기운)
BOSS_REWARDS: dict[tuple[str, str], tuple[int, int]] = {
    ("발록", "easy"): (0, 0),
    ("반 레온", "easy"): (602_000, 0),
    ("반 레온", "normal"): (830_000, 0),
    ("반 레온", "hard"): (1_070_000, 0),
    ("혼테일", "easy"): (502_000, 0),
    ("혼테일", "normal"): (576_000, 0),
    ("혼테일", "chaos"): (770_000, 0),
    ("아카이럼", "easy"): (656_000, 0),
    ("아카이럼", "normal"): (1_110_000, 0),
    ("핑크빈", "normal"): (799_000, 0),
    ("핑크빈", "chaos"): (1_320_000, 0),
    ("시그너스", "normal"): (1_360_000, 0),
    ("자쿰", "normal"): (354_800, 0),
    ("자쿰", "chaos"): (8_080_000, 0),
    ("매그너스", "easy"): (418_300, 0),
    ("매그너스", "normal"): (1_160_000, 0),
    ("매그너스", "hard"): (8_560_000, 0),
    ("힐라", "normal"): (463_500, 0),
    ("힐라", "hard"): (1_280_000, 0),
    ("카웅", "normal"): (1_250_000, 0),
    ("파풀라투스", "easy"): (396_500, 0),
    ("파풀라투스", "normal"): (1_200_000, 0),
    ("파풀라투스", "chaos"): (13_100_000, 0),
    ("피에르", "normal"): (968_000, 0),
    ("피에르", "chaos"): (8_170_000, 0),
    ("반반", "normal"): (968_000, 0),
    ("반반", "chaos"): (8_150_000, 0),
    ("블러디퀸", "normal"): (968_000, 0),
    ("블러디퀸", "chaos"): (8_140_000, 0),
    ("벨룸", "normal"): (968_000, 0),
    ("벨룸", "chaos"): (9_280_000, 0),
    ("스우", "normal"): (16_700_000, 0),
    ("스우", "hard"): (51_500_000, 40),
    ("스우", "extreme"): (574_000_000, 400),
    ("데미안", "normal"): (17_500_000, 0),
    ("데미안", "hard"): (48_900_000, 40),
    ("가디언 엔젤 슬라임", "normal"): (25_500_000, 0),
    ("가디언 엔젤 슬라임", "chaos"): (75_100_000, 60),
    ("루시드", "easy"): (29_800_000, 0),
    ("루시드", "normal"): (35_600_000, 40),
    ("루시드", "hard"): (62_900_000, 70),
    ("윌", "easy"): (32_300_000, 0),
    ("윌", "normal"): (41_100_000, 50),
    ("윌", "hard"): (77_100_000, 80),
    ("더스크", "normal"): (44_000_000, 45),
    ("더스크", "chaos"): (69_800_000, 90),
    ("진 힐라", "normal"): (71_200_000, 50),
    ("진 힐라", "hard"): (106_000_000, 100),
    ("듄켈", "normal"): (47_500_000, 50),
    ("듄켈", "hard"): (94_400_000, 90),
    ("검은 마법사", "hard"): (665_000_000, 250),
    ("검은 마법사", "extreme"): (8_740_000_000, 1000),
    ("선택받은 세렌", "normal"): (239_000_000, 120),
    ("선택받은 세렌", "hard"): (356_000_000, 220),
    ("선택받은 세렌", "extreme"): (2_835_000_000, 600),
    ("감시자 칼로스", "easy"): (280_000_000, 140),
    ("감시자 칼로스", "normal"): (505_000_000, 240),
    ("감시자 칼로스", "chaos"): (1_273_000_000, 420),
    ("감시자 칼로스", "extreme"): (4_104_000_000, 650),
    ("카링", "easy"): (377_000_000, 160),
    ("카링", "normal"): (678_000_000, 260),
    ("카링", "hard"): (1_739_000_000, 500),
    ("카링", "extreme"): (5_387_000_000, 800),
    ("림보", "normal"): (1_026_000_000, 420),
    ("림보", "hard"): (2_385_000_000, 750),
    ("발드릭스", "normal"): (1_368_000_000, 500),
    ("발드릭스", "hard"): (3_078_000_000, 900),
    ("시즌 보스 메이린", "normal"): (300_000_000, 400),
    ("시즌 보스 메이린", "hard"): (600_000_000, 550),
    ("메이린", "normal"): (300_000_000, 400),
    ("메이린", "hard"): (600_000_000, 550),
    ("최초의 대적자", "easy"): (308_000_000, 0),
    ("최초의 대적자", "normal"): (560_000_000, 0),
    ("최초의 대적자", "hard"): (1_435_000_000, 0),
    ("최초의 대적자", "extreme"): (4_712_000_000, 0),
    ("찬란한 흉성", "normal"): (625_000_000, 0),
    ("찬란한 흉성", "hard"): (2_678_000_000, 0),
    ("유피테르", "normal"): (1_615_000_000, 0),
    ("유피테르", "hard"): (4_845_000_000, 0),
    ("벨로나", "easy"): (440_000_000, 200),
    ("벨로나", "normal"): (890_000_000, 290),
    ("벨로나", "hard"): (2_950_000_000, 590),
}

DIFFICULTIES = ("easy", "normal", "hard", "chaos", "extreme")

DIFFICULTY_ALIASES: dict[str, str] = {
    "이지": "easy",
    "노멀": "normal",
    "노말": "normal",
    "하드": "hard",
    "카오스": "chaos",
    "익스트림": "extreme",
}

DIFFICULTY_KO: dict[str, str] = {
    "easy": "이지",
    "normal": "노멀",
    "hard": "하드",
    "chaos": "카오스",
    "extreme": "익스트림",
}

# 월간 리셋을 따르는 보스. 나머지는 전부 주간이다.
MONTHLY_BOSSES = frozenset({"검은 마법사"})

# 시즌 보스는 파티 일정이 있어도 항상 1인 분배로 본다.
SEASON_BOSS_MARKERS = ("시즌보스", "메이린")


def normalize(text: str) -> str:
    """공백을 모두 제거하고 소문자로. '반 레온' -> '반레온'"""
    return "".join(text.split()).lower()


def normalize_difficulty(difficulty: str) -> str:
    """한글 난이도를 영문으로. 이미 영문이면 소문자로만 정리한다."""
    cleaned = normalize(difficulty)
    return DIFFICULTY_ALIASES.get(cleaned, cleaned)


def reward_key(boss_name: str, difficulty: str) -> str:
    """시세 테이블 조회 키. '보스#난이도' 형태."""
    return f"{normalize(boss_name)}#{normalize_difficulty(difficulty)}"


REWARD_TABLE: dict[str, tuple[int, int]] = {
    reward_key(boss, difficulty): reward for (boss, difficulty), reward in BOSS_REWARDS.items()
}


def get_reward(boss_name: str, difficulty: str) -> tuple[int, int] | None:
    """(결정석 메소, 솔 에르다 기운). 시세 정보가 없으면 None."""
    return REWARD_TABLE.get(reward_key(boss_name, difficulty))


def is_season_boss(boss_name: str) -> bool:
    normalized = normalize(boss_name)
    return any(marker in normalized for marker in SEASON_BOSS_MARKERS)


def is_monthly_boss(boss_name: str) -> bool:
    normalized = normalize(boss_name)
    return any(normalize(name) == normalized for name in MONTHLY_BOSSES)


def canonical_boss_name(boss_name: str) -> str | None:
    """입력한 이름과 정규화 결과가 같은 정식 보스명을 찾는다."""
    normalized = normalize(boss_name)
    for name in BOSS_DIFFICULTIES:
        if normalize(name) == normalized:
            return name
    return None


def difficulties_for(boss_name: str) -> list[str]:
    """해당 보스에 실제로 존재하는 난이도 목록. 모르는 보스면 빈 리스트."""
    canonical = canonical_boss_name(boss_name)
    return list(BOSS_DIFFICULTIES.get(canonical, [])) if canonical else []


def ordered_boss_names() -> list[str]:
    """autocomplete 노출 순서. 우선순위 목록이 앞, 나머지는 뒤에 붙인다."""
    ordered = [name for name in BOSS_PRIORITY_ORDER if name in BOSS_DIFFICULTIES]
    rest = [name for name in BOSS_DIFFICULTIES if name not in ordered]
    return ordered + rest


def search_boss_names(query: str, limit: int = 25) -> list[str]:
    """공백을 무시한 부분 일치 검색. 노출 순서를 유지한다."""
    needle = normalize(query)
    names = ordered_boss_names()
    if not needle:
        return names[:limit]
    return [name for name in names if needle in normalize(name)][:limit]
