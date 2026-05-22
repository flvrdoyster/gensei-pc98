"""
환세희담 demo 디스크 한글 패치 스크립트
=========================================

사용법:
  python3 kitan_demo_inserter.py <game_dir>

동작:
  1. translation/kitan/translation.json의 demo 섹션 로드
  2. original/kitan/demo/SP1.COM에 한글 바이트 치환
  3. 패치된 SP1.COM을 build/kitan-demo/ 에 저장
  4. emulator/rom/kitan-demo.fdi에 삽입 후 저장
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hukyou_inserter import load_charmap
from kitan_inserter import encode_korean_kitan
from pc98disk import DiskImage


def run(game_dir):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # game_dir 정규화
    base = os.path.basename(os.path.normpath(game_dir))
    if base == 'data':
        title_dir = os.path.dirname(os.path.normpath(game_dir))
    else:
        title_dir = game_dir

    demo_dir = os.path.join(title_dir, 'demo')
    sp1_src  = os.path.join(demo_dir, 'SP1.COM')
    fdi_src  = os.path.join(project_root, 'emulator', 'rom', 'kitan-demo.fdi')

    if not os.path.exists(sp1_src):
        print(f'SP1.COM 없음: {sp1_src}')
        sys.exit(1)
    if not os.path.exists(fdi_src):
        print(f'kitan-demo.fdi 없음: {fdi_src}')
        sys.exit(1)

    trans_path = os.path.join(project_root, 'translation', 'kitan', 'translation.json')
    with open(trans_path, encoding='utf-8') as f:
        translation = json.load(f)

    demo_entries = [e for e in translation.get('demo', []) if e.get('kr', '').strip()]
    if not demo_entries:
        print('번역된 demo 항목 없음')
        return

    charmap = load_charmap()

    # SP1.COM 패치
    with open(sp1_src, 'rb') as f:
        sp1 = bytearray(f.read())

    patched = 0
    for entry in demo_entries:
        offset  = entry['offset']
        jp_len  = entry['jp_len']
        kr      = entry['kr']
        kr_bytes = encode_korean_kitan(kr, charmap)

        if len(kr_bytes) > jp_len:
            print(f'  ⚠ 0x{offset:04X} {entry["jp"]!r}: KR 길이 초과 ({len(kr_bytes)} > {jp_len}), 건너뜀')
            continue

        fill = jp_len - len(kr_bytes)
        sp1[offset:offset + jp_len] = kr_bytes + b'\x00' * fill
        patched += 1
        print(f'  0x{offset:04X}: {entry["jp"]!r} -> {kr!r}')

    print(f'SP1.COM: {patched}건 패치')

    # 패치된 SP1.COM을 build/kitan-demo/ 에 저장
    build_dir = os.path.join(project_root, 'build', 'kitan-demo')
    os.makedirs(build_dir, exist_ok=True)
    with open(os.path.join(build_dir, 'SP1.COM'), 'wb') as f:
        f.write(sp1)

    # FDI에 삽입 → emulator/rom/ 에 바로 출력
    disk = DiskImage.open(fdi_src)
    disk.add_file('SP1.COM', bytes(sp1))
    disk.save()

    print(f'저장: {fdi_src}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python3 kitan_demo_inserter.py <game_dir>')
        sys.exit(1)
    run(sys.argv[1])
