"""
환세쾌도전 텍스트 추출기 v2
============================

사용법:
  python3 tools/kaitou_parser.py original/kaitou

DISK_B.DAT 에서 텍스트를 추출하여
translation/kaitou/translation.json 을 생성.

구조 노트:
  - 파일 앞 264바이트(0x108): 33개 청크 인덱스 (8바이트/엔트리)
    → [hi_type(1), lo_type(1), offset_LE(4), field(2)]
  - type=0000 청크 4개(합계 ~92KB)가 스크립트/텍스트 데이터
  - 다른 type (0100=그래픽, 0200~=음악 등)은 스캔하지 않음
  - 제어코드 체계:
      62 00 XX XX  = 대화 블록 헤더
      72 XX        = 줄바꿈 (line break)
      64 XX        = 탭/열 제어
      65 XX        = 페이지/대기?
      6b XX        = unknown
      ff           = 블록 종료 추정
  - 고밀도 스크립트 영역 (SJIS 비율 ≥ 0.30/256바이트)만 라인 추출
  - 저밀도 영역(머신 코드 등)도 근접 런 그룹화로 추가 수집
"""

import json
import os
import struct
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

# ── 청크 인덱스 파싱 ──────────────────────────────────────────────────────────

def parse_chunk_index(data: bytes) -> list[tuple[int, int, int, int]]:
    """
    파일 앞부분 8바이트 엔트리를 파싱.
    반환: [(hi_type, lo_type, offset, field), ...]
    """
    entries = []
    i = 0
    while i + 8 <= len(data):
        hi_type, lo_type = data[i], data[i + 1]
        offset = struct.unpack_from('<I', data, i + 2)[0]
        field  = struct.unpack_from('<H', data, i + 6)[0]
        # offset이 0이고 type이 0이면 인덱스 끝
        if offset == 0 and hi_type == 0 and lo_type == 0:
            break
        if offset >= len(data):
            break
        entries.append((hi_type, lo_type, offset, field))
        i += 8
        if len(entries) > 200:
            break
    return entries

def get_text_chunk_ranges(data: bytes) -> list[tuple[int, int]]:
    """
    type=0000 청크의 (start, end) 범위 목록 반환.
    end는 다음 청크 시작 또는 파일 끝.
    """
    entries = parse_chunk_index(data)
    # 오프셋 순 정렬
    sorted_entries = sorted(entries, key=lambda e: e[2])

    ranges = []
    for idx, (hi, lo, offset, field) in enumerate(sorted_entries):
        if hi != 0 or lo != 0:
            continue
        # end = 다음 청크 시작
        if idx + 1 < len(sorted_entries):
            next_offset = sorted_entries[idx + 1][2]
        else:
            next_offset = len(data)
        ranges.append((offset, next_offset))
    return ranges

# ── SJIS 밀도 측정 ────────────────────────────────────────────────────────────

def sjis_ratio(data: bytes, start: int, length: int) -> float:
    """data[start:start+length] 의 SJIS 쌍 비율."""
    end = min(start + length, len(data))
    total = sjis = 0
    i = start
    while i < end - 1:
        if is_sjis_pair(data[i], data[i + 1]):
            sjis += 1
            total += 1
            i += 2
        else:
            total += 1
            i += 1
    return sjis / total if total > 0 else 0.0

# ── 고밀도 스크립트 영역 탐지 ────────────────────────────────────────────────

def find_script_regions(
    data: bytes, cs: int, ce: int,
    window: int = 256, step: int = 64, threshold: float = 0.30
) -> list[tuple[int, int]]:
    """SJIS 비율 ≥ threshold 인 윈도우를 병합한 영역 목록."""
    regions: list[tuple[int, int]] = []
    off = cs
    while off + window <= ce:
        if sjis_ratio(data, off, window) >= threshold:
            new_end = off + window
            if regions and regions[-1][1] >= off - step:
                regions[-1] = (regions[-1][0], new_end)
            else:
                regions.append((off, new_end))
        off += step
    # ce를 초과하지 않도록 클리핑
    return [(max(cs, s), min(ce, e)) for s, e in regions]

# ── 스크립트 영역에서 라인 추출 (72 XX 줄바꿈 인식) ────────────────────────

def extract_lines_from_region(
    data: bytes, start: int, end: int
) -> list[tuple[int, str]]:
    """
    스크립트 영역에서 72 XX 를 줄바꿈으로 인식하여 라인 추출.
    반환: [(offset, text), ...]
    """
    lines: list[tuple[int, str]] = []
    i = start
    current: list[str] = []
    line_start = start

    while i < end - 1:
        b = data[i]
        if is_sjis_lead(b) and is_sjis_pair(b, data[i + 1]):
            ch = decode_sjis(b, data[i + 1])
            if ch:
                current.append(ch)
            i += 2
        elif b == 0x72 and i + 1 < end:          # 줄바꿈
            if current:
                text = ''.join(current).strip()
                if len(text) >= 2:
                    lines.append((line_start, text))
                current = []
            line_start = i + 2
            i += 2
        else:
            i += 1

    if current:
        text = ''.join(current).strip()
        if len(text) >= 2:
            lines.append((line_start, text))

    return lines

# ── 텍스트 런 추출 (근접 그룹화) ──────────────────────────────────────────────

def extract_runs(data: bytes, ranges: list[tuple[int, int]], min_chars: int = 3) -> list[tuple[int, str]]:
    """지정 범위 내에서 연속 SJIS 런 추출."""
    runs: list[tuple[int, str]] = []
    for cs, ce in ranges:
        i = cs
        while i < ce - 1:
            if is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1]):
                start = i
                text = ''
                while i < ce - 1 and is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1]):
                    ch = decode_sjis(data[i], data[i + 1])
                    if not ch:
                        i += 2
                        break
                    text += ch
                    i += 2
                if len(text) >= min_chars:
                    runs.append((start, text))
            else:
                i += 1
    return runs


