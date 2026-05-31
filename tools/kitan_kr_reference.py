"""
환세희담 한국어판(original/kitan_kr) 텍스트를 참고용 마크다운으로 정리.

사용법:
  python3 tools/kitan_kr_reference.py

출력: translation/kitan/KR_REFERENCE.md
  SC4A~SC6D 를 파일별 섹션으로, JP 블록마다 JP 줄 ↔ 한국어판 줄 나란히.

번역 작업 시 참고용. translation.json 은 건드리지 않는다.
한국어판 추출 로직은 kitan_kr_import 의 함수를 재사용 (JP extract_dialogs 미러).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from compile_lz import decompress
from kitan_parser import extract_dialogs
from kitan_kr_import import extract_kr_dialogs


def _is_story_text(jp):
    """대화 텍스트로 보이면 True. 가나/대화괄호가 없는 한자 노이즈는 제외."""
    return any('ぁ' <= c <= 'ヿ' or c in '「」『』（）？！…、。' for c in jp)


def _dialog_offset_map(jp_data, kr_data):
    """6b00/6e006701 대화 블록만 index 매칭 → {jp_block_offset: [kr_line, ...]}."""
    jp_dialogs = extract_dialogs(jp_data)
    kr_dialogs = extract_kr_dialogs(kr_data)
    out = {}
    for n, jp_lines in enumerate(jp_dialogs):
        if n < len(kr_dialogs):
            _, kr_lines = kr_dialogs[n]
            if kr_lines:
                out[jp_lines[0]['offset']] = kr_lines
    return out

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 새 번역 대상 (참고문서 생성 범위)
TARGET_FILES = [
    'SC4A.CMD', 'SC4B.CMD', 'SC4C.CMD', 'SC4D.CMD', 'SC4E.CMD',
    'SC5A.CMD', 'SC5B.CMD', 'SC5C.CMD', 'SC5D.CMD', 'SC5E.CMD', 'SC5F.CMD',
    'SC6A.CMD', 'SC6B.CMD', 'SC6C.CMD', 'SC6D.CMD',
]


def run():
    jp_dir = os.path.join(PROJECT_ROOT, 'original', 'kitan', 'data')
    kr_dir = os.path.join(PROJECT_ROOT, 'original', 'kitan_kr')
    json_path = os.path.join(PROJECT_ROOT, 'translation', 'kitan', 'translation.json')
    out_path = os.path.join(PROJECT_ROOT, 'translation', 'kitan', 'KR_REFERENCE.md')

    with open(json_path, encoding='utf-8') as f:
        tj = json.load(f)

    # 파일별 JP 블록 (translation.json 순서)
    jp_blocks_by_file = {}
    for d in tj['dialogs']:
        jp_blocks_by_file.setdefault(d['file'], []).append(d)

    lines_out = [
        '# 환세희담 한국어판 참고 텍스트',
        '',
        '한국어판(`original/kitan_kr`)을 다시 파싱한 참고용 문서. '
        '새 번역(GUIDE.md 기준) 작성 시 의미·뉘앙스 참고용이며 직접 베끼지 않는다.',
        '',
        '`tools/kitan_kr_reference.py` 로 재생성. JP 줄 → 한국어판 줄 순으로 정렬.',
        '',
        '---',
        '',
    ]

    total_blocks = total_pairs = mismatch_blocks = 0

    for fname in TARGET_FILES:
        jp_path = os.path.join(jp_dir, fname)
        kr_path = os.path.join(kr_dir, fname)
        if not os.path.exists(jp_path) or not os.path.exists(kr_path):
            continue

        jp_data = decompress(open(jp_path, 'rb').read())
        kr_data = decompress(open(kr_path, 'rb').read())
        offset_map = _dialog_offset_map(jp_data, kr_data)

        lines_out.append(f'## {fname}')
        lines_out.append('')

        for block in jp_blocks_by_file.get(fname, []):
            jp_lines = block['lines']
            key = jp_lines[0]['offset']
            kr_lines = offset_map.get(key)
            if not kr_lines:
                continue
            # 노이즈 블록 (한자만 있는 바이너리 오탐) 제외
            if not any(_is_story_text(ln['jp']) for ln in jp_lines):
                continue
            total_blocks += 1

            lines_out.append(f'**@0x{key:X}**')
            lines_out.append('')

            jp_texts = [ln['jp'] for ln in jp_lines]
            if len(jp_texts) == len(kr_lines):
                for jt, kt in zip(jp_texts, kr_lines):
                    lines_out.append(f'- {jt}  →  {kt}')
                    total_pairs += 1
            else:
                # 줄 수 불일치 — JP/KR 따로 나열
                mismatch_blocks += 1
                lines_out.append(f'- (줄 수 불일치: JP {len(jp_texts)} / KR {len(kr_lines)})')
                lines_out.append(f'  - JP: {" / ".join(jp_texts)}')
                lines_out.append(f'  - KR: {" / ".join(kr_lines)}')
            lines_out.append('')

        lines_out.append('---')
        lines_out.append('')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_out))

    print(f'저장: {out_path}')
    print(f'블록 {total_blocks}개 / 줄 매칭 {total_pairs}개 / 줄 수 불일치 블록 {mismatch_blocks}개')


if __name__ == '__main__':
    run()
