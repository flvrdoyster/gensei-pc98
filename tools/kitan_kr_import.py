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
from kitan_parser import (extract_dialogs, extract_menus, extract_labeled_text,
                          extract_message_dialog,
                          _LABELED_PREFIXES as _JP_LABELED_PREFIXES,
                          _DEFAULT_LABELED_PREFIXES as _JP_DEFAULT_LABELED_PREFIXES,
                          ITEM_FILE as _JP_ITEM_FILE)


# ─── 인코딩 ────────────────────────────────────────────

def _to_halfwidth(text):
    """전각 공백·전각 ASCII 문자를 반각으로 변환.
    U+3000 (전각 스페이스) → 반각 스페이스
    U+FF01–U+FF5E (전각 ！ ~ ～) → U+0021–U+007E (ASCII)
    """
    out = []
    for c in text:
        cp = ord(c)
        if cp == 0x3000:
            out.append(' ')
        elif 0xFF01 <= cp <= 0xFF5E:
            out.append(chr(cp - 0xFEE0))
        else:
            out.append(c)
    return ''.join(out)


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
    """6b 00 기반 대화 블록 추출.
    start_offset = 블록 내 첫 KR 문자 위치 (JP lines[0]['offset'] 와 일치).
    """
    dialogs = []
    cur_lines = []
    cur_text = ''
    in_dialog = False
    block_start = None  # 첫 KR 문자를 만날 때 설정
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
        nonlocal block_start
        flush_line()
        if cur_lines and block_start is not None:
            dialogs.append((block_start, list(cur_lines)))
        cur_lines.clear()
        block_start = None

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
            if block_start is None:
                block_start = i  # 첫 KR 문자 위치 = JP lines[0]['offset'] 에 대응
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
        cur_prefix = matched

        j = i + 2
        text = ''
        text_off = None  # 첫 KR 문자 위치

        while j < len(data):
            if data[j] == 0x65:
                j += 2 if j + 1 < len(data) else 1
                break
            if data[j] == 0x64 and j + 1 < len(data):
                j += 2
                continue
            if _is_kr(data, j):
                if text_off is None:
                    text_off = j
                text += _decode_kr(data, j)
                j += 2
            else:
                j += 1

        if len(text.strip()) >= 2:
            if not cur_group and text_off is not None:
                cur_start = text_off  # 그룹 첫 항목의 첫 KR 문자 위치
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
    block_start = 블록 내 첫 KR 문자 위치 (JP lines[0]['offset'] 와 일치).
    """
    blocks = []
    i = _KR_MSG_DIALOG_START
    block_start = None  # 첫 KR 문자를 만날 때 설정
    cur_lines = []
    cur_text = ''

    while i < len(data):
        b = data[i]

        if b == 0x65:
            t = cur_text.strip()
            if len(t) >= 2:
                cur_lines.append(t)
            cur_text = ''
            if cur_lines and block_start is not None:
                blocks.append((block_start, cur_lines))
                cur_lines = []
            i += 1
            block_start = None  # 다음 블록을 위해 리셋
            continue

        if b == 0x72:
            t = cur_text.strip()
            if len(t) >= 2:
                cur_lines.append(t)
            cur_text = ''
            i += 2
            continue

        if _is_kr(data, i):
            if block_start is None:
                block_start = i  # 첫 KR 문자 위치
            cur_text += _decode_kr(data, i)
            i += 2
            continue

        i += 1

    t = cur_text.strip()
    if len(t) >= 2:
        cur_lines.append(t)
    if cur_lines and block_start is not None:
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


# ─── JP↔KR 오프셋 매핑 ──────────────────────────────────

def _build_offset_map(jp_data, kr_data, fname):
    """
    JP 압축 해제 데이터와 KR 압축 해제 데이터를 받아
    {jp_offset → [kr_line_text, ...]} 딕셔너리를 반환.

    매칭 방식: 추출기 종류별(dialogs / labeled / msg_dialogs)로 N번째끼리 대응.
    JP와 KR 파일의 바이너리 오프셋이 달라도 순서가 같으면 정확히 매핑됨.
    """
    prefixes = _JP_LABELED_PREFIXES.get(fname, _JP_DEFAULT_LABELED_PREFIXES)
    offset_map: dict[int, list] = {}

    # 1. 대화 블록 (6b 00)
    jp_dialogs = extract_dialogs(jp_data)
    kr_dialogs = extract_kr_dialogs(kr_data)
    for n, jp_lines in enumerate(jp_dialogs):
        if n < len(kr_dialogs):
            _, kr_lines = kr_dialogs[n]
            if kr_lines:
                offset_map[jp_lines[0]['offset']] = kr_lines

    # 2. 레이블 텍스트 (64 01 / 63 08 / 6d 08)
    jp_labeled = extract_labeled_text(jp_data, prefixes)
    kr_labeled = extract_kr_labeled_text(kr_data, prefixes)
    for n, jp_lines in enumerate(jp_labeled):
        if n < len(kr_labeled):
            _, kr_lines = kr_labeled[n]
            if kr_lines:
                offset_map[jp_lines[0]['offset']] = kr_lines

    # 3. MESSAGE.CMD 스토리 대화
    if fname == _JP_ITEM_FILE:
        jp_msg = extract_message_dialog(jp_data)
        kr_msg = extract_kr_message_dialog(kr_data)
        for n, jp_lines in enumerate(jp_msg):
            if n < len(kr_msg):
                _, kr_lines = kr_msg[n]
                if kr_lines:
                    offset_map[jp_lines[0]['offset']] = kr_lines

    return offset_map


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


_COMMITTED_OVERLAY_FILES = {'START.CMD', 'ENDING.CMD'}
_COMMITTED_SHA = '32ac5bc'


def _load_committed_kr(sha):
    """git 커밋에서 translation.json을 읽어 {(file, offset): kr} 딕셔너리 반환."""
    import subprocess
    try:
        out = subprocess.check_output(
            ['git', 'show', f'{sha}:translation/kitan/translation.json'],
            stderr=subprocess.DEVNULL,
        )
        tj = json.loads(out)
        return {
            (d['file'], ln['offset']): ln['kr']
            for d in tj['dialogs']
            for ln in d['lines']
            if ln.get('kr')
        }
    except Exception as e:
        print(f'⚠ 커밋 번역 로드 실패 ({sha}): {e}')
        return {}


def run(kr_dir, json_path, jp_dir=None):
    """
    kr_dir:    KR CMD 파일 디렉터리 (예: original/kitan_kr)
    json_path: translation.json 경로
    jp_dir:    JP CMD 파일 디렉터리 (미지정 시 json_path에서 유추)

    동작:
      1) 모든 kr 초기화
      2) per-extractor auto-match로 KR 게임 참고 텍스트 채우기
      3) START.CMD / ENDING.CMD: 32ac5bc 커밋 번역으로 오버레이 (커밋 우선)
    """
    with open(json_path, encoding='utf-8') as f:
        tj = json.load(f)

    # JP 게임 파일 경로 유추 (translation/{title}/translation.json → original/{title}/data)
    if jp_dir is None:
        title = os.path.basename(os.path.dirname(json_path))
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(json_path))))
        jp_dir = os.path.join(root, 'original', title, 'data')

    # 1) 모든 kr 초기화
    for d in tj['dialogs']:
        for ln in d['lines']:
            ln['kr'] = ''
    for item in tj.get('items', []):
        item['name']['kr'] = ''
        if 'stat' in item:
            item['stat']['kr'] = ''
        for desc in item['desc']:
            desc['kr'] = ''

    # 2) 파일별 JP↔KR 오프셋 매핑 구성 (추출기 종류별 N번째 대응)
    kr_offset_map: dict[str, dict[int, list]] = {}
    for fname in DIALOG_FILES:
        jp_path = os.path.join(jp_dir, fname)
        kr_path = os.path.join(kr_dir, fname)
        if not os.path.exists(jp_path) or not os.path.exists(kr_path):
            continue
        with open(jp_path, 'rb') as f:
            jp_data = decompress(f.read())
        with open(kr_path, 'rb') as f:
            kr_data = decompress(f.read())
        kr_offset_map[fname] = _build_offset_map(jp_data, kr_data, fname)

    # KR 아이템 추출
    kr_items = []
    item_kr_path = os.path.join(kr_dir, ITEM_FILE)
    if os.path.exists(item_kr_path):
        with open(item_kr_path, 'rb') as f:
            kr_items = extract_kr_items(decompress(f.read()))

    # auto-match 적용 (lines[0]에 KR 게임 블록 텍스트)
    auto_filled = auto_skipped = 0
    for jp_dialog in tj['dialogs']:
        fname = jp_dialog['file']
        if fname not in kr_offset_map:
            continue
        jp_offset = jp_dialog['lines'][0]['offset']
        kr_lines = kr_offset_map[fname].get(jp_offset)
        if kr_lines:
            jp_dialog['lines'][0]['kr'] = '　'.join(kr_lines)
            auto_filled += 1
        else:
            auto_skipped += 1

    # 아이템 auto-match
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

    # 3) START.CMD / ENDING.CMD: 커밋 번역 오버레이
    committed = _load_committed_kr(_COMMITTED_SHA)
    overlay_count = 0
    for d in tj['dialogs']:
        if d['file'] not in _COMMITTED_OVERLAY_FILES:
            continue
        for ln in d['lines']:
            key = (d['file'], ln['offset'])
            if key in committed:
                ln['kr'] = committed[key]
                overlay_count += 1

    # 전각 → 반각 정규화 (전체)
    normalized = 0
    for d in tj['dialogs']:
        for ln in d['lines']:
            if ln.get('kr'):
                nkr = _to_halfwidth(ln['kr'])
                if nkr != ln['kr']:
                    ln['kr'] = nkr
                    normalized += 1
    for item in tj.get('items', []):
        for field in (item.get('name'), item.get('stat'), *item.get('desc', [])):
            if field and field.get('kr'):
                nkr = _to_halfwidth(field['kr'])
                if nkr != field['kr']:
                    field['kr'] = nkr
                    normalized += 1

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tj, f, ensure_ascii=False, indent=2)

    print(f'auto-match: {auto_filled}개 채움 / {auto_skipped}개 미매칭')
    print(f'커밋 오버레이 ({_COMMITTED_SHA}, START+ENDING): {overlay_count}개')
    print(f'아이템 채움: {item_filled}개')
    if normalized:
        print(f'전각→반각 정규화: {normalized}개')
    print(f'저장: {json_path}')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: python3 kitan_kr_import.py <kr_dir> <translation.json>')
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
