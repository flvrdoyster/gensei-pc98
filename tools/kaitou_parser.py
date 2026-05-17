"""
환세쾌도전 텍스트 추출기
========================

사용법:
  python3 tools/kaitou_parser.py original/kaitou

DISK_B.DAT에서 SJIS 텍스트 런을 추출, 인접 런을 메시지로 묶어
translation/kaitou/translation.json 생성.

구조 노트:
  - 텍스트는 비압축 SJIS (풍광전 LZ와 다름)
  - 제어 바이트: SJIS 이외 모든 바이트
  - 파악된 패턴:
      62 00 xx xx  = 대화 블록 헤더
      64 01 ... 65 = 메뉴 항목
      72 01        = 줄바꿈(추정)
      0a           = 아이템/스킬 구분자(추정)
"""

import json
import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── SJIS 유틸 ────────────────────────────────────────────────────────────────

def is_sjis_lead(b: int) -> bool:
    return (0x81 <= b <= 0x9f) or (0xe0 <= b <= 0xfc)

def is_sjis_pair(b1: int, b2: int) -> bool:
    return is_sjis_lead(b1) and (0x40 <= b2 <= 0xfc) and b2 != 0x7f

def decode_sjis(b1: int, b2: int) -> str:
    try:
        return bytes([b1, b2]).decode('shift_jis')
    except Exception:
        return ''

# ── 텍스트 추출 ───────────────────────────────────────────────────────────────

def extract_runs(data: bytes, min_chars: int = 3) -> list[tuple[int, str]]:
    """연속 SJIS 문자 런 추출 → [(offset, text), ...]"""
    runs = []
    i = 0
    while i < len(data) - 1:
        if is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1]):
            start = i
            text = ''
            while i < len(data) - 1 and is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1]):
                ch = decode_sjis(data[i], data[i + 1])
                if not ch:
                    i += 2  # 디코딩 실패 시 전진 (무한루프 방지)
                    break
                text += ch
                i += 2
            if len(text) >= min_chars:
                runs.append((start, text))
            # i가 start에서 전진했으므로 추가 증가 불필요
        else:
            i += 1
    return runs


def group_runs(data: bytes, runs: list, max_gap: int = 16) -> list[list]:
    """인접 런을 메시지로 묶기: 런 사이 제어 바이트가 max_gap 이하면 같은 메시지"""
    if not runs:
        return []
    messages = []
    cur = [runs[0]]
    for off, text in runs[1:]:
        prev_end = cur[-1][0] + len(cur[-1][1].encode('shift_jis'))
        gap = off - prev_end
        if 0 <= gap <= max_gap:
            cur.append((off, text))
        else:
            messages.append(cur)
            cur = [(off, text)]
    messages.append(cur)
    return messages


# ── 분류 ─────────────────────────────────────────────────────────────────────

def classify(data: bytes, first_off: int, lookback: int = 20) -> str:
    """직전 제어 바이트 패턴으로 메시지 타입 추정"""
    pre = data[max(0, first_off - lookback): first_off]
    for i in range(len(pre) - 1):
        if pre[i] == 0x62 and pre[i + 1] == 0x00:
            return 'dialog'
    if len(pre) >= 2 and pre[-2] == 0x64 and pre[-1] == 0x01:
        return 'menu'
    if 0x0a in pre[-6:]:
        return 'item'
    return 'unknown'


def looks_like_font_table(text: str) -> bool:
    """코드 포인트 순차 나열 → 폰트/문자표 데이터로 판단"""
    if len(text) < 4:
        return False
    sequential = sum(
        1 for i in range(len(text) - 1)
        if abs(ord(text[i + 1]) - ord(text[i])) == 1
    )
    return sequential >= len(text) - 2


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main(game_dir: str) -> None:
    title = os.path.basename(game_dir.rstrip('/\\'))

    disk_b = os.path.join(game_dir, 'DISK_B.DAT')
    if not os.path.exists(disk_b):
        print(f'오류: {disk_b} 없음')
        sys.exit(1)

    data = open(disk_b, 'rb').read()
    print(f'DISK_B.DAT 로드: {len(data):,} bytes')

    # 1. 런 추출
    runs = extract_runs(data, min_chars=3)
    print(f'SJIS 런: {len(runs)}개')

    # 2. 메시지 그룹화
    groups = group_runs(data, runs, max_gap=16)
    print(f'메시지 그룹: {len(groups)}개 (gap ≤ 16 bytes)')

    # 3. 엔트리 생성
    entries = []
    skipped_font = 0
    skipped_short = 0

    for blocks in groups:
        jp_full = ''.join(t for _, t in blocks)

        # 폰트 테이블 제거
        if looks_like_font_table(jp_full):
            skipped_font += 1
            continue

        # 단일 블록이고 3자 미만인 경우 제거 (이미 min_chars=3이지만 합쳐서 짧을 수도)
        if len(jp_full) < 3:
            skipped_short += 1
            continue

        first_off = blocks[0][0]
        msg_type = classify(data, first_off)

        entry = {
            'file':    'DISK_B.DAT',
            'offset':  first_off,
            'type':    msg_type,
            'jp':      jp_full,
            'kr':      '',
            'blocks':  [
                {
                    'offset': off,
                    'jp':     text,
                    'kr':     '',
                    'bytes':  len(text.encode('shift_jis')),
                }
                for off, text in blocks
            ],
        }
        entries.append(entry)

    # 4. 통계
    print(f'엔트리: {len(entries)}개')
    print(f'필터: 폰트테이블 {skipped_font}개, 짧은 텍스트 {skipped_short}개')
    type_count = Counter(e['type'] for e in entries)
    for t, c in type_count.most_common():
        print(f'  {t}: {c}개')

    # 5. 저장
    out_dir = os.path.join(PROJECT_ROOT, 'translation', title)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'translation.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'entries': entries}, f, ensure_ascii=False, indent=2)

    print(f'\n저장: {out_path}')


if __name__ == '__main__':
    game_dir = sys.argv[1] if len(sys.argv) > 1 else 'original/kaitou'
    main(game_dir)
