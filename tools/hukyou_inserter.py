"""
환세풍광전 번역 재삽입 스크립트
================================

사용법:
  python3 hukyou_inserter.py <game_dir>

동작:
  1. translation/<title>/translation.json 로드
  2. 원본 CMD 파일 압축 해제
  3. 각 오프셋에서 JP 텍스트를 KR로 교체 (charmap.json 기반 인코딩)
  4. LZ 재압축
  5. build/<title>/ 에 패치된 CMD 저장
"""

import json
import os
import sys

from compile_lz import decompress, compress, encode_gaiji_char


def load_charmap():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charmap.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


ASCII_TO_FULLWIDTH = {
    ' ': b'\x81\x40',  #
    '.': b'\x81\x44',  # ．
    ',': b'\x81\x43',  # ，
    '!': b'\x81\x49',  # ！
    '?': b'\x81\x48',  # ？
    '(': b'\x81\x69',  # （
    ')': b'\x81\x6A',  # ）
    '+': b'\x81\x7B',  # ＋
    '=': b'\x81\x81',  # ＝
    '~': b'\x81\x60',  # ～ (Python shift_jis 코덱 미지원으로 직접 지정)
    '∼': b'\x81\x60',  # U+223C TILDE OPERATOR → ～
    '·': b'\x81\x45',  # U+00B7 MIDDLE DOT → ・
    'ĸ': b'\x81\x40',  # U+0138 KR 인코딩 잔여 → 전각 공백
    '￠': b'\x81\x40',  # U+FFE0 KR 인코딩 잔여 → 전각 공백
    '￡': b'\x81\x40',  # U+FFE1 KR 인코딩 잔여 → 전각 공백
    '∴': b'\x81\x45',  # U+2234 THEREFORE → ・
    '-': b'\x81\x7C',  # ー
    # 반각 숫자·영문 → 전각 (게임 렌더러가 1바이트 ASCII를 표시하지 못함)
    '0': b'\x82\x4F',  # ０
    '1': b'\x82\x50',  # １
    '2': b'\x82\x51',  # ２
    '3': b'\x82\x52',  # ３
    '4': b'\x82\x53',  # ４
    '5': b'\x82\x54',  # ５
    '6': b'\x82\x55',  # ６
    '7': b'\x82\x56',  # ７
    '8': b'\x82\x57',  # ８
    '9': b'\x82\x58',  # ９
    'A': b'\x82\x60',  # Ａ
    'B': b'\x82\x61',  # Ｂ
    'C': b'\x82\x62',  # Ｃ
    'D': b'\x82\x63',  # Ｄ
    'E': b'\x82\x64',  # Ｅ
    'F': b'\x82\x65',  # Ｆ
    'G': b'\x82\x66',  # Ｇ
    'H': b'\x82\x67',  # Ｈ
    'I': b'\x82\x68',  # Ｉ
    'J': b'\x82\x69',  # Ｊ
    'K': b'\x82\x6A',  # Ｋ
    'L': b'\x82\x6B',  # Ｌ
    'M': b'\x82\x6C',  # Ｍ
    'N': b'\x82\x6D',  # Ｎ
    'O': b'\x82\x6E',  # Ｏ
    'P': b'\x82\x6F',  # Ｐ
    'Q': b'\x82\x70',  # Ｑ
    'R': b'\x82\x71',  # Ｒ
    'S': b'\x82\x72',  # Ｓ
    'T': b'\x82\x73',  # Ｔ
    'U': b'\x82\x74',  # Ｕ
    'V': b'\x82\x75',  # Ｖ
    'W': b'\x82\x76',  # Ｗ
    'X': b'\x82\x77',  # Ｘ
    'Y': b'\x82\x78',  # Ｙ
    'Z': b'\x82\x79',  # Ｚ
    'a': b'\x82\x81',  # ａ
    'b': b'\x82\x82',  # ｂ
    'c': b'\x82\x83',  # ｃ
    'd': b'\x82\x84',  # ｄ
    'e': b'\x82\x85',  # ｅ
    'f': b'\x82\x86',  # ｆ
    'g': b'\x82\x87',  # ｇ
    'h': b'\x82\x88',  # ｈ
    'i': b'\x82\x89',  # ｉ
    'j': b'\x82\x8A',  # ｊ
    'k': b'\x82\x8B',  # ｋ
    'l': b'\x82\x8C',  # ｌ
    'm': b'\x82\x8D',  # ｍ
    'n': b'\x82\x8E',  # ｎ
    'o': b'\x82\x8F',  # ｏ
    'p': b'\x82\x90',  # ｐ
    'q': b'\x82\x91',  # ｑ
    'r': b'\x82\x92',  # ｒ
    's': b'\x82\x93',  # ｓ
    't': b'\x82\x94',  # ｔ
    'u': b'\x82\x95',  # ｕ
    'v': b'\x82\x96',  # ｖ
    'w': b'\x82\x97',  # ｗ
    'x': b'\x82\x98',  # ｘ
    'y': b'\x82\x99',  # ｙ
    'z': b'\x82\x9A',  # ｚ
}


