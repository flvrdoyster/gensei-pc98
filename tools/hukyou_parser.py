"""
환세풍광전 (幻世風狂伝, Compile 1994) CMD 파일 파서
===================================================

사용법:
  python hukyou_parser.py <game_dir>       translation/<title>/translation.json 생성
  python hukyou_parser.py <game_dir> dump  각 CMD 압축 해제본 저장

제어코드 (압축 해제 후):
  65 00 [SJIS lead]  대화 블록 시작
  72 XX              줄바꿈
  6b                 대화 블록 종료
  0f 03              아이템 항목 시작 (MESSAGE.CMD)
  64 02              아이템 설명 줄 구분
  64 XX (XX!=02)     아이템 수치 구분
"""

import json
import os
import sys

from compile_lz import decompress, is_sjis_lead, is_sjis, read_sjis_char


# ─────────────────────────────────────
# 대화 파서
# ─────────────────────────────────────

def extract_dialogs(data):
    dialogs = []
    cur_lines = []
    cur_text = ''
    cur_offset = 0
    in_dialog = False
    i = 0

    while i < len(data):
        if (i + 2 < len(data) and data[i] == 0x65 and data[i + 1] == 0x00
                and (is_sjis_lead(data[i + 2]) or data[i + 2] == 0x68)):
            if in_dialog:
                if cur_text.strip():
                    cur_lines.append({'offset': cur_offset, 'jp': cur_text, 'kr': ''})
                if cur_lines:
                    dialogs.append(cur_lines)
            cur_lines = []
            cur_text = ''
            in_dialog = True
            i += 2
            if data[i] == 0x68:
                i += 2
            cur_offset = i
            continue

        if not in_dialog:
            i += 1
            continue

        if data[i] == 0x6b:
            if cur_text.strip():
                cur_lines.append({'offset': cur_offset, 'jp': cur_text, 'kr': ''})
            if cur_lines:
                dialogs.append(cur_lines)
            cur_lines = []
            cur_text = ''
            in_dialog = False
            i += 1

        elif data[i] == 0x72:
            if cur_text.strip():
                cur_lines.append({'offset': cur_offset, 'jp': cur_text, 'kr': ''})
            cur_text = ''
            i += 2
            cur_offset = i

        elif is_sjis(data, i):
            if not cur_text:
                cur_offset = i
            cur_text += read_sjis_char(data, i)
            i += 2

        else:
            i += 1

    if in_dialog:
        if cur_text.strip():
            cur_lines.append({'offset': cur_offset, 'jp': cur_text, 'kr': ''})
        if cur_lines:
            dialogs.append(cur_lines)

    return dialogs


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
        name, name_off = '', 0
        stat, stat_off = '', 0
        desc_lines = []
        cur, cur_off = '', 0

        def flush():
            nonlocal cur, name, stat, name_off, stat_off
            s = cur.strip()
            cur = ''
            if not s:
                return
            if state == 'name':
                name = s; name_off = cur_off
            elif state == 'stat':
                stat = s; stat_off = cur_off
            else:
                desc_lines.append({'offset': cur_off, 'jp': s, 'kr': ''})

        while i < len(data):
            b = data[i]
            nb = data[i + 1] if i + 1 < len(data) else 0

            if (b == 0x65 and nb == 0x00) or (b == 0x0f and nb == 0x03):
                flush(); break

            if b == 0x64:
                flush()
                state = 'desc' if nb == 0x02 else 'stat'
                i += 2; cur_off = i; continue

            if b == 0x72:
                flush()
                i += 2; cur_off = i; continue

            if is_sjis(data, i):
                if not cur: cur_off = i
                cur += read_sjis_char(data, i)
                i += 2
            else:
                i += 1

        if name:
            entry = {
                'offset': item_start,
                'name': {'offset': name_off, 'jp': name, 'kr': ''},
                'desc': desc_lines,
            }
            if stat:
                entry['stat'] = {'offset': stat_off, 'jp': stat, 'kr': ''}
            items.append(entry)

    return items


# ─────────────────────────────────────
# UI 텍스트 파서 (GF2.COM)
# ─────────────────────────────────────

UI_RANGES = [
    (0x70B6, 0x73C0, 'system'),
    (0x9DF0, 0x9F00, 'status'),
    (0xA1A4, 0xA3B0, 'names'),
]


def _is_valid_ui_text(text):
    if any(ord(c) == 0xFFFD or 0xFF61 <= ord(c) <= 0xFF9F for c in text):
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
                'kr': '',
            })
    return ui


# ─────────────────────────────────────
# JSON 출력
# ─────────────────────────────────────

DIALOG_FILES = [
    'OPEN.CMD', 'STAGE1.CMD', 'STAGE2.CMD', 'STAGE3.CMD',
    'STAGE4.CMD', 'STAGE5.CMD', 'STAGE6.CMD', 'STAGE7.CMD', 'ENDING.CMD',
]
ITEM_FILE = 'MESSAGE.CMD'
UI_FILE = 'GF2.COM'


def generate_json(game_dir, out_path):
    result = {'dialogs': [], 'items': [], 'ui': []}

    for fname in DIALOG_FILES:
        fpath = os.path.join(game_dir, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        dialogs = extract_dialogs(data)
        for idx, lines in enumerate(dialogs):
            result['dialogs'].append({
                'file': fname,
                'index': idx + 1,
                'lines': lines,
            })

    fpath = os.path.join(game_dir, ITEM_FILE)
    if os.path.exists(fpath):
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        result['items'] = extract_items(data)

    fpath = os.path.join(game_dir, UI_FILE)
    if os.path.exists(fpath):
        with open(fpath, 'rb') as f:
            raw = f.read()
        data = decompress(raw)
        result['ui'] = extract_ui(data)

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
