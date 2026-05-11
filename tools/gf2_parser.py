"""
환세풍광전 (Compile Inc., 1994) CMD 파일 파서
================================================
같은 개발사(Compile) 동 시기 PC-98 게임에서 응용 가능.

파일 포맷 개요:
  - 실행파일(GF2.COM): 자가 압축(self-extracting), LZ 계열
  - 스크립트(.CMD): 런타임에 동일 LZ 알고리즘으로 압축 해제 후 인터프리트
  - 텍스트 인코딩: Shift-JIS

사용법:
  python gf2_parser.py <game_dir>       translation.json 생성
  python gf2_parser.py <game_dir> dump  각 CMD 압축 해제본 저장

출력 형식 (translation.json):
  {
    "dialogs": [
      {
        "file": "STAGE1.CMD",
        "index": 1,
        "lines": [
          {"offset": 18462, "jp": "「あら　いらっしゃい！", "kr": ""},
          {"offset": 18484, "jp": "　今日はどーしたの？",   "kr": ""}
        ]
      }, ...
    ],
    "items": [
      {
        "offset": 96,
        "name": {"offset": 98,  "jp": "鉄の剣",     "kr": ""},
        "stat": {"offset": 106, "jp": "攻撃力＋２０", "kr": ""},
        "desc": [
          {"offset": 120, "jp": "鉄製の長剣",            "kr": ""},
          {"offset": 132, "jp": "量産品のため",           "kr": ""},
          {"offset": 146, "jp": "あまり上等とは言えない",  "kr": ""}
        ]
      }, ...
    ]
  }

  offset: 압축 해제 후 바이트 오프셋. 재삽입 스크립트에서 직접 참조.
"""

import json
import os
import sys


# ─────────────────────────────────────────
# 1. LZ 압축 해제
# ─────────────────────────────────────────

def decompress(data, start=0):
    """
    환세풍광전 LZ 압축 해제.

    알고리즘:
      al = *src++
      if al == 0: 종료
      if al & 0x80:  <- back-reference
        length = (al & 0x7f) + 3
        offset = *src++ + 1
        copy 'length' bytes from (output[-offset])
      else:          <- literal
        copy 'al' bytes from src

    GF2.COM 자가 압축(0x100~0x170)과 CMD 파일 런타임 압축이
    동일한 알고리즘을 사용.

    다른 Compile 타이틀에서도 동일 알고리즘 확인 가능성 높음.
    시그니처: COM 파일 0x100이 0xFC(CLD)로 시작하고
    0x113~0x114가 F3 A5(REP MOVSW)이면 동일 구조로 추정.
    """
    output = bytearray()
    i = start
    while i < len(data):
        al = data[i]; i += 1
        if al == 0:
            break
        if al & 0x80:
            length = (al & 0x7f) + 3
            if i >= len(data):
                break
            offset = data[i] + 1; i += 1
            for _ in range(length):
                pos = len(output) - offset
                output.append(output[pos] if pos >= 0 else 0)
        else:
            length = al
            output.extend(data[i:i + length])
            i += length
    return output


# ─────────────────────────────────────────
# 2. Shift-JIS 유틸
# ─────────────────────────────────────────

def is_sjis_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def is_sjis(data, i):
    if i + 1 >= len(data):
        return False
    b = data[i]
    if is_sjis_lead(b):
        b2 = data[i + 1]
        return 0x40 <= b2 <= 0xFC and b2 != 0x7F
    return False


def read_sjis_char(data, i):
    return data[i:i + 2].decode('shift_jis', errors='replace')


# ─────────────────────────────────────────
# 3. 대화 파서
# ─────────────────────────────────────────
#
# 제어코드 (압축 해제 후 기준):
#   0x65 0x00 [SJIS lead]  대화 블록 시작 (새 화자 또는 새 장면)
#   0x72 0x??              줄바꿈
#   0x6b                   대화 블록 명시적 종료 (STAGE 파일에서 주로 사용)
#
# 대화 블록 종료 조건:
#   1. 0x6b 명시적 종료
#   2. 다음 0x65 0x00 [SJIS] 등장 (ENDING/MESSAGE에서 주로 사용)
#   3. 0x65 0x00 [non-SJIS] 등장 (비대화 데이터 시작)
#
# 파일별 특징:
#   STAGE1~7.CMD  대화가 0x6b로 명시 종료
#   ENDING.CMD    대화가 연속으로 이어짐 (0x6b 없음)
#   OPEN.CMD      혼합

def extract_dialogs(data):
    """
    반환:
      [
        [{"offset": int, "jp": str, "kr": ""}, ...],
        ...
      ]
    offset: 압축 해제 후 해당 줄 텍스트의 시작 오프셋.
    첫 줄이 캐릭터명인 경우도 포함 (구분하지 않음).
    캐릭터명 분리가 필요하면 '「'로 시작하는 줄을 대사로 판별.
    """
    dialogs = []
    cur_lines = []
    cur_text = ''
    cur_offset = 0
    in_dialog = False
    i = 0

    while i < len(data):
        if (i + 2 < len(data) and data[i] == 0x65 and
                data[i + 1] == 0x00 and is_sjis_lead(data[i + 2])):
            if in_dialog:
                if cur_text.strip():
                    cur_lines.append({'offset': cur_offset, 'jp': cur_text, 'kr': ''})
                if cur_lines:
                    dialogs.append(cur_lines)
            cur_lines = []
            cur_text = ''
            in_dialog = True
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


# ─────────────────────────────────────────
# 4. 아이템/장비 설명 파서 (MESSAGE.CMD 전용)
# ─────────────────────────────────────────
#
# 제어코드:
#   0x0f 0x03              아이템 항목 시작
#   0x64 0x02              설명 줄 구분자
#   0x64 0x?? (??!=0x02)   수치(공격력/방어력 등) 구분자
#   0x72 0x01              줄바꿈
#   0x65 0x00              아이템 종료 / 다음 아이템
#
# 구조:
#   [0f 03] 아이템명 [64 ??] 수치(있으면) [72 01]
#   [64 02] 설명줄 [64 02] 설명줄 ... [65 00 62 00]
#
# 주의: 일부 아이템은 수치 구분자(64 0c/0a 등) 없이
#        바로 [64 02]로 시작. stat 필드가 비어도 정상.

def extract_items(data):
    """
    반환:
      [
        {
          "offset": int,
          "name": {"offset": int, "jp": str, "kr": ""},
          "stat": {"offset": int, "jp": str, "kr": ""},  # 없으면 키 자체 없음
          "desc": [{"offset": int, "jp": str, "kr": ""}, ...]
        },
        ...
      ]
    stat이 없으면 소모품/열쇠 아이템 등 수치 없는 항목.
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


# ─────────────────────────────────────────
# 5. JSON 출력
# ─────────────────────────────────────────

DIALOG_FILES = [
    'OPEN.CMD', 'STAGE1.CMD', 'STAGE2.CMD', 'STAGE3.CMD',
    'STAGE4.CMD', 'STAGE5.CMD', 'STAGE6.CMD', 'STAGE7.CMD', 'ENDING.CMD',
]
ITEM_FILE = 'MESSAGE.CMD'


def generate_json(game_dir, out_path):
    result = {'dialogs': [], 'items': []}

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
        print('usage: python gf2_parser.py <game_dir> [dump]')
        sys.exit(1)
    game_dir = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == 'dump':
        dump_decompressed(game_dir, os.path.join(game_dir, '_decompressed'))
    else:
        generate_json(game_dir, os.path.join(game_dir, 'translation.json'))
