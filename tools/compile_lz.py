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
        return 0x40 <= b2 <= 0xFC and b2 != 0x7F
    return False


def read_sjis_char(data, i):
    return data[i:i + 2].decode('shift_jis', errors='replace')
