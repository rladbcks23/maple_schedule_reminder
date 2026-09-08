"""파티 일정에 붙이는 짧은 식별 코드. discord 의존성 없는 순수 로직.

'SU4K' 처럼 앞 두 글자는 보스에서 따오고 뒤 두 글자는 무작위로 채운다.
보스 이니셜이 들어가면 목록에서 눈으로 훑을 때 어느 파티인지 짐작이 된다.
"""

from __future__ import annotations

import secrets
from collections.abc import Container

# 눈으로 헷갈리는 글자(O/0, I/1, L, S/5 …)는 빼서 받아적기 쉽게 만든다.
ALPHABET = "ABCDEFGHJKMNPQRTUVWXY"
DIGITS = "2346789"
BODY = ALPHABET + DIGITS

CODE_LENGTH = 4
PREFIX_LENGTH = 2
MAX_ATTEMPTS = 200

# 보스 이니셜. 없으면 로마자 음차 대신 무작위 글자를 쓴다.
BOSS_PREFIXES: dict[str, str] = {
    "발록": "BR",
    "자쿰": "ZK",
    "매그너스": "MG",
    "힐라": "HL",
    "반 레온": "VL",
    "혼테일": "HT",
    "아카이럼": "AK",
    "핑크빈": "PB",
    "시그너스": "CY",
    "카웅": "KU",
    "파풀라투스": "PP",
    "피에르": "PR",
    "반반": "VB",
    "블러디퀸": "BQ",
    "벨룸": "VM",
    "스우": "SU",
    "데미안": "DM",
    "가디언 엔젤 슬라임": "GA",
    "루시드": "LU",
    "윌": "WL",
    "더스크": "DK",
    "진 힐라": "JH",
    "듄켈": "DU",
    "검은 마법사": "BM",
    "선택받은 세렌": "SR",
    "감시자 칼로스": "KL",
    "카링": "KR",
    "림보": "LB",
    "발드릭스": "BX",
    "최초의 대적자": "FA",
    "찬란한 흉성": "RD",
    "유피테르": "JP",
    "벨로나": "BL",
    "시즌 보스 메이린": "MR",
    "메이린": "MR",
}


def normalize_code(text: str) -> str:
    """입력한 코드를 대문자로 맞추고 공백과 대괄호를 턴다."""
    return "".join(text.split()).strip("[]").upper()


def boss_prefix(boss_name: str) -> str:
    """보스에서 따온 두 글자. 모르는 보스면 무작위."""
    from .boss_data import normalize

    needle = normalize(boss_name)
    for name, prefix in BOSS_PREFIXES.items():
        if normalize(name) == needle:
            return prefix
    return "".join(secrets.choice(ALPHABET) for _ in range(PREFIX_LENGTH))


def random_suffix(length: int = CODE_LENGTH - PREFIX_LENGTH) -> str:
    return "".join(secrets.choice(BODY) for _ in range(length))


def generate_code(boss_name: str, taken: Container[str]) -> str:
    """이미 쓰인 코드를 피해 새 코드를 만든다.

    보스 접두사로 만들 수 있는 조합이 동나면 접두사까지 무작위로 돌린다.
    """
    prefix = boss_prefix(boss_name)
    for attempt in range(MAX_ATTEMPTS):
        if attempt < MAX_ATTEMPTS // 2:
            candidate = prefix + random_suffix()
        else:
            candidate = "".join(secrets.choice(BODY) for _ in range(CODE_LENGTH))
        if candidate not in taken:
            return candidate

    # 여기까지 오면 4자리가 사실상 포화된 것이므로 한 자리 늘린다.
    while True:
        candidate = prefix + random_suffix(CODE_LENGTH - PREFIX_LENGTH + 1)
        if candidate not in taken:
            return candidate