def group_runs(runs: list[tuple[int, str]], max_gap: int = 16) -> list[list[tuple[int, str]]]:
    """인접 런을 메시지로 묶기."""
    if not runs:
        return []
    messages: list[list[tuple[int, str]]] = []
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

# ── 분류 ──────────────────────────────────────────────────────────────────────

def classify(data: bytes, first_off: int, lookback: int = 24) -> str:
    """직전 제어 바이트 패턴으로 메시지 타입 추정."""
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
    """코드 포인트 순차 나열 → 폰트/문자표 데이터 판단."""
    if len(text) < 4:
        return False
    sequential = sum(
        1 for i in range(len(text) - 1)
        if abs(ord(text[i + 1]) - ord(text[i])) == 1
    )
    return sequential >= len(text) - 2

# ── 메인 ──────────────────────────────────────────────────────────────────────

def main(game_dir: str) -> None:
    title = os.path.basename(game_dir.rstrip('/\\'))

    disk_b = os.path.join(game_dir, 'DISK_B.DAT')
    if not os.path.exists(disk_b):
        print(f'오류: {disk_b} 없음')
        sys.exit(1)

    data = open(disk_b, 'rb').read()
    print(f'DISK_B.DAT 로드: {len(data):,} bytes')

    # ── 1. type=0000 청크 범위 파악 ──────────────────────────────────────────
    text_ranges = get_text_chunk_ranges(data)
    print(f'type=0000 청크: {len(text_ranges)}개')
    for i, (cs, ce) in enumerate(text_ranges):
        print(f'  청크 {i}: 0x{cs:06x} - 0x{ce:06x} ({ce - cs:,} bytes)')

    # ── 2. 고밀도 스크립트 영역에서 라인 추출 (72 XX 인식) ──────────────────
    line_entries: list[tuple[int, str]] = []
    for cs, ce in text_ranges:
        regions = find_script_regions(data, cs, ce, window=256, step=64, threshold=0.30)
        for rs, re in regions:
            lines = extract_lines_from_region(data, rs, re)
            line_entries.extend(lines)

    # 중복 제거 (오프셋 기준)
    seen_offsets: set[int] = set()
    unique_lines: list[tuple[int, str]] = []
    for off, text in sorted(line_entries):
        if off not in seen_offsets:
            seen_offsets.add(off)
            unique_lines.append((off, text))

    print(f'\n라인 단위 추출 (72 XX 기반): {len(unique_lines)}개')

    # ── 3. 전체 type=0000 청크에서 런 그룹화 (보완) ─────────────────────────
    runs = extract_runs(data, text_ranges, min_chars=3)
    groups = group_runs(runs, max_gap=16)
    print(f'런 그룹: {len(groups)}개')

    # ── 4. 엔트리 통합 ───────────────────────────────────────────────────────
    all_entries: list[dict] = []
    seen_texts: set[str] = set()
    skipped_font = 0

    # 4a. 라인 기반 엔트리 (구조 명확한 대화)
    for off, text in unique_lines:
        if looks_like_font_table(text):
            skipped_font += 1
            continue
        if text in seen_texts:
            continue
        seen_texts.add(text)
        msg_type = classify(data, off)
        all_entries.append({
            'file':   'DISK_B.DAT',
            'offset': off,
            'type':   'line_' + msg_type,
            'jp':     text,
            'kr':     '',
            'blocks': [{'offset': off, 'jp': text, 'kr': '', 'bytes': len(text.encode('shift_jis'))}],
        })

    # 4b. 런 그룹 기반 엔트리 (UI, 아이템, 메뉴 등 보완)
    for blocks in groups:
        jp_full = ''.join(t for _, t in blocks)
        if looks_like_font_table(jp_full):
            skipped_font += 1
            continue
        if len(jp_full) < 3:
            continue
        # 라인 기반에서 이미 포함된 텍스트면 스킵
        if jp_full in seen_texts:
            continue
        # 완전히 겹치는 하위 문자열도 스킵 (선택적)
        first_off = blocks[0][0]
        msg_type = classify(data, first_off)
        seen_texts.add(jp_full)
        all_entries.append({
            'file':   'DISK_B.DAT',
            'offset': first_off,
            'type':   msg_type,
            'jp':     jp_full,
            'kr':     '',
            'blocks': [
                {
                    'offset': off,
                    'jp':     text,
                    'kr':     '',
                    'bytes':  len(text.encode('shift_jis')),
                }
                for off, text in blocks
            ],
        })

    # 오프셋 순 정렬
    all_entries.sort(key=lambda e: e['offset'])

    # ── 5. 통계 ──────────────────────────────────────────────────────────────
    print(f'\n=== 최종 엔트리: {len(all_entries)}개 ===')
    print(f'필터: 폰트테이블 {skipped_font}개 제거')
    type_count = Counter(e['type'] for e in all_entries)
    for t, c in type_count.most_common():
        print(f'  {t}: {c}개')

    # ── 6. 저장 ──────────────────────────────────────────────────────────────
    out_dir = os.path.join(PROJECT_ROOT, 'translation', title)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'translation.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'entries': all_entries}, f, ensure_ascii=False, indent=2)

    print(f'\n저장: {out_path}')


if __name__ == '__main__':
    game_dir = sys.argv[1] if len(sys.argv) > 1 else 'original/kaitou'
    main(game_dir)
