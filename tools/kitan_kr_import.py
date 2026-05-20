"""
환세희담 한국어판 텍스트를 translation.json kr 필드에 채우는 스크립트.

사용법:
  python3 tools/kitan_kr_import.py original/kitan_kr translation/kitan/translation.json

블록 인덱스 + 줄 인덱스로 JP/KR 텍스트를 1:1 매핑.

KR 인코딩:
  리드 바이트: 0x81-0x9F (SJIS 범위), 트레일: 0x40-0xFC (0x7F 제외)
  glyph_index = (lead - 0x81) * 189 + (trail - 0x40)
  → EUC-KR lead = 0xA1 + glyph // 96
  → EUC-KR trail = 0xA0 + glyph % 96
  MDRSYSF.COM에서 역공학으로 확인된 두 경로(SJIS 범위 / EUC-KR)가
  동일한 glyph index 공간을 공유함을 이용.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from compile_lz import decompress


# ─── 인코딩 ────────────────────────────────────────────

def _is_kr(data, i):
    """SJIS 바이트 범위만 체크 (shift_jis 디코딩 없이)."""
    if i + 1 >= len(data):
        return False
    b = data[i]
    if not (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF):
        return False
    b2 = data[i + 1]
    return (0x40 <= b2 <= 0x7E or 0x80 <= b2 <= 0xFC) and b2 != 0x7F


def _decode_kr(data, i):
    """게임 코드(SJIS 범위) → glyph_index → EUC-KR → 유니코드."""
    lead, trail = data[i], data[i + 1]
    glyph = (lead - 0x81) * 189 + (trail - 0x40)
    euc_lead = 0xA1 + glyph // 96
    euc_trail = 0xA0 + glyph % 96
    if euc_lead > 0xFE or euc_trail > 0xFE or euc_trail < 0xA1:
        return ''  # 미정의 위치 (제어 코드 등)
    try:
        return bytes([euc_lead, euc_trail]).decode('euc_kr')
    except (UnicodeDecodeError, ValueError):
        return ''


# ─── 대화 추출 (kitan_parser.py와 동일 로직, 디코더만 교체) ──────────────

def extract_kr_dialogs(data):
    def has_text(start):
        for j in range(start, min(start + 5, len(data) - 1)):
            if _is_kr(data, j):
                return True
        return False

    dialogs = []
    cur_lines = []
    cur_text = ''
    in_dialog = False
    i = 0

    def flush_line():
        nonlocal cur_text
        t = cur_text.strip()
        if t:
            cur_lines.append(t)
        cur_text = ''

    def flush_dialog():
        flush_line()
        if cur_lines:
            dialogs.append(list(cur_lines))
        cur_lines.clear()

    while i < len(data) - 1:
        if data[i] == 0x6b and data[i + 1] == 0x00:
            if in_dialog:
                flush_dialog()
            in_dialog = has_text(i + 2)
            i += 2
            cur_text = ''
            continue

        if not in_dialog:
            i += 1
            continue

        if data[i] in (0x72, 0x73, 0x76):
            flush_line()
            i += 2
            continue

        if data[i] == 0x64 and i + 1 < len(data) and data[i + 1] not in (0x00, 0x02):
            flush_line()
            i += 2
            continue

        if data[i] == 0x65 and i + 1 < len(data) and data[i + 1] != 0x00:
            flush_line()
            i += 2
            continue

        # 81 65 / 81 6b: 제어 코드 (81 6b는 뒤에 텍스트가 없을 때만)
        if data[i] == 0x81 and i + 1 < len(data) and data[i + 1] in (0x65, 0x6b):
            if data[i + 1] == 0x65 or i + 2 >= len(data) or not _is_kr(data, i + 2):
                i += 2
                continue

        if _is_kr(data, i):
            cur_text += _decode_kr(data, i)
            i += 2
            continue

        i += 1

    if in_dialog:
        flush_dialog()

    return dialogs


def extract_kr_items(data):
    """MESSAGE.CMD: 0f 03 마커 기준으로 name/stat/desc 추출."""
    items = []
    i = 0
    while i < len(data) - 1:
        if data[i] != 0x0f or data[i + 1] != 0x03:
            i += 1
            continue
        i += 2
        state = 'name'
        name, stat, desc_lines = '', '', []
        cur = ''

        def flush():
            nonlocal cur, name, stat
            s = cur.strip()
            cur = ''
            if not s:
                return
            if state == 'name':
                name = s
            elif state == 'stat':
                stat = s
            else:
                desc_lines.append(s)

        while i < len(data) - 1:
            b, nb = data[i], data[i + 1]
            if (b == 0x62 and nb == 0x00) or (b == 0x0f and nb == 0x03):
                flush()
                break
            if b == 0x64:
                flush()
                state = 'desc' if (nb == 0x02 and state == 'stat') else 'stat'
                i += 2
                continue
            if b == 0x72:
                flush()
                if state in ('stat', 'name'):
                    state = 'desc'
                i += 2
                continue
            if _is_kr(data, i):
                cur += _decode_kr(data, i)
                i += 2
            else:
                i += 1

        if name:
            items.append({'name': name, 'stat': stat, 'desc': desc_lines})

    return items


# ─── 매핑 + JSON 업데이트 ────────────────────────────────

DIALOG_FILES = [
    'START.CMD', 'SC1A.CMD', 'SC1B.CMD',
    'SC2A.CMD', 'SC2B.CMD', 'SC2C.CMD', 'SC2D.CMD', 'SC2E.CMD', 'SC2F.CMD', 'SC2G.CMD',
    'SC3A.CMD', 'SC3B.CMD', 'SC3C.CMD', 'SC3D.CMD', 'SC3E.CMD',
    'SC4A.CMD', 'SC4B.CMD', 'SC4C.CMD', 'SC4D.CMD', 'SC4E.CMD',
    'SC5A.CMD', 'SC5B.CMD', 'SC5C.CMD', 'SC5D.CMD', 'SC5E.CMD', 'SC5F.CMD',
    'SC6A.CMD', 'SC6B.CMD', 'SC6C.CMD', 'SC6D.CMD', 'SC7A.CMD',
    'PARTY2.CMD', 'PARTY3.CMD', 'PARTY4.CMD', 'PARTY6.CMD', 'PARTY7.CMD',
    'BTL_PC.CMD', 'ENDING.CMD', 'MESSAGE.CMD',
]
ITEM_FILE = 'MESSAGE.CMD'


def run(kr_dir, json_path):
    with open(json_path, encoding='utf-8') as f:
        tj = json.load(f)

    # 파일별 KR 대화 블록 추출
    kr_dialogs: dict[str, list] = {}
    for fname in DIALOG_FILES:
        path = os.path.join(kr_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path, 'rb') as f:
            data = decompress(f.read())
        kr_dialogs[fname] = extract_kr_dialogs(data)

    # KR 아이템 추출
    item_path = os.path.join(kr_dir, ITEM_FILE)
    kr_items = []
    if os.path.exists(item_path):
        with open(item_path, 'rb') as f:
            data = decompress(f.read())
        kr_items = extract_kr_items(data)

    # 대화 매핑: JP 블록 순서(파일별) → KR 블록 인덱스
    # JP translation.json의 dialogs는 파일+index 순서대로 나열됨
    filled = skipped = 0
    file_block_idx: dict[str, int] = {}  # 파일별 JP 블록 카운터 (0-based)

    for jp_dialog in tj['dialogs']:
        fname = jp_dialog['file']
        if fname not in kr_dialogs:
            continue

        # 이 파일에서 몇 번째 블록인지 (0-based)
        bi = file_block_idx.get(fname, 0)
        file_block_idx[fname] = bi + 1

        kr_blocks = kr_dialogs[fname]
        if bi >= len(kr_blocks):
            skipped += 1
            continue

        kr_lines = kr_blocks[bi]
        # 기존 kr 필드 초기화 후, 전체 KR 텍스트를 첫 번째 JP 줄에만 넣기
        for jp_line in jp_dialog['lines']:
            jp_line.pop('kr', None)
        if kr_lines:
            jp_dialog['lines'][0]['kr'] = '　'.join(kr_lines)
            filled += 1

    # 아이템 매핑: 인덱스 순서
    item_filled = 0
    for ji, jp_item in enumerate(tj.get('items', [])):
        if ji >= len(kr_items):
            break
        kr_item = kr_items[ji]
        if kr_item['name']:
            jp_item['name']['kr'] = kr_item['name']
            item_filled += 1
        if 'stat' in jp_item and kr_item['stat']:
            jp_item['stat']['kr'] = kr_item['stat']
        for di, jp_desc in enumerate(jp_item.get('desc', [])):
            if di < len(kr_item['desc']):
                jp_desc['kr'] = kr_item['desc'][di]

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tj, f, ensure_ascii=False, indent=2)

    print(f'대화 줄 채움: {filled}개 / 스킵: {skipped}블록')
    print(f'아이템 name 채움: {item_filled}개')
    print(f'저장: {json_path}')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: python3 kitan_kr_import.py <kr_dir> <translation.json>')
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
