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

    def add(fname, offset, jp, kr):
        if not kr:
            return
        old = jp.encode('shift_jis')
        new = encode_korean(kr, charmap)
        new = fit_length(old, new, context=f'{fname} 0x{offset:X}: {kr}')
        if fname not in by_file:
            by_file[fname] = []
        by_file[fname].append((offset, old, new))

    def add_ui(fname, offset, jp_len, kr):
        if not kr:
            return
        new = encode_korean(kr, charmap, use_gaiji=True)
        dummy_old = b'\x00' * jp_len
        new = fit_length(dummy_old, new, context=f'{fname} 0x{offset:X}: {kr}')
        if fname not in by_file:
            by_file[fname] = []
        by_file[fname].append((offset, jp_len, new))

    for dialog in translation['dialogs']:
        fname = dialog['file']
        for line in dialog['lines']:
            add(fname, line['offset'], line['jp'], line['kr'])

    for item in translation.get('items', []):
        fname = 'MESSAGE.CMD'
        add(fname, item['name']['offset'], item['name']['jp'], item['name']['kr'])
        if 'stat' in item:
            add(fname, item['stat']['offset'], item['stat']['jp'], item['stat']['kr'])
        for desc in item['desc']:
            add(fname, desc['offset'], desc['jp'], desc['kr'])

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
                raise ValueError(
                    f'오프셋 0x{offset:X} 불일치: '
                    f'예상 {old.hex()} != 실제 {actual.hex()}'
                )
            buf[offset:offset + len(old)] = new
        else:
            offset, length, new = entry
            buf[offset:offset + length] = new

    return bytes(buf)


GF2_BOOTSTRAP_SIZE = 0x171  # x86 self-extractor stub; LZ data starts here
GF2_PAD_SIZE = 837          # bytes output when parsing bootstrap as LZ (offset correction)


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


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python3 hukyou_inserter.py <game_dir>')
        sys.exit(1)
    run(sys.argv[1])
