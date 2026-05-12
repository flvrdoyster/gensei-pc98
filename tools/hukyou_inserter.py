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

from compile_lz import decompress, compress


def load_charmap():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'charmap.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def encode_korean(text, charmap):
    """한국어 텍스트를 SJIS 바이트로 인코딩. 한글은 charmap, 나머지는 SJIS."""
    result = bytearray()
    for ch in text:
        if ch in charmap:
            code = charmap[ch]
            result.append(int(code[:2], 16))
            result.append(int(code[2:], 16))
        else:
            encoded = ch.encode('shift_jis', errors='strict')
            result.extend(encoded)
    return bytes(result)


def collect_replacements(translation, charmap):
    """translation.json에서 파일별 교체 목록 생성."""
    by_file = {}

    for dialog in translation['dialogs']:
        fname = dialog['file']
        if fname not in by_file:
            by_file[fname] = []
        for line in dialog['lines']:
            if not line['kr']:
                continue
            old = line['jp'].encode('shift_jis')
            new = encode_korean(line['kr'], charmap)
            by_file[fname].append((line['offset'], old, new))

    for item in translation.get('items', []):
        fname = 'MESSAGE.CMD'
        if fname not in by_file:
            by_file[fname] = []

        if item['name']['kr']:
            old = item['name']['jp'].encode('shift_jis')
            new = encode_korean(item['name']['kr'], charmap)
            by_file[fname].append((item['name']['offset'], old, new))

        if 'stat' in item and item['stat']['kr']:
            old = item['stat']['jp'].encode('shift_jis')
            new = encode_korean(item['stat']['kr'], charmap)
            by_file[fname].append((item['stat']['offset'], old, new))

        for desc in item['desc']:
            if not desc['kr']:
                continue
            old = desc['jp'].encode('shift_jis')
            new = encode_korean(desc['kr'], charmap)
            by_file[fname].append((desc['offset'], old, new))

    return by_file


def patch_data(data, replacements):
    """압축 해제된 데이터에 텍스트 교체 적용. 오프셋 내림차순."""
    buf = bytearray(data)
    replacements.sort(key=lambda r: r[0], reverse=True)

    for offset, old, new in replacements:
        actual = buf[offset:offset + len(old)]
        if actual != old:
            raise ValueError(
                f'오프셋 0x{offset:X} 불일치: '
                f'예상 {old.hex()} != 실제 {actual.hex()}'
            )
        buf[offset:offset + len(old)] = new

    return bytes(buf)


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
