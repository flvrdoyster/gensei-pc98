"""
Compile社 PC-98 게임 공통 LZ 압축/해제 + Shift-JIS 유틸
========================================================
환세풍광전, 환세쾌도전, 환세포물장 등 동일 엔진 타이틀에서 공유.

COM 파일 시그니처: 0x100이 FC(CLD)로 시작, 0x113~0x114가 F3 A5(REP MOVSW).

LZ 코덱 자체는 compile-gfx(`compilegfx.codec.pc98lz`)로 옮겼다 — 추출용
코덱/컨테이너 지식은 그쪽에 모으고, 이 파일은 재삽입·번역 쪽 유틸만 남긴다.
아래 두 함수는 호출부 호환을 위한 얇은 위임이며, 실제 게임 청크 30개 +
랜덤/엣지케이스로 기존 구현과 바이트 단위 동일함을 확인했다.
"""

from compilegfx.codec import pc98lz


def decompress(data, start=0):
    """스트림 **하나**를 해제 (0x00 종료까지).

    `pc98lz.decompress()`가 아니라 `decompress_stream()`에 위임하는 게
    중요하다 — 전자는 파일에 이어 붙은 스트림을 전부 연결해서 돌려주므로,
    4플레인 화면(640x400)에서 32,000이 아니라 128,000바이트가 나온다.
    이 파일의 기존 호출부는 전부 단일 스트림을 가정하고 있다.
    """
    return bytearray(pc98lz.decompress_stream(data, start)[0])


def compress(data):
    """decompress()의 역함수 (DP 최적 파싱). 상세는 pc98lz.compress 참조."""
    return pc98lz.compress(data)


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

# PC-98 반각 폰트의 탁점/반탁점 합성 카나 (0x85E3~0x85FC).
# _HW_KANA(0x859F~0x85DE, idx 0~63) 뒤에 이어지는 영역으로,
# 표준 JIS X 0201 에는 없어 cp932 로는 U+FFFD 가 된다. 폰트 BMP 판독으로 확정.
_HW_DAKUTEN = {
    0xe3: 'ヴ',
    0xe4: 'ガ', 0xe5: 'ギ', 0xe6: 'グ', 0xe7: 'ゲ', 0xe8: 'ゴ',
    0xe9: 'ザ', 0xea: 'ジ', 0xeb: 'ズ', 0xec: 'ゼ', 0xed: 'ゾ',
    0xee: 'ダ', 0xef: 'ヂ', 0xf0: 'ヅ', 0xf1: 'デ', 0xf2: 'ド',
    0xf3: 'バ', 0xf4: 'パ', 0xf5: 'ビ', 0xf6: 'ピ', 0xf7: 'ブ',
    0xf8: 'プ', 0xf9: 'ベ', 0xfa: 'ペ', 0xfb: 'ボ', 0xfc: 'ポ',
}


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
            if s2 in _HW_DAKUTEN:
                return _HW_DAKUTEN[s2]
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
