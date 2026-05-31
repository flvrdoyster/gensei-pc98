"""
Compile社 PC-98 게임 공통 LZ 압축/해제 + Shift-JIS 유틸
========================================================
환세풍광전, 환세쾌도전, 환세포물장 등 동일 엔진 타이틀에서 공유.

COM 파일 시그니처: 0x100이 FC(CLD)로 시작, 0x113~0x114가 F3 A5(REP MOVSW).
"""


# ─────────────────────────────────────
# LZ 압축 해제
# ─────────────────────────────────────

def decompress(data, start=0):
    """
    al = *src++
    if al == 0: 종료
    if al & 0x80: back-reference (length = (al & 0x7f) + 3, offset = *src++ + 1)
    else: literal copy (length = al)
    """
    output = bytearray()
    i = start
    while i < len(data):
        al = data[i]; i += 1
        if al == 0:
            break
        if al & 0x80:
            length = (al & 0x7f) + 3
            if i >= len(data):
                break
            offset = data[i] + 1; i += 1
            for _ in range(length):
                pos = len(output) - offset
                output.append(output[pos] if pos >= 0 else 0)
        else:
            length = al
            output.extend(data[i:i + length])
            i += length
    return output


# ─────────────────────────────────────
# LZ 압축
# ─────────────────────────────────────

def _find_match(data, i):
    """위치 i에서 최장 매치 (length, dist). 매치 없으면 (0, 0)."""
    best_len = 0
    best_dist = 0
    max_dist = min(i, 256)
    max_len = min(len(data) - i, 130)
    for dist in range(1, max_dist + 1):
        ml = 0
        while ml < max_len and data[i + ml] == data[i - dist + (ml % dist)]:
            ml += 1
        if ml > best_len:
            best_len = ml
            best_dist = dist
    return best_len, best_dist


def compress(data):
    """
    decompress()의 역함수. Optimal parsing (DP).
    윈도우: 256바이트, 매치 길이: 3~130, 리터럴 런: 1~127.

    각 위치에서 literal vs match 중 minimum-cost 선택을 DP 로 결정.
    Literal run 헤더 오버헤드까지 정확히 모델링.
    """
    n = len(data)
    if n == 0:
        return b'\x00'

    # dp[i] = data[i:] 압축 minimum cost (terminator 제외)
    # decision[i] = ('lit',) or ('match', length, dist)
    INF = float('inf')
    dp = [INF] * (n + 1)
    decision = [None] * n
    dp[n] = 0

    # 뒤에서 앞으로
    for i in range(n - 1, -1, -1):
        # 옵션 1: literal run of length L (L = 1..min(127, n-i))
        # cost = 1 (header) + L + dp[i+L]
        max_run = min(127, n - i)
        for L in range(1, max_run + 1):
            cost = 1 + L + dp[i + L]
            if cost < dp[i]:
                dp[i] = cost
                decision[i] = ('lit', L)

        # 옵션 2: match length k (k = 3..min(130, n-i)), 가장 짧은 dist
        max_dist = min(i, 256)
        max_len = min(n - i, 130)
        best_len_for_dist = {}
        for dist in range(1, max_dist + 1):
            ml = 0
            while ml < max_len and data[i + ml] == data[i - dist + (ml % dist)]:
                ml += 1
            # 모든 길이 k (3..ml) 에 대해 가장 작은 dist 만 기록
            for k in range(3, ml + 1):
                if k not in best_len_for_dist:
                    best_len_for_dist[k] = dist

        for k, dist in best_len_for_dist.items():
            cost = 2 + dp[i + k]
            if cost < dp[i]:
                dp[i] = cost
                decision[i] = ('match', k, dist)

    # Decision 따라 emit
    result = bytearray()
    i = 0
    while i < n:
        d = decision[i]
        if d[0] == 'lit':
            L = d[1]
            result.append(L)
            result.extend(data[i:i + L])
            i += L
        else:
            _, k, dist = d
            result.append(0x80 | (k - 3))
            result.append(dist - 1)
            i += k

    result.append(0x00)
    return bytes(result)


# ─────────────────────────────────────
# Shift-JIS 유틸
# ─────────────────────────────────────

def is_sjis_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def is_sjis(data, i):
    if i + 1 >= len(data):
        return False
    b = data[i]
    if is_sjis_lead(b):
        b2 = data[i + 1]
        if not (0x40 <= b2 <= 0xFC and b2 != 0x7F):
            return False
        if b == 0x85:
            return True  # 반각 영역 — read_sjis_char에서 별도 디코딩
        try:
            data[i:i + 2].decode('shift_jis')
            return True
        except (UnicodeDecodeError, ValueError):
            return False
    return False


_HW_KANA = (
    '。「」、・ヲァィゥェォャュョッ'
    'ーアイウエオカキクケコサシスセソ'
    'タチツテトナニヌネノハヒフヘホマ'
    'ミムメモヤユヨラリルレロワン゛゜'
)


def read_sjis_char(data, i):
    s1, s2 = data[i], data[i + 1]
    if s1 == 0x85:
        if s2 < 0x9F:
            j2 = (s2 - 0x1F) if s2 < 0x80 else (s2 - 0x20)
            return chr(j2)
        else:
            j2 = s2 - 0x7E
            idx = j2 - 0x21
            if 0 <= idx < len(_HW_KANA):
                return _HW_KANA[idx]
    return data[i:i + 2].decode('shift_jis', errors='replace')


_HALFWIDTH_REV = {}


def _build_halfwidth_rev():
    if _HALFWIDTH_REV:
        return
    for code in range(0x21, 0x7F):
        if code < 0x80:
            s2 = code + 0x1F
        else:
            s2 = code + 0x20
        sjis = (0x85 << 8) | s2
        _HALFWIDTH_REV[chr(code)] = bytes([0x85, s2])
    for idx, ch in enumerate(_HW_KANA):
        j2 = idx + 0x21
        s2 = j2 + 0x7E
        _HALFWIDTH_REV[ch] = bytes([0x85, s2])


def encode_halfwidth_char(ch):
    _build_halfwidth_rev()
    return _HALFWIDTH_REV.get(ch)
