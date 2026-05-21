"""
환세희담 (幻世喜譚, Compile 1995) CMD 파일 파서
================================================

사용법:
  python kitan_parser.py <game_dir>       translation/<title>/translation.json 생성
  python kitan_parser.py <game_dir> dump  각 CMD 압축 해제본 저장

제어코드 (압축 해제 후):
  6b 00              대화 블록 경계 (시작이자 이전 블록 종료)
  72 XX              줄바꿈
  73 XX              페이지 표시/대기 (줄 구분으로 처리)
  76 XX              화면 클리어 + 계속 (줄 구분으로 처리)
  64 XX              항목 구분 (아이템 stat/desc 구분)
  0f 03              아이템 항목 시작 (MESSAGE.CMD, 62 00 이 앞에 붙음)
  13 00              메뉴 선택지 포인터 테이블 시작
"""

import json
import os
import subprocess
import sys

from compile_lz import decompress, is_sjis, read_sjis_char


def _auto_backup(out_path, project_root):
    """translation.json에 미커밋 변경이 있으면 파서 재실행 전 자동 백업."""
    try:
        rel = os.path.relpath(out_path, project_root)
        status = subprocess.run(
            ['git', 'status', '--porcelain', rel],
            cwd=project_root, capture_output=True, text=True,
        )
        if status.stdout.strip():
            subprocess.run(['git', 'add', rel], cwd=project_root, check=True,
                           capture_output=True)
            subprocess.run(
                ['git', 'commit', '-m', '파서 재실행 전 자동 백업'],
                cwd=project_root, check=True, capture_output=True,
            )
            print('  자동 백업 커밋 완료')
    except Exception as e:
        print(f'  ⚠ 자동 백업 실패: {e}')


# ─────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────

def _has_gaiji(data, start, end):
    """바이트 범위에 가이지(0x85XX) 코드가 포함되어 있는지 확인."""
    i = start
    while i < end - 1:
        if data[i] == 0x85:
            return True
        if is_sjis(data, i):
            i += 2
        else:
            i += 1
    return False


def _make_line(cur_offset, cur_end, cur_text, data=None):
    line = {'offset': cur_offset, 'jp': cur_text,
            'jp_len': cur_end - cur_offset, 'kr': ''}
    if data is not None and _has_gaiji(data, cur_offset, cur_end):
        line['gaiji'] = True
    return line


# ─────────────────────────────────────
# 대화 파서
# ─────────────────────────────────────

_DIALOG_LOOKAHEAD = 30  # 6b 00 이후 이 바이트 수 안에 SJIS가 없으면 바이너리 블록으로 간주
# 캐릭터 코드 프리앰블(80 XX 00 + 이벤트 코드)이 최대 29바이트까지 붙을 수 있음


def _has_sjis_nearby(data, start, limit=_DIALOG_LOOKAHEAD):
    """start 오프셋부터 limit 바이트 이내에 유효한 SJIS 문자가 있는지 확인."""
    for j in range(start, min(start + limit, len(data) - 1)):
        if is_sjis(data, j):
            return True
    return False


