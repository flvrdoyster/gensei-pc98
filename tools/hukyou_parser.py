"""
환세풍광전 (幻世風狂伝, Compile 1994) CMD 파일 파서
===================================================

사용법:
  python hukyou_parser.py <game_dir>       translation/<title>/translation.json 생성
  python hukyou_parser.py <game_dir> dump  각 CMD 압축 해제본 저장

제어코드 (압축 해제 후):
  65 00/01 [SJIS/ctrl]  대화 블록 시작 (01 = 이벤트/보물상자, ctrl = 62-76)
  72 XX              줄바꿈
  6b                 대화 블록 종료
  64 00 [2B] [text]  메뉴/선택지 항목 (65 00으로 종료)
  0f 03              아이템 항목 시작 (MESSAGE.CMD)
  64 02              아이템 설명 줄 구분
  64 XX (XX!=02)     아이템 수치 구분
"""

import json
import os
import subprocess
import sys

from compile_lz import decompress, is_sjis_lead, is_sjis, read_sjis_char


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
                ['git', 'commit', '-m', f'파서 재실행 전 자동 백업'],
                cwd=project_root, check=True, capture_output=True,
            )
            print('  자동 백업 커밋 완료')
    except Exception as e:
        print(f'  ⚠ 자동 백업 실패: {e}')


# ─────────────────────────────────────
# 대화 파서
# ─────────────────────────────────────

def _has_halfwidth(data, start, end):
    """바이트 범위에 반각(0x85XX) 코드가 포함되어 있는지 확인."""
    i = start
    while i < end - 1:
        if data[i] == 0x85:
            return True
        if is_sjis_lead(data[i]):
            i += 2
        else:
            i += 1
    return False


def _make_line(cur_offset, cur_end, cur_text, data=None):
    line = {'offset': cur_offset, 'jp': cur_text,
            'jp_len': cur_end - cur_offset, 'kr': ''}
    if data is not None and _has_halfwidth(data, cur_offset, cur_end):
        line['halfwidth'] = True
    return line


def extract_dialogs(data):
    dialogs = []
    cur_lines = []
    cur_text = ''
    cur_offset = 0
    cur_end = 0
    in_dialog = False
    i = 0

    while i < len(data):
        is_65_start = (i + 2 < len(data) and data[i] == 0x65 and data[i + 1] in (0x00, 0x01)
                       and (is_sjis_lead(data[i + 2]) or data[i + 2] == 0x68
                            or (not in_dialog
                                and data[i + 2] in (0x62, 0x63, 0x64, 0x66, 0x76))))
        is_68_start = (not is_65_start and i + 3 < len(data)
                       and data[i] == 0x68 and is_sjis_lead(data[i + 2])
                       and data[i + 3] != 0x6b)

        if is_65_start or is_68_start:
            if in_dialog:
                if cur_text.strip():
                    cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
                if cur_lines:
                    dialogs.append(cur_lines)
            cur_lines = []
            cur_text = ''
            in_dialog = True
            if is_65_start:
                i += 2
                if data[i] == 0x68:
                    i += 2
            else:
                i += 2
            cur_offset = cur_end = i
            continue

        if not in_dialog:
            i += 1
            continue

        if data[i] == 0x6b:
            if cur_text.strip():
                cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
            if cur_lines:
                dialogs.append(cur_lines)
            cur_lines = []
            cur_text = ''
            in_dialog = False
            i += 1

        elif data[i] == 0x72:
            if cur_text.strip():
                cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
            cur_text = ''
            i += 2
            cur_offset = cur_end = i

        elif data[i] == 0x64:
            # 0x64 N [제어바이트] [텍스트] 0x65 0x00 서브항목
            if cur_text.strip():
                cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
            cur_text = ''
            i += 2  # 0x64 + N 건너뜀
            while i < len(data) and data[i] < 0x81:
                i += 1  # 제어바이트 건너뜀 (SJIS 시작 전까지)
            cur_offset = cur_end = i

        elif data[i] == 0x45 and i + 1 < len(data) and data[i + 1] == 0x00:
            # 텍스트 서브항목 섹션 종료 마커 — 이후 0x64 블록은 바이너리 데이터
            if cur_text.strip():
                cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
            cur_text = ''
            i += 2
            # 0x6B(dialog end)까지 건너뜀
            while i < len(data) and data[i] != 0x6b:
                i += 1

        elif data[i] == 0x65 and i + 1 < len(data) and data[i + 1] == 0x00:
            # 서브항목 종료자 (다이얼로그 내부 0x65 0x00)
            if cur_text.strip():
                cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
            cur_text = ''
            i += 2
            cur_offset = cur_end = i

        elif is_sjis(data, i):
            if not cur_text:
                cur_offset = i
            cur_text += read_sjis_char(data, i)
            i += 2
            cur_end = i

        else:
            i += 1

    if in_dialog:
        if cur_text.strip():
            cur_lines.append(_make_line(cur_offset, cur_end, cur_text, data))
        if cur_lines:
            dialogs.append(cur_lines)

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
                if _has_halfwidth(data, text_off, text_end):
                    line['halfwidth'] = True
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
            if _has_halfwidth(data, text_off, text_end):
                line['halfwidth'] = True
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
                if _has_halfwidth(data, cur_off, cur_end2):
                    dl['halfwidth'] = True
                desc_lines.append(dl)

        while i < len(data):
            b = data[i]
            nb = data[i + 1] if i + 1 < len(data) else 0

            if (b == 0x65 and nb == 0x00) or (b == 0x0f and nb == 0x03):
                flush(); break

            if b == 0x64:
                flush()
                state = 'desc' if nb == 0x02 else 'stat'
                i += 2; cur_off = cur_end2 = i; continue

            if b == 0x72:
                flush()
                i += 2; cur_off = cur_end2 = i; continue

            if is_sjis(data, i):
                if not cur: cur_off = i
                cur += read_sjis_char(data, i)
                i += 2
                cur_end2 = i
            else:
                i += 1

        if name:
            name_line = {'offset': name_off, 'jp': name,
                         'jp_len': name_end - name_off, 'kr': ''}
            if _has_halfwidth(data, name_off, name_end):
                name_line['halfwidth'] = True
            entry = {
                'offset': item_start,
                'name': name_line,
                'desc': desc_lines,
            }
            if stat:
                stat_line = {'offset': stat_off, 'jp': stat,
                             'jp_len': stat_end - stat_off, 'kr': ''}
                if _has_halfwidth(data, stat_off, stat_end):
                    stat_line['halfwidth'] = True
                entry['stat'] = stat_line
            items.append(entry)

    return items


