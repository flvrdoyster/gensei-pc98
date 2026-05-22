"""
환세희담 번역 재삽입 스크립트
================================

사용법:
  python3 kitan_inserter.py <game_dir>

동작:
  1. translation/kitan/translation.json 로드
  2. 원본 CMD 파일 압축 해제 → 텍스트 패치 → LZ 재압축
  3. build/kitan/ 에 패치된 CMD 저장
"""

import json
import os
import struct
import sys

import hukyou_inserter
from compile_lz import decompress, compress, encode_gaiji_char
from hukyou_inserter import (
    load_charmap, collect_replacements, patch_data,
    ASCII_TO_FULLWIDTH,
)


def encode_korean_kitan(text, charmap=None, use_gaiji=False):
    """희담 KR 인코딩: 풍광전과 동일하게 charmap.json 기반."""
    result = bytearray()
    for ch in text:
        if charmap and ch in charmap:
            code = charmap[ch]
            result.append(int(code[:2], 16))
            result.append(int(code[2:], 16))
        elif use_gaiji and encode_gaiji_char(ch):
            result.extend(encode_gaiji_char(ch))
        elif ch in ASCII_TO_FULLWIDTH:
            result.extend(ASCII_TO_FULLWIDTH[ch])
        else:
            result.extend(ch.encode('shift_jis', errors='strict'))
    return bytes(result)


# ─────────────────────────────────────
# 아카이브 오프셋 테이블
# ─────────────────────────────────────

DISK_B_BASE = 0x14400  # DISK_B.DAT in kitan-system.fdi
DISK_C_BASE = 0x3C00   # DISK_C in kitan-data.fdi
DATA_OFFSET = 0x400

DISK_B_INDEX = {
    'GS.OVL': 0,
    'START.CMD': 2, 'MESSAGE.CMD': 3, 'PARTY2.CMD': 4, 'BTL_PC.CMD': 6,
    'SC1A.CMD': 11, 'SC1B.CMD': 12,
    'SC2A.CMD': 14, 'SC2B.CMD': 15, 'SC2C.CMD': 16, 'SC2D.CMD': 17,
    'SC2E.CMD': 18, 'SC2F.CMD': 19, 'SC2G.CMD': 20,
    'PARTY3.CMD': 29, 'PARTY4.CMD': 30, 'PARTY6.CMD': 31,
    'SC3A.CMD': 43, 'SC3B.CMD': 44, 'SC3C.CMD': 45, 'SC3D.CMD': 46, 'SC3E.CMD': 47,
    'SC5D.CMD': 52, 'SC5E.CMD': 53, 'SC5F.CMD': 54,
    'SC4A.CMD': 57, 'SC4B.CMD': 58, 'SC4C.CMD': 59, 'SC4D.CMD': 60,
    'SC5A.CMD': 77, 'SC5B.CMD': 78, 'SC5C.CMD': 79,
    'SC6A.CMD': 89, 'SC6B.CMD': 90, 'SC6C.CMD': 91, 'SC6D.CMD': 93,
    'SC7A.CMD': 115, 'SC4E.CMD': 116, 'ENDING.CMD': 119,
}

DISK_C_INDEX = {
    'PARTY7.CMD': 81,
}


def parse_offset_table(data, base):
    entries = []
    for i in range(base + 4, base + DATA_OFFSET, 4):
        if i + 3 >= len(data):
            break
        high = struct.unpack_from('<H', data, i)[0]
        low = struct.unpack_from('<H', data, i + 2)[0]
        end_offset = high * 65536 + low
        if end_offset == 0:
            break
        entries.append(end_offset)
    return entries


def get_slot_range(entries, index, disk_base):
    start = entries[index - 1] if index > 0 else DATA_OFFSET
    end = entries[index]
    return disk_base + start, disk_base + end


def detect_disk_type(fdi_data):
    """FDI가 system(DISK_B) 인지 data(DISK_C) 인지 판별."""
    if len(fdi_data) > DISK_B_BASE + 4:
        magic = struct.unpack_from('>I', fdi_data, DISK_B_BASE)[0]
        if magic == 4:
            return 'system'
    if len(fdi_data) > DISK_C_BASE + 4:
        magic = struct.unpack_from('>I', fdi_data, DISK_C_BASE)[0]
        if magic == 4:
            return 'data'
    return None