def extract_dialogs(data):
    """
    6b 00 으로 시작하는 대화 블록 파싱.
    다음 6b 00 이 나올 때까지 SJIS 텍스트를 수집하고,
    72 XX / 73 XX / 76 XX 를 줄 구분자로 처리.

    6b 00 이후 _DIALOG_LOOKAHEAD 바이트 내에 SJIS가 없으면 바이너리
    이벤트 블록으로 간주하고 텍스트 수집을 건너뜀.
    """
    dialogs = []
    cur_lines = []
    cur_text = ''
    cur_offset = 0
    cur_end = 0
    in_dialog = False
    i = 0

    def _flush_line():
        nonlocal cur_text, cur_offset, cur_end
        if len(cur_text.strip()) >= 2:  # 1자 이하는 노이즈로 간주
            cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
        cur_text = ''
        cur_offset = cur_end = i

    def _flush_dialog():
        _flush_line()
        if cur_lines:
            dialogs.append(list(cur_lines))
        cur_lines.clear()

    while i < len(data) - 1:
        # 6b 00 : 블록 경계 (이전 블록 종료 + 새 블록 시작)
        if data[i] == 0x6b and data[i + 1] == 0x00:
            if in_dialog:
                _flush_dialog()
            # 직후 SJIS가 없으면 바이너리 이벤트 블록 — 스킵
            in_dialog = _has_sjis_nearby(data, i + 2)
            i += 2
            cur_text = ''
            cur_offset = cur_end = i
            continue

        if not in_dialog:
            i += 1
            continue

        # 줄바꿈: 72 XX
        if data[i] == 0x72:
            _flush_line()
            i += 2
            cur_offset = cur_end = i
            continue

        # 페이지 구분: 73 XX (표시 대기), 76 XX (화면 클리어)
        if data[i] in (0x73, 0x76):
            _flush_line()
            i += 2
            cur_offset = cur_end = i
            continue

        # 64 00: portrait/캐릭터 코드 + 2바이트 인수 (총 4바이트 오피코드)
        # 인수 바이트가 우연히 SJIS 쌍을 이뤄 텍스트로 오인되는 것 방지
        if data[i] == 0x64 and i + 1 < len(data) and data[i + 1] == 0x00:
            cur_text = ''
            i += min(4, len(data) - i)
            cur_offset = cur_end = i
            continue

        # 메뉴 항목 구분: 64 XX (XX ≠ 00, 02)
        # 64 02 = MESSAGE.CMD desc 구분자; 64 01/03/04 등 = 메뉴 항목 경계
        if data[i] == 0x64 and i + 1 < len(data) and data[i + 1] not in (0x00, 0x02):
            _flush_line()
            i += 2
            cur_offset = cur_end = i
            continue

        # 65 XX (XX ≠ 00): 메뉴 항목 종료 코드 — 줄 구분자로 처리
        if data[i] == 0x65 and i + 1 < len(data) and data[i + 1] != 0x00:
            _flush_line()
            i += 2
            cur_offset = cur_end = i
            continue

        # 6d 00: 항목 표시 종료 코드 (6d 04 [SJIS] 6d 00 65 형식) — flush
        if data[i] == 0x6d and i + 1 < len(data) and data[i + 1] == 0x00:
            _flush_line()
            i += 2
            cur_offset = cur_end = i
            continue

        # 81 65 ('): 다이얼로그 박스 제어 코드 — 번역 대상 아님, 스킵
        if data[i] == 0x81 and i + 1 < len(data) and data[i + 1] == 0x65:
            i += 2
            continue

        # 81 6b (〔): 직후 바이트가 SJIS가 아닐 때만 제어 코드로 스킵
        # 직후에 SJIS 문자가 오면 실제 텍스트 내 괄호 문자 (예: 〔薬草〕)
        if data[i] == 0x81 and i + 1 < len(data) and data[i + 1] == 0x6b:
            if i + 2 >= len(data) or not is_sjis(data, i + 2):
                i += 2
                continue
            # SJIS가 뒤따르면 실제 문자 — 아래 SJIS 처리로 fall-through

        # SJIS 문자
        if is_sjis(data, i):
            if not cur_text:
                cur_offset = i
            cur_text += read_sjis_char(data, i)
            i += 2
            cur_end = i
            continue

        # 그 외 바이너리 바이트 — 스킵 + 텍스트 리셋
        # 바이너리 이벤트 데이터 내 우연한 SJIS 쌍이 실제 텍스트에 붙는 것 방지
        cur_text = ''
        i += 1

    # 파일 끝 처리
    if in_dialog:
        _flush_dialog()

    return dialogs


# ─────────────────────────────────────
# 메뉴 파서 (13 00 선택지 블록)
# ─────────────────────────────────────