# ─────────────────────────────────────
# UI 텍스트 파서 (GF2.COM)
# ─────────────────────────────────────

UI_RANGES = [
    (0x70B6, 0x73C0, 'system'),
    (0x9DF0, 0x9F00, 'status'),
    (0xA1A4, 0xA3B0, 'names'),
    (0x0E980, 0x0EA00, 'battle'),  # アイテム, MISS 등 전투 UI
]


def _is_valid_ui_text(text):
    if any(ord(c) == 0xFFFD for c in text):
        return False
    if len(text) == 1 and text not in '炎氷雷毒':
        return False
    return True


def extract_ui(data):
    ui = []
    for start, end, category in UI_RANGES:
        i = start
        cur = ''
        cur_off = 0
        while i < end:
            if is_sjis(data, i):
                if not cur:
                    cur_off = i
                cur += read_sjis_char(data, i)
                i += 2
            else:
                if cur and _is_valid_ui_text(cur):
                    ui.append({
                        'offset': cur_off,
                        'category': category,
                        'jp': cur,
                        'jp_len': i - cur_off,
                        'kr': '',
                    })
                    cur = ''
                elif cur:
                    cur = ''
                i += 1
        if cur and _is_valid_ui_text(cur):
            ui.append({
                'offset': cur_off,
                'category': category,
                'jp': cur,
                'jp_len': i - cur_off,
                'kr': '',
            })
    return ui


# ─────────────────────────────────────
# JSON 출력
# ─────────────────────────────────────

DIALOG_FILES = [
    'OPEN.CMD', 'STAGE1.CMD', 'STAGE2.CMD', 'STAGE3.CMD',
    'STAGE4.CMD', 'STAGE5.CMD', 'STAGE6.CMD', 'STAGE7.CMD', 'ENDING.CMD',
    'MESSAGE.CMD',
]
ITEM_FILE = 'MESSAGE.CMD'
UI_FILE = 'GF2.COM'


