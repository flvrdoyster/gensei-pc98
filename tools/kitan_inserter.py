"""
환세희담 번역 재삽입 스크립트
================================

사용법:
  python3 kitan_inserter.py <game_dir>

동작:
  1. translation/kitan/translation.json 로드
  2. 원본 CMD 파일 압축 해제
  3. 각 오프셋에서 JP 텍스트를 KR로 교체 (charmap.json 기반 인코딩)
  4. LZ 재압축
  5. kitan-system.fdi (DISK_B) / kitan-data.fdi (DISK_C)에 직접 덮어쓰기
"""

import json
import os
import struct
import sys

from compile_lz import decompress, compress
from hukyou_inserter import load_charmap, collect_replacements, patch_data


# DISK_B.DAT: kitan-system.fdi 내 오프셋 0x14400
# DISK_C: kitan-data.fdi 내 오프셋 0x3C00
DISK_B_BASE = 0x14400
DISK_C_BASE = 0x3C00
DATA_OFFSET = 0x400

# CMD 파일 → 아카이브 인덱스 매핑 (바이트 비교로 검증 완료)
DISK_B_INDEX = {
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
    by_file = collect_replacements(translation, charmap)

    if not by_file:
        print('번역된 항목 없음')
        return

    system_fdi_path = os.path.join(project_root, 'emulator', 'rom', 'kitan-system.fdi')
    data_fdi_path = os.path.join(project_root, 'emulator', 'rom', 'kitan-data.fdi')

    with open(system_fdi_path, 'rb') as f:
        system_fdi = bytearray(f.read())
    with open(data_fdi_path, 'rb') as f:
        data_fdi = bytearray(f.read())

    system_entries = parse_offset_table(system_fdi, DISK_B_BASE)
    data_entries = parse_offset_table(data_fdi, DISK_C_BASE)

    system_modified = False
    data_modified = False

    for fname, replacements in by_file.items():
        src_path = os.path.join(game_dir, fname)
        with open(src_path, 'rb') as f:
            raw = f.read()

        decompressed = decompress(raw)
        patched = patch_data(decompressed, replacements)
        compressed = compress(patched)

        wrote = False

        if fname in DISK_B_INDEX:
            idx = DISK_B_INDEX[fname]
            abs_start, abs_end = get_slot_range(system_entries, idx, DISK_B_BASE)
            slot_size = abs_end - abs_start
            if len(compressed) > slot_size:
                print(f'  ⚠ {fname} (DISK_B): 압축 크기 초과 '
                      f'({len(compressed)} > {slot_size})')
            else:
                system_fdi[abs_start:abs_start + len(compressed)] = compressed
                if len(compressed) < slot_size:
                    system_fdi[abs_start + len(compressed):abs_end] = (
                        b'\x00' * (slot_size - len(compressed)))
                system_modified = True
                wrote = True

        if fname in DISK_C_INDEX:
            idx = DISK_C_INDEX[fname]
            abs_start, abs_end = get_slot_range(data_entries, idx, DISK_C_BASE)
            slot_size = abs_end - abs_start
            if len(compressed) > slot_size:
                print(f'  ⚠ {fname} (DISK_C): 압축 크기 초과 '
                      f'({len(compressed)} > {slot_size})')
            else:
                data_fdi[abs_start:abs_start + len(compressed)] = compressed
                if len(compressed) < slot_size:
                    data_fdi[abs_start + len(compressed):abs_end] = (
                        b'\x00' * (slot_size - len(compressed)))
                data_modified = True
                wrote = True

        if not wrote and fname not in DISK_B_INDEX and fname not in DISK_C_INDEX:
            print(f'  ⚠ {fname}: 매핑 없음')
            continue

        print(f'{fname}: {len(replacements)}건 교체, '
              f'{len(raw)} → {len(compressed)} bytes')

    if system_modified:
        with open(system_fdi_path, 'wb') as f:
            f.write(system_fdi)
        print(f'\n{os.path.basename(system_fdi_path)} 갱신 완료')
    if data_modified:
        with open(data_fdi_path, 'wb') as f:
            f.write(data_fdi)
        print(f'\n{os.path.basename(data_fdi_path)} 갱신 완료')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python3 kitan_inserter.py <game_dir>')
        sys.exit(1)
    run(sys.argv[1])