def extract_menus(data):
    """13 00 [ptr...] [64 00 ID text 65 00] 형식의 메뉴 선택지 블록 추출."""
    menus = []
    i = 0

    while i < len(data) - 1:
        if data[i] != 0x13 or data[i + 1] != 0x00:
            i += 1
            continue

        base = i + 2  # 포인터 테이블 시작
        if base + 2 > len(data):
            i += 1
            continue

        first_ptr = data[base] | (data[base + 1] << 8)
        if first_ptr <= base or first_ptr >= len(data):
            i += 1
            continue

        n_ptrs = (first_ptr - base) // 2
        if n_ptrs <= 0 or n_ptrs > 10:
            i += 1
            continue

        ptrs = []
        p = base
        for _ in range(n_ptrs):
            ptr = data[p] | (data[p + 1] << 8)
            ptrs.append(ptr)
            p += 2

        lines = []
        for ptr in ptrs:
            j = ptr
            if j + 4 > len(data):
                continue
            if data[j] != 0x64 or data[j + 1] != 0x00:
                continue
            j += 4  # 64 00 [2B ID] 건너뜀
            text = ''
            text_off = j
            text_end = j
            while j < len(data) - 1:
                if data[j] == 0x65 and data[j + 1] == 0x00:
                    break
                if is_sjis(data, j):
                    if not text:
                        text_off = j
                    text += read_sjis_char(data, j)
                    j += 2
                    text_end = j
                else:
                    j += 1
            if text.strip():
                line = {'offset': text_off, 'jp': text,
                        'jp_len': text_end - text_off, 'kr': ''}
                if _has_gaiji(data, text_off, text_end):
                    line['gaiji'] = True
                lines.append(line)

        if lines:
            menus.append(lines)

        i += 1

    return menus


# ─────────────────────────────────────
# 독립 메뉴 항목 파서 (13 00 블록 밖의 64 00 항목)
# ─────────────────────────────────────

def extract_orphan_items(data, captured_offsets):
    """extract_dialogs/extract_menus가 잡지 못한 64 00 [2B ID] [SJIS text] 65 00 항목."""
    items = []
    cur_group = []
    i = 0

    while i < len(data) - 5:
        if data[i] != 0x64 or data[i + 1] != 0x00:
            if cur_group:
                items.append(cur_group)
                cur_group = []
            i += 1
            continue

        j = i + 4
        text = ''
        text_off = j
        text_end = j
        while j < len(data) - 1:
            if data[j] == 0x65 and j + 1 < len(data) and data[j + 1] == 0x00:
                break
            if is_sjis(data, j):
                if not text:
                    text_off = j
                text += read_sjis_char(data, j)
                j += 2
                text_end = j
            else:
                j += 1

        if (text.strip() and len(text) >= 2
                and text_off not in captured_offsets
                and not any(ord(c) == 0xFFFD for c in text)):
            line = {'offset': text_off, 'jp': text,
                    'jp_len': text_end - text_off, 'kr': ''}
            if _has_gaiji(data, text_off, text_end):
                line['gaiji'] = True
            cur_group.append(line)
            i = j + 2 if j < len(data) - 1 else j
        else:
            if cur_group:
                items.append(cur_group)
                cur_group = []
            i += 1

    if cur_group:
        items.append(cur_group)
    return items


# ─────────────────────────────────────
# 아이템/장비 파서 (MESSAGE.CMD)
# ─────────────────────────────────────