def patch_fdi(fdi_data, build_dir):
    """build/ 의 패치된 CMD 파일을 FDI에 삽입. bytes 반환."""
    fdi = bytearray(fdi_data)
    disk_type = detect_disk_type(fdi)
    if disk_type is None:
        raise ValueError('DISK_B/DISK_C 아카이브를 찾을 수 없음')

    if disk_type == 'system':
        base, index_map = DISK_B_BASE, DISK_B_INDEX
    else:
        base, index_map = DISK_C_BASE, DISK_C_INDEX

    entries = parse_offset_table(fdi, base)
    patched = []

    build_files = [f for f in os.listdir(build_dir)
                   if os.path.isfile(os.path.join(build_dir, f))
                   and not f.startswith('.')]

    for fname in build_files:
        if fname not in index_map:
            continue
        idx = index_map[fname]
        abs_start, abs_end = get_slot_range(entries, idx, base)
        slot_size = abs_end - abs_start

        with open(os.path.join(build_dir, fname), 'rb') as f:
            compressed = f.read()

        if len(compressed) > slot_size:
            continue

        fdi[abs_start:abs_start + len(compressed)] = compressed
        if len(compressed) < slot_size:
            fdi[abs_start + len(compressed):abs_end] = (
                b'\x00' * (slot_size - len(compressed)))
        patched.append(fname)

    return bytes(fdi), patched


# ─────────────────────────────────────
# 빌드 (build/ 출력)
# ─────────────────────────────────────

def run(game_dir):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    _base = os.path.basename(os.path.normpath(game_dir))
    if _base == 'data':
        title = os.path.basename(os.path.dirname(os.path.normpath(game_dir)))
    else:
        title = _base
        game_dir = os.path.join(game_dir, 'data')

    trans_path = os.path.join(project_root, 'translation', title, 'translation.json')
    with open(trans_path, encoding='utf-8') as f:
        translation = json.load(f)

    charmap = load_charmap()
    _orig = hukyou_inserter.encode_korean
    hukyou_inserter.encode_korean = encode_korean_kitan
    by_file = collect_replacements(translation, charmap)
    hukyou_inserter.encode_korean = _orig

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

    # GS.OVL 패치 (캐릭터 이름, 배틀 메뉴, UI 라벨 등)
    _patch_gsovl(game_dir, out_dir, charmap, translation)


def _patch_gsovl(game_dir, out_dir, charmap, translation):
    src = os.path.join(game_dir, 'GS.OVL')
    if not os.path.exists(src):
        print('GS.OVL: 없음, 건너뜀')
        return
    with open(src, 'rb') as f:
        raw = f.read()
    data = bytearray(decompress(raw))

    patched = 0
    for entry in translation.get('gsovl', []):
        kr = entry.get('kr', '').strip()
        if not kr:
            continue
        offset = entry['offset']
        jp_len = entry['jp_len']
        kr_bytes = encode_korean_kitan(kr, charmap)
        if len(kr_bytes) > jp_len:
            print(f'  ⚠ 0x{offset:04X} {entry["jp"]!r}: KR 길이 초과 ({len(kr_bytes)} > {jp_len}), 건너뜀')
            continue
        fill = jp_len - len(kr_bytes)
        padding = b'\x00\xF4' * (fill // 2) + (b'\x00' if fill % 2 else b'')
        data[offset:offset + jp_len] = kr_bytes + padding
        patched += 1

    recompressed = compress(bytes(data))
    out_path = os.path.join(out_dir, 'GS.OVL')
    with open(out_path, 'wb') as f:
        f.write(recompressed)
    print(f'GS.OVL: {patched}건 패치 완료 ({len(raw)} → {len(recompressed)} bytes)')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python3 kitan_inserter.py <game_dir>')
        sys.exit(1)
    run(sys.argv[1])