def generate_json(game_dir, out_path):
    result = {'dialogs': [], 'items': [], 'ui': []}

    # 아이템을 먼저 추출 — MESSAGE.CMD 대화에서 아이템 오프셋 제외용
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
        captured = set()
        for lines in dialogs + menus:
            for line in lines:
                captured.add(line['offset'])
        orphans = extract_orphan_items(data, captured)

        # MESSAGE.CMD: 아이템과 중복되는 오프셋 제외
        exclude = item_offsets if fname == ITEM_FILE else set()

        file_idx = 0
        all_blocks = dialogs + menus + orphans
        # 오프셋 순 정렬
        all_blocks.sort(key=lambda b: b[0]['offset'] if b else 0)
        # 중복 오프셋 제거
        seen = set()
        for lines in all_blocks:
            clean = [ln for ln in lines if ln['offset'] not in seen and ln['offset'] not in exclude]
            if clean:
                for ln in clean:
                    seen.add(ln['offset'])
                file_idx += 1
                result['dialogs'].append({
                    'file': fname,
                    'index': file_idx,
                    'lines': clean,
                })

    fpath = os.path.join(game_dir, UI_FILE)
    if os.path.exists(fpath):
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        result['ui'] = extract_ui(data)

    if os.path.exists(out_path):
        # 미커밋 변경 자동 백업
        _auto_backup(out_path, project_root)

        with open(out_path, encoding='utf-8') as f:
            old = json.load(f)

        # 복원 키 전략:
        #   1차: (file, offset) + JP 텍스트 일치 검증
        #        — 오프셋이 같아도 JP가 다르면 적용 안 함 (오염 방지)
        #   2차: (file, jp) 텍스트 fallback
        #        — 단, 같은 파일 내 동일 JP 텍스트가 2회 이상이면 미사용
        #          (어느 위치에 적용할지 알 수 없어 오염 위험)
        from collections import Counter
        jp_count = Counter(
            (d['file'], l['jp'])
            for d in old.get('dialogs', [])
            for l in d['lines']
        )
        kr_map = {}       # (file, offset) → kr
        jp_at = {}        # (file, offset) → jp  (검증용)
        kr_jp_map = {}    # (file, jp)     → kr  (fallback)
        tag_map = {}
        tag_jp_map = {}
        for dialog in old.get('dialogs', []):
            for line in dialog['lines']:
                fkey = (dialog['file'], line['offset'])
                jkey = (dialog['file'], line['jp'])
                jp_at[fkey] = line['jp']
                if line['kr']:
                    kr_map[fkey] = line['kr']
                    if jp_count[jkey] == 1:
                        kr_jp_map[jkey] = line['kr']
                if line.get('tag'):
                    tag_map[fkey] = line['tag']
                    if jp_count[jkey] == 1:
                        tag_jp_map[jkey] = line['tag']
        for item in old.get('items', []):
            if item['name']['kr']:
                kr_map[('item_name', item['name']['offset'])] = item['name']['kr']
            if 'stat' in item and item['stat']['kr']:
                kr_map[('item_stat', item['stat']['offset'])] = item['stat']['kr']
            for desc in item['desc']:
                if desc['kr']:
                    kr_map[('item_desc', desc['offset'])] = desc['kr']
        for entry in old.get('ui', []):
            if entry['kr']:
                kr_map[('ui', entry['offset'])] = entry['kr']

        restored = fallback = 0
        for dialog in result['dialogs']:
            for line in dialog['lines']:
                fkey = (dialog['file'], line['offset'])
                jkey = (dialog['file'], line['jp'])
                kr = kr_map.get(fkey)
                # 오프셋 일치 시 JP 텍스트도 검증 — 다르면 오염이므로 스킵
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
        for entry in result['ui']:
            kr = kr_map.get(('ui', entry['offset']), '')
            if kr:
                entry['kr'] = kr
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
    u = len(result['ui'])
    print(f'저장: {out_path}')
    print(f'  대화 블록: {d}개 / 대사 줄: {l}줄 / 아이템: {it}개 / UI: {u}개')


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
        print('usage: python hukyou_parser.py <game_dir> [dump]')
        sys.exit(1)

    game_dir = sys.argv[1]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    title = os.path.basename(os.path.normpath(game_dir))

    if len(sys.argv) >= 3 and sys.argv[2] == 'dump':
        dump_decompressed(game_dir, os.path.join(project_root, 'build', title, '_decompressed'))
    else:
        out_path = os.path.join(project_root, 'translation', title, 'translation.json')
        generate_json(game_dir, out_path)