def extract_items(data):
    """
    0f 03 으로 시작하는 아이템 항목 파싱 (MESSAGE.CMD).
    62 00 또는 다음 0f 03 에서 항목 종료.
    """
    items = []
    i = 0

    while i < len(data) - 1:
        if data[i] != 0x0f or data[i + 1] != 0x03:
            i += 1
            continue

        item_start = i
        i += 2

        state = 'name'
        name, name_off, name_end = '', 0, 0
        stat, stat_off, stat_end = '', 0, 0
        desc_lines = []
        cur, cur_off, cur_end2 = '', 0, 0

        def flush():
            nonlocal cur, name, stat, name_off, stat_off, name_end, stat_end, cur_end2
            s = cur.strip()
            cur = ''
            if not s:
                return
            if state == 'name':
                name = s; name_off = cur_off; name_end = cur_end2
            elif state == 'stat':
                stat = s; stat_off = cur_off; stat_end = cur_end2
            else:
                dl = {'offset': cur_off, 'jp': s,
                      'jp_len': cur_end2 - cur_off, 'kr': ''}
                if _has_gaiji(data, cur_off, cur_end2):
                    dl['gaiji'] = True
                desc_lines.append(dl)

        while i < len(data) - 1:
            b = data[i]
            nb = data[i + 1]

            # 아이템 종료: 62 00 (다음 항목 프리픽스) 또는 다음 0f 03
            if (b == 0x62 and nb == 0x00) or (b == 0x0f and nb == 0x03):
                flush()
                break

            if b == 0x64:
                flush()
                # 64 02: stat 상태에서만 desc로, 그 외(name 포함)는 stat으로
                # → サムライアーマー 등 name 직후 64 02가 오는 아이템 처리
                state = 'desc' if (nb == 0x02 and state == 'stat') else 'stat'
                i += 2; cur_off = cur_end2 = i; continue

            if b == 0x72:
                flush()
                # name/stat 직후 줄바꿈 = 이후는 설명 줄
                # → 64 없이 72 01로 이름과 설명을 구분하는 아이템(薬草 등) 처리
                if state in ('stat', 'name'):
                    state = 'desc'
                i += 2; cur_off = cur_end2 = i; continue

            if is_sjis(data, i):
                if not cur:
                    cur_off = i
                cur += read_sjis_char(data, i)
                i += 2
                cur_end2 = i
            else:
                i += 1

        if name:
            name_line = {'offset': name_off, 'jp': name,
                         'jp_len': name_end - name_off, 'kr': ''}
            if _has_gaiji(data, name_off, name_end):
                name_line['gaiji'] = True
            entry = {
                'offset': item_start,
                'name': name_line,
                'desc': desc_lines,
            }
            if stat:
                stat_line = {'offset': stat_off, 'jp': stat,
                             'jp_len': stat_end - stat_off, 'kr': ''}
                if _has_gaiji(data, stat_off, stat_end):
                    stat_line['gaiji'] = True
                entry['stat'] = stat_line
            items.append(entry)

    return items


# ─────────────────────────────────────
# 레이블 텍스트 파서 (64 01 / 63 08 / 6d 08 + 65 형식)
# ─────────────────────────────────────

def extract_labeled_text(data, prefixes):
    """
    XX YY [SJIS...] 65 형식 레이블 텍스트 추출.

    prefixes: [(b0, b1), ...] — 대상 프리픽스 목록.
    연속된 동일 prefix 항목을 하나의 그룹으로 묶음.
    prefix 사이에 끼어드는 64 XX 제어코드는 스킵.
    """
    if not prefixes:
        return []

    prefix_set = set(prefixes)
    items = []
    cur_group = []
    cur_prefix = None
    i = 0

    while i < len(data) - 1:
        # 현재 위치에서 prefix 매칭 시도
        matched = None
        for p0, p1 in prefix_set:
            if data[i] == p0 and data[i + 1] == p1:
                matched = (p0, p1)
                break

        if matched is None:
            # prefix 아닌 바이트 → 현재 그룹 마감
            if cur_group:
                items.append(cur_group)
                cur_group = []
                cur_prefix = None
            i += 1
            continue

        # prefix 변경 시 이전 그룹 마감
        if matched != cur_prefix and cur_group:
            items.append(cur_group)
            cur_group = []
        cur_prefix = matched

        # prefix 직후부터 65 (종료) 까지 SJIS 수집
        j = i + 2
        text = ''
        text_off = j
        text_end = j

        while j < len(data):
            if data[j] == 0x65:
                # 2바이트 오피코드 (65 XX)
                j += 2 if j + 1 < len(data) else 1
                break
            # 임베디드 제어코드 (64 XX) — 스킵
            if data[j] == 0x64 and j + 1 < len(data):
                j += 2
                continue
            if is_sjis(data, j):
                if not text:
                    text_off = j
                text += read_sjis_char(data, j)
                j += 2
                text_end = j
            else:
                j += 1

        if (len(text.strip()) >= 2  # 1자 이하는 노이즈
                and not any(ord(c) == 0xFFFD for c in text)):
            line = {'offset': text_off, 'jp': text,
                    'jp_len': text_end - text_off, 'kr': ''}
            if _has_gaiji(data, text_off, text_end):
                line['gaiji'] = True
            cur_group.append(line)
            i = j
        else:
            # 매칭 실패 — 그룹 마감 후 1바이트 전진
            if cur_group:
                items.append(cur_group)
                cur_group = []
                cur_prefix = None
            i += 1

    if cur_group:
        items.append(cur_group)

    return items