def encode_korean(text, charmap, use_gaiji=False):
    """한국어 텍스트를 SJIS 바이트로 인코딩. 한글은 charmap, 나머지는 SJIS."""
    result = bytearray()
    for ch in text:
        if ch in charmap:
            code = charmap[ch]
            result.append(int(code[:2], 16))
            result.append(int(code[2:], 16))
        elif use_gaiji and encode_gaiji_char(ch):
            result.extend(encode_gaiji_char(ch))
        elif ch in ASCII_TO_FULLWIDTH:
            result.extend(ASCII_TO_FULLWIDTH[ch])
        else:
            encoded = ch.encode('shift_jis', errors='strict')
            result.extend(encoded)
    return bytes(result)


FULLWIDTH_SPACE = b'\x81\x40'


def fit_length(old_bytes, new_bytes, context=''):
    """new_bytes를 old_bytes와 동일한 길이로 맞춤. 짧으면 전각 공백 패딩, 길면 뒤에서 자름."""
    diff = len(old_bytes) - len(new_bytes)
    if diff == 0:
        return new_bytes
    if diff > 0:
        pad = FULLWIDTH_SPACE * (diff // 2)
        if diff % 2 == 1:
            pad += b'\x20'
        return new_bytes + pad
    overflow = len(new_bytes) - len(old_bytes)
    print(f'  ⚠ {overflow}바이트 초과, 잘림: {context}')
    target = len(old_bytes)
    cut = new_bytes[:target]
    if target >= 1 and is_sjis_lead_byte(cut[-1]):
        cut = cut[:-1] + b'\x20'
    return cut


def is_sjis_lead_byte(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def collect_replacements(translation, charmap):
    """translation.json에서 파일별 교체 목록 생성. 바이트 길이 자동 맞춤."""
    by_file = {}

    def add(fname, offset, jp, kr, jp_len=None):
        if not kr:
            return
        try:
            old = jp.encode('shift_jis')
            # jp_len과 실제 인코딩 길이가 다르면 가이지 불완전 디코딩 → 길이 기반으로 전환
            if jp_len is not None and len(old) != jp_len:
                raise ValueError
            new = encode_korean(kr, charmap)
            new = fit_length(old, new, context=f'{fname} 0x{offset:X}: {kr}')
            by_file.setdefault(fname, []).append((offset, old, new))
        except (UnicodeEncodeError, ValueError):
            # 가이지 등 round-trip 불가 문자 포함 → 가이지 인코딩 + jp_len 기반 교체
            length = jp_len if jp_len is not None else len(jp.encode('shift_jis', errors='replace'))
            new = encode_korean(kr, charmap, use_gaiji=True)
            new = fit_length(b'\x00' * length, new, context=f'{fname} 0x{offset:X}: {kr}')
            by_file.setdefault(fname, []).append((offset, length, new))

    def add_ui(fname, offset, jp_len, kr):
        if not kr:
            return
        new = encode_korean(kr, charmap, use_gaiji=True)
        new = fit_length(b'\x00' * jp_len, new, context=f'{fname} 0x{offset:X}: {kr}')
        by_file.setdefault(fname, []).append((offset, jp_len, new))

    for dialog in translation['dialogs']:
        fname = dialog['file']
        for line in dialog['lines']:
            if line.get('tag') == 'ignore':
                continue  # 제외 태그는 패치 안 함 (KR 남아있어도 무시)
            add(fname, line['offset'], line['jp'], line['kr'],
                jp_len=line.get('jp_len'))

    for item in translation.get('items', []):
        fname = 'MESSAGE.CMD'
        n = item['name']
        add(fname, n['offset'], n['jp'], n['kr'], jp_len=n.get('jp_len'))
        if 'stat' in item:
            s = item['stat']
            add(fname, s['offset'], s['jp'], s['kr'], jp_len=s.get('jp_len'))
        for desc in item['desc']:
            add(fname, desc['offset'], desc['jp'], desc['kr'], jp_len=desc.get('jp_len'))

    for entry in translation.get('ui', []):
        fname = 'GF2.COM'
        add_ui(fname, entry['offset'], entry.get('jp_len', len(entry['jp'].encode('shift_jis'))), entry['kr'])

    return by_file


def patch_data(data, replacements):
    """압축 해제된 데이터에 텍스트 교체 적용. 오프셋 내림차순."""
    buf = bytearray(data)
    replacements.sort(key=lambda r: r[0], reverse=True)

    for entry in replacements:
        if len(entry) == 3 and isinstance(entry[1], bytes):
            offset, old, new = entry
            actual = buf[offset:offset + len(old)]
            if actual != old:
                if len(actual) != len(old):
                    raise ValueError(
                        f'오프셋 0x{offset:X} 길이 불일치: '
                        f'예상 {len(old)}바이트 != 실제 {len(actual)}바이트'
                    )
                # 0x85XX 가이지 인코딩 차이: 같은 문자지만 다른 바이트 → 위치는 정확
                print(f'  ⚠ 0x{offset:X} 가이지 인코딩 차이 (무시)')
            buf[offset:offset + len(old)] = new
        else:
            offset, length, new = entry
            buf[offset:offset + length] = new

    return bytes(buf)


GF2_BOOTSTRAP_SIZE = 0x71   # x86 self-extractor stub (0x000-0x070); LZ data starts here
GF2_PAD_SIZE = 236          # bytes output before part71 data (offset correction)


def run(game_dir):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    title = os.path.basename(os.path.normpath(game_dir))

    trans_path = os.path.join(project_root, 'translation', title, 'translation.json')
    with open(trans_path, encoding='utf-8') as f:
        translation = json.load(f)

    charmap = load_charmap()
    by_file = collect_replacements(translation, charmap)

    if not by_file:
        print('번역된 항목 없음')
        return

    out_dir = os.path.join(project_root, 'build', title)
    os.makedirs(out_dir, exist_ok=True)

    for fname, replacements in by_file.items():
        src_path = os.path.join(game_dir, fname)
        with open(src_path, 'rb') as f:
            raw = f.read()

        if fname == 'GF2.COM':
            bootstrap = raw[:GF2_BOOTSTRAP_SIZE]
            data = decompress(raw, start=GF2_BOOTSTRAP_SIZE)
            adj = [(r[0] - GF2_PAD_SIZE,) + r[1:] for r in replacements]
            patched = patch_data(data, adj)
            compressed = bootstrap + compress(patched)
        else:
            data = decompress(raw)
            patched = patch_data(data, replacements)
            compressed = compress(patched)

        out_path = os.path.join(out_dir, fname)
        with open(out_path, 'wb') as f:
            f.write(compressed)

        print(f'{fname}: {len(replacements)}건 교체, '
              f'{len(raw)} → {len(compressed)} bytes')


def patch_fdi(fdi_path, build_dir):
    """build/ 의 패치된 파일을 FAT12 FDI에 삽입. 변경된 파일 목록 반환."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pc98disk import DiskImage

    build_files = [f for f in os.listdir(build_dir)
                   if os.path.isfile(os.path.join(build_dir, f))
                   and not f.startswith('.')]
    if not build_files:
        return []

    img = DiskImage.open(fdi_path)
    for fname in build_files:
        img.add_file(fname, open(os.path.join(build_dir, fname), 'rb').read())
    img.save(fdi_path)
    return build_files


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python3 hukyou_inserter.py <game_dir>')
        sys.exit(1)
    run(sys.argv[1])
