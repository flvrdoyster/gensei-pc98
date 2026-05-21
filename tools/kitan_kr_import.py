"""
환세희담 한국어판 텍스트를 translation.json kr 필드에 채우는 스크립트.

사용법:
  python3 tools/kitan_kr_import.py original/kitan_kr translation/kitan/translation.json

블록 인덱스 + 줄 인덱스로 JP/KR 텍스트를 1:1 매핑.
각 파일에서 KR 블록을 오프셋 기준으로 정렬해 JP 블록 순서와 맞춤.
빈 kr 필드만 채우며, 기존 번역은 건드리지 않음.

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


# ─── 대화 추출 ──────────────────────────────────────────
# 각 함수는 (start_offset, [line_text, ...]) 튜플의 리스트를 반환.
# kitan_parser.py 의 동명 함수와 동일한 로직, 디코더만 교체.

_DIALOG_LOOKAHEAD = 30


def extract_kr_dialogs(data):
    """6b 00 기반 대화 블록 추출."""
    dialogs = []
    cur_lines = []
    cur_text = ''
    in_dialog = False
    block_start = 0
    i = 0

    def has_text(start):
        for j in range(start, min(start + _DIALOG_LOOKAHEAD, len(data) - 1)):
            if _is_kr(data, j):
                return True
        return False

    def flush_line():
        nonlocal cur_text
        t = cur_text.strip()
        if len(t) >= 2:
            cur_lines.append(t)
        cur_text = ''

    def flush_dialog():
        flush_line()
        if cur_lines:
            dialogs.append((block_start, list(cur_lines)))
        cur_lines.clear()

    while i < len(data) - 1:
        if data[i] == 0x6b and data[i + 1] == 0x00:
            if in_dialog:
                flush_dialog()
            in_dialog = has_text(i + 2)
            block_start = i
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

        # 64 00: portrait/캐릭터 코드 + 2바이트 인수 = 총 4바이트 오피코드
        if data[i] == 0x64 and i + 1 < len(data) and data[i + 1] == 0x00:
            cur_text = ''
            i += min(4, len(data) - i)
            continue

        if data[i] == 0x64 and i + 1 < len(data) and data[i + 1] not in (0x00, 0x02):
            flush_line()
            i += 2
            continue

        if data[i] == 0x65 and i + 1 < len(data) and data[i + 1] != 0x00:
            flush_line()
            i += 2
            continue

        # 6d 00: 항목 표시 종료 코드 — flush
        if data[i] == 0x6d and i + 1 < len(data) and data[i + 1] == 0x00:
            flush_line()
            i += 2
            continue

        # 81 65: 제어 코드
        if data[i] == 0x81 and i + 1 < len(data) and data[i + 1] == 0x65:
            i += 2
            continue

        # 81 6b: 뒤에 텍스트가 없을 때만 제어 코드
        if data[i] == 0x81 and i + 1 < len(data) and data[i + 1] == 0x6b:
            if i + 2 >= len(data) or not _is_kr(data, i + 2):
                i += 2
                continue

        if _is_kr(data, i):
            cur_text += _decode_kr(data, i)
            i += 2
            continue

        # 비-KR 바이트 — 텍스트 리셋
        cur_text = ''
        i += 1

    if in_dialog:
        flush_dialog()

    return dialogs


def extract_kr_labeled_text(data, prefixes):
    """
    XX YY [KR...] 65 형식 레이블 텍스트 추출.
    kitan_parser.py extract_labeled_text 와 동일한 로직.
    """
    if not prefixes:
        return []

    prefix_set = set(prefixes)
    items = []
    cur_group = []
    cur_start = 0
    cur_prefix = None
    i = 0

    while i < len(data) - 1:
        matched = None
        for p0, p1 in prefix_set:
            if data[i] == p0 and data[i + 1] == p1:
                matched = (p0, p1)
                break

        if matched is None:
            if cur_group:
                items.append((cur_start, cur_group))
                cur_group = []
                cur_prefix = None
            i += 1
            continue

        if matched != cur_prefix and cur_group:
            items.append((cur_start, cur_group))
            cur_group = []
        if not cur_group:
            cur_start = i
        cur_prefix = matched

        j = i + 2
        text = ''

        while j < len(data):
            if data[j] == 0x65:
                j += 2 if j + 1 < len(data) else 1
                break
            if data[j] == 0x64 and j + 1 < len(data):
                j += 2
                continue
            if _is_kr(data, j):
                text += _decode_kr(data, j)
                j += 2
            else:
                j += 1

        if len(text.strip()) >= 2:
            cur_group.append(text.strip())
            i = j
        else:
            if cur_group:
                items.append((cur_start, cur_group))
                cur_group = []
                cur_prefix = None
            i += 1

    if cur_group:
        items.append((cur_start, cur_group))

    return items


_KR_MSG_DIALOG_START = 0x1290


def extract_kr_message_dialog(data):
    """
    MESSAGE.CMD 전용 스토리 대화 추출.
    kitan_parser.py extract_message_dialog 와 동일한 로직.
    """
    blocks = []
    i = _KR_MSG_DIALOG_START
    block_start = i
    cur_lines = []
    cur_text = ''

    while i < len(data):
        b = data[i]

        if b == 0x65:
            t = cur_text.strip()
            if len(t) >= 2:
                cur_lines.append(t)
            cur_text = ''
            if cur_lines:
                blocks.append((block_start, cur_lines))
                cur_lines = []
            i += 1
            block_start = i
            continue

        if b == 0x72:
            t = cur_text.strip()
            if len(t) >= 2:
                cur_lines.append(t)
            cur_text = ''
            i += 2
            continue

        if _is_kr(data, i):
            cur_text += _decode_kr(data, i)
            i += 2
            continue

        i += 1

    t = cur_text.strip()
    if len(t) >= 2:
        cur_lines.append(t)
    if cur_lines:
        blocks.append((block_start, cur_lines))

    return blocks


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

_DEFAULT_LABELED_PREFIXES = [(0x64, 0x01)]
_LABELED_PREFIXES = {
    'ENDING.CMD': [(0x63, 0x08), (0x64, 0x01)],
    **{p: [(0x6d, 0x08), (0x64, 0x01)]
       for p in ('PARTY2.CMD', 'PARTY3.CMD', 'PARTY4.CMD',
                 'PARTY6.CMD', 'PARTY7.CMD')},
    'MESSAGE.CMD': [],
}


def run(kr_dir, json_path):
    with open(json_path, encoding='utf-8') as f:
        tj = json.load(f)

    # 파일별 KR 블록 추출 — JP generate_json 와 동일한 방식으로 합치고 정렬
    kr_file_blocks: dict[str, list] = {}
    for fname in DIALOG_FILES:
        path = os.path.join(kr_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path, 'rb') as f:
            data = decompress(f.read())

        all_kr = extract_kr_dialogs(data)

        prefixes = _LABELED_PREFIXES.get(fname, _DEFAULT_LABELED_PREFIXES)
        all_kr += extract_kr_labeled_text(data, prefixes)

        if fname == ITEM_FILE:
            all_kr += extract_kr_message_dialog(data)

        # 오프셋 기준 정렬 (JP all_blocks.sort 와 동일)
        all_kr.sort(key=lambda x: x[0])

        # 같은 오프셋 중복 제거
        seen = set()
        deduped = []
        for off, lines in all_kr:
            if off not in seen:
                seen.add(off)
                deduped.append(lines)

        kr_file_blocks[fname] = deduped

    # KR 아이템 추출
    item_path = os.path.join(kr_dir, ITEM_FILE)
    kr_items = []
    if os.path.exists(item_path):
        with open(item_path, 'rb') as f:
            data = decompress(f.read())
        kr_items = extract_kr_items(data)

    # 대화 매핑: 파일별 블록 카운터로 JP → KR 1:1
    # 빈 kr 필드만 채움 — 기존 번역 보존
    filled = skipped = 0
    file_block_idx: dict[str, int] = {}

    for jp_dialog in tj['dialogs']:
        fname = jp_dialog['file']
        if fname not in kr_file_blocks:
            continue

        bi = file_block_idx.get(fname, 0)
        file_block_idx[fname] = bi + 1

        kr_blocks = kr_file_blocks[fname]
        if bi >= len(kr_blocks):
            skipped += 1
            continue

        kr_lines = kr_blocks[bi]
        first_line = jp_dialog['lines'][0]
        if kr_lines and not first_line.get('kr'):
            first_line['kr'] = '　'.join(kr_lines)
            filled += 1

    # 아이템 매핑 (빈 kr만)
    item_filled = 0
    for ji, jp_item in enumerate(tj.get('items', [])):
        if ji >= len(kr_items):
            break
        kr_item = kr_items[ji]
        if kr_item['name'] and not jp_item['name'].get('kr'):
            jp_item['name']['kr'] = kr_item['name']
            item_filled += 1
        if 'stat' in jp_item and kr_item['stat'] and not jp_item['stat'].get('kr'):
            jp_item['stat']['kr'] = kr_item['stat']
        for di, jp_desc in enumerate(jp_item.get('desc', [])):
            if di < len(kr_item['desc']) and not jp_desc.get('kr'):
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