# ─────────────────────────────────────
# MESSAGE.CMD 스토리 대화 파서 (00 02 블록)
# ─────────────────────────────────────

_MSG_DIALOG_START = 0x1290  # MESSAGE.CMD 스토리 대화 시작 오프셋


def extract_message_dialog(data):
    """
    MESSAGE.CMD 전용 스토리 대화 추출.

    0x1290부터 EOF까지 순차 스캔.
    블록 형식: [SJIS...] (72 XX 줄바꿈) ... 65 (블록 종료)
    블록 사이에 00 02 프리픽스는 섹션 최초에만 존재하며, 이후 블록은
    직전 65 종료 직후부터 시작. 비-SJIS 바이트는 스킵 (텍스트 리셋 없음).
    """
    blocks = []
    i = _MSG_DIALOG_START

    cur_lines = []
    cur_text = ''
    cur_offset = i
    cur_end = i

    while i < len(data):
        b = data[i]

        # 65: 블록 종료
        if b == 0x65:
            if cur_text.strip():
                cur_lines.append(
                    _make_line(cur_offset, cur_end, cur_text, data))
                cur_text = ''
            if cur_lines:
                blocks.append(cur_lines)
                cur_lines = []
            i += 1
            cur_offset = cur_end = i
            continue

        # 72 XX: 줄바꿈
        if b == 0x72:
            if cur_text.strip():
                cur_lines.append(
                    _make_line(cur_offset, cur_end, cur_text, data))
                cur_text = ''
            i += 2
            cur_offset = cur_end = i
            continue

        # SJIS
        if is_sjis(data, i):
            if not cur_text:
                cur_offset = i
            cur_text += read_sjis_char(data, i)
            i += 2
            cur_end = i
            continue

        # 그 외 바이트 (제어코드, 반각가나 등) — 텍스트 리셋 없이 스킵
        # 이 섹션은 순수 텍스트 영역이므로 바이너리 이벤트 블록 없음
        i += 1

    # EOF 처리
    if cur_text.strip():
        cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
    if cur_lines:
        blocks.append(cur_lines)

    return blocks


# ─────────────────────────────────────
# bare SJIS+65 파서 (SC6A 층수 이름 등)
# ─────────────────────────────────────

def extract_bare_sjis65(data, captured_offsets):
    """
    순수 SJIS 연속 + 65 종료 패턴 스캔.

    중간에 바이너리 바이트 없이 SJIS만 이어지다가 65로 끝나는 패턴.
    주 용도: SC6A.CMD 층수 이름 (　４階　 등).
    captured_offsets 에 이미 있는 오프셋은 제외.
    """
    items = []
    i = 0

    while i < len(data) - 1:
        if not is_sjis(data, i):
            i += 1
            continue

        start = i
        text = ''
        text_off = i
        text_end = i
        pure = True
        j = i

        while j < len(data):
            if data[j] == 0x65:
                j += 1  # 65 는 1바이트로 취급
                break
            if is_sjis(data, j):
                text += read_sjis_char(data, j)
                text_end = j + 2
                j += 2
            else:
                # 순수 SJIS 연속이 깨짐
                pure = False
                break
        else:
            pure = False  # 65 종료 없이 EOF

        if (pure and text.strip() and len(text) >= 2
                and not any(ord(c) == 0xFFFD for c in text)):
            if text_off not in captured_offsets:
                line = {'offset': text_off, 'jp': text,
                        'jp_len': text_end - text_off, 'kr': ''}
                if _has_gaiji(data, text_off, text_end):
                    line['gaiji'] = True
                items.append([line])
            i = j  # 캡처 여부 무관하게 런 전체를 건너뜀
        else:
            i = start + 1

    return items


# ─────────────────────────────────────
# JSON 출력
# ─────────────────────────────────────

DIALOG_FILES = [
    'START.CMD',
    'SC1A.CMD', 'SC1B.CMD',
    'SC2A.CMD', 'SC2B.CMD', 'SC2C.CMD', 'SC2D.CMD', 'SC2E.CMD', 'SC2F.CMD', 'SC2G.CMD',
    'SC3A.CMD', 'SC3B.CMD', 'SC3C.CMD', 'SC3D.CMD', 'SC3E.CMD',
    'SC4A.CMD', 'SC4B.CMD', 'SC4C.CMD', 'SC4D.CMD', 'SC4E.CMD',
    'SC5A.CMD', 'SC5B.CMD', 'SC5C.CMD', 'SC5D.CMD', 'SC5E.CMD', 'SC5F.CMD',
    'SC6A.CMD', 'SC6B.CMD', 'SC6C.CMD', 'SC6D.CMD',
    'SC7A.CMD',
    'PARTY2.CMD', 'PARTY3.CMD', 'PARTY4.CMD', 'PARTY6.CMD', 'PARTY7.CMD',
    'BTL_PC.CMD',
    'ENDING.CMD',
    'MESSAGE.CMD',
]
ITEM_FILE = 'MESSAGE.CMD'

# 파일별 레이블 텍스트 프리픽스 (extract_labeled_text 용)
_DEFAULT_LABELED_PREFIXES = [(0x64, 0x01)]
_LABELED_PREFIXES = {
    'ENDING.CMD': [(0x63, 0x08), (0x64, 0x01)],
    **{p: [(0x6d, 0x08), (0x64, 0x01)]
       for p in ('PARTY2.CMD', 'PARTY3.CMD', 'PARTY4.CMD',
                 'PARTY6.CMD', 'PARTY7.CMD')},
    'MESSAGE.CMD': [],  # extract_message_dialog 사용
}

# bare SJIS+65 스캔 적용 파일
_BARE_SJIS65_FILES = {'SC6A.CMD'}


def generate_json(game_dir, out_path):
    result = {'dialogs': [], 'items': []}

    # 아이템 먼저 추출 — MESSAGE.CMD 대화 중복 제외용
    item_offsets = set()
    fpath = os.path.join(game_dir, ITEM_FILE)
    if os.path.exists(fpath):
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        result['items'] = extract_items(data)
        for item in result['items']:
            item_offsets.add(item['name']['offset'])
            if 'stat' in item:
                item_offsets.add(item['stat']['offset'])
            for desc in item['desc']:
                item_offsets.add(desc['offset'])

    for fname in DIALOG_FILES:
        fpath = os.path.join(game_dir, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        dialogs = extract_dialogs(data)
        menus = extract_menus(data)

        # 레이블 텍스트 (64 01 세이브/메뉴, 63 08 크레딧, 6d 08 적 이름)
        prefixes = _LABELED_PREFIXES.get(fname, _DEFAULT_LABELED_PREFIXES)
        labeled = extract_labeled_text(data, prefixes)

        # MESSAGE.CMD: 스토리 대화 (00 02 블록)
        msg_dialogs = extract_message_dialog(data) if fname == ITEM_FILE else []

        # MESSAGE.CMD: 아이템과 중복되는 오프셋 제외
        exclude = item_offsets if fname == ITEM_FILE else set()

        file_idx = 0
        all_blocks = dialogs + menus + labeled + msg_dialogs

        # SC6A.CMD: bare SJIS+65 층수 이름 추가
        if fname in _BARE_SJIS65_FILES:
            pre_captured = {ln['offset'] for blk in all_blocks for ln in blk}
            all_blocks += extract_bare_sjis65(data, pre_captured)

        all_blocks.sort(key=lambda b: b[0]['offset'] if b else 0)
        seen = set()
        for lines in all_blocks:
            clean = [ln for ln in lines
                     if ln['offset'] not in seen and ln['offset'] not in exclude]
            if clean:
                for ln in clean:
                    seen.add(ln['offset'])
                file_idx += 1
                result['dialogs'].append({
                    'file': fname,
                    'index': file_idx,
                    'lines': clean,
                })

    if os.path.exists(out_path):
        _auto_backup(out_path, project_root)

        with open(out_path, encoding='utf-8') as f:
            old = json.load(f)

        from collections import Counter
        jp_count = Counter(
            (d['file'], l['jp'])
            for d in old.get('dialogs', [])
            for l in d['lines']
        )
        kr_map = {}
        jp_at = {}
        kr_jp_map = {}
        tag_map = {}
        tag_jp_map = {}
        for dialog in old.get('dialogs', []):
            for line in dialog['lines']:
                fkey = (dialog['file'], line['offset'])
                jkey = (dialog['file'], line['jp'])
                jp_at[fkey] = line['jp']
                kr = line.get('kr', '')
                if kr:
                    kr_map[fkey] = kr
                    if jp_count[jkey] == 1:
                        kr_jp_map[jkey] = kr
                if line.get('tag'):
                    tag_map[fkey] = line['tag']
                    if jp_count[jkey] == 1:
                        tag_jp_map[jkey] = line['tag']
        for item in old.get('items', []):
            if item['name'].get('kr', ''):
                kr_map[('item_name', item['name']['offset'])] = item['name']['kr']
            if 'stat' in item and item['stat'].get('kr', ''):
                kr_map[('item_stat', item['stat']['offset'])] = item['stat']['kr']
            for desc in item['desc']:
                if desc.get('kr', ''):
                    kr_map[('item_desc', desc['offset'])] = desc['kr']

        restored = fallback = 0
        for dialog in result['dialogs']:
            for line in dialog['lines']:
                fkey = (dialog['file'], line['offset'])
                jkey = (dialog['file'], line['jp'])
                kr = kr_map.get(fkey)
                if kr and jp_at.get(fkey) != line['jp']:
                    kr = None
                if kr:
                    line['kr'] = kr
                    restored += 1
                elif kr_jp_map.get(jkey):
                    line['kr'] = kr_jp_map[jkey]
                    fallback += 1
                tag = tag_map.get(fkey) if jp_at.get(fkey) == line['jp'] else None
                tag = tag or tag_jp_map.get(jkey)
                if tag:
                    line['tag'] = tag
        for item in result['items']:
            kr = kr_map.get(('item_name', item['name']['offset']), '')
            if kr:
                item['name']['kr'] = kr
                restored += 1
            if 'stat' in item:
                kr = kr_map.get(('item_stat', item['stat']['offset']), '')
                if kr:
                    item['stat']['kr'] = kr
                    restored += 1
            for desc in item['desc']:
                kr = kr_map.get(('item_desc', desc['offset']), '')
                if kr:
                    desc['kr'] = kr
                    restored += 1

        total_kr = sum(1 for d in old.get('dialogs', [])
                       for l in d['lines'] if l.get('kr', '').strip())
        missed = total_kr - restored - fallback
        print(f'  기존 번역 보존: {restored}건 (오프셋 일치) + {fallback}건 (텍스트 fallback)'
              + (f' | ⚠ 미복원 {missed}건' if missed > 0 else ''))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    d = len(result['dialogs'])
    l = sum(len(e['lines']) for e in result['dialogs'])
    it = len(result['items'])
    print(f'저장: {out_path}')
    print(f'  대화 블록: {d}개 / 대사 줄: {l}줄 / 아이템: {it}개')


def dump_decompressed(game_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for fname in os.listdir(game_dir):
        if not fname.upper().endswith('.CMD'):
            continue
        with open(os.path.join(game_dir, fname), 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        out_path = os.path.join(out_dir, fname)
        with open(out_path, 'wb') as f:
            f.write(data)
        print(f'{fname}: {len(raw)} -> {len(data)} bytes')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python kitan_parser.py <game_dir> [dump]')
        sys.exit(1)

    game_dir = sys.argv[1]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 데이터가 original/kitan/data/ 하위에 있으므로 basename이 'data'가 됨 — 상위 디렉터리로 올라감
    _base = os.path.basename(os.path.normpath(game_dir))
    title = os.path.basename(os.path.dirname(os.path.normpath(game_dir))) if _base == 'data' else _base

    if len(sys.argv) >= 3 and sys.argv[2] == 'dump':
        dump_decompressed(game_dir, os.path.join(project_root, 'build', title, '_decompressed'))
    else:
        out_path = os.path.join(project_root, 'translation', title, 'translation.json')
        generate_json(game_dir, out_path)
