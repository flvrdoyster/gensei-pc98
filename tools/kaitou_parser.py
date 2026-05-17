"""
환세쾌도전 텍스트 추출기 v5
============================

사용법:
  python3 tools/kaitou_parser.py original/kaitou

DISK_B.DAT 에서 텍스트를 추출하여
translation/kaitou/translation.json 을 생성.

v5 변경점:
  - extract_6b_dialogue_blocks() 추가:
      6b 00 80 77 00 [SJIS] 73 XX 패턴 (화자 없는 대화)
      청크 31 등에서 6e 00 67 이전 구간의 누락 대화 처리
  - extract_simple_blocks() 추가:
      62 00 XX XX [SJIS 직접] 65 패턴 (스킬/아이템 설명)
      6e 00 67 앵커 없는 블록만 처리, 청크 3 커버
  - extract_6d_name_blocks() 추가:
      6d 08 [SJIS만] 65 패턴 (적/아이템 이름, 청크 61-64)
      엄격 모드: SJIS 쌍만 허용, 32바이트 상한
  - SJIS 런 폴백 범위 제한:
      find_block_ranges() 로 62 00 블록 경계 내부만 eligible
      x86 코드 등 구조 없는 영역의 노이즈 제거

확정 제어코드:
  62 00 XX XX  = 블록 시작 (직접 텍스트 또는 대화 컨테이너)
  64 XX        = 이름/레이블 블록 (XX=00이면 64 00 XX XX 챕터 제목)
  65           = 블록 종료
  67 XX        = 화자 마커
  6b 00 80 77 00 = 화자 없는 대화 블록
  6b 00 81 65    = 빈 대화 슬롯
  6d 08        = 적/아이템 이름 블록
  6e 00 67     = 대화 블록 앵커
  72 XX        = 줄바꿈
  73 XX        = 대화 블록 종료
"""

import json
import os
import struct
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_lz import decompress, is_sjis_lead

# ── SJIS 유틸 ─────────────────────────────────────────────────────────────────

def is_sjis_pair(b1: int, b2: int) -> bool:
    return is_sjis_lead(b1) and (0x40 <= b2 <= 0xFC) and b2 != 0x7F

def decode_sjis_char(b1: int, b2: int) -> str:
    try:
        return bytes([b1, b2]).decode('shift_jis')
    except Exception:
        return ''

def sjis_density(data: bytes) -> float:
    """전체 바이트 중 유효 SJIS 쌍 바이트 비율."""
    if not data:
        return 0.0
    sjis = 0
    i = 0
    n = len(data)
    while i < n - 1:
        if is_sjis_pair(data[i], data[i + 1]):
            try:
                bytes([data[i], data[i + 1]]).decode('shift_jis')
                sjis += 2
                i += 2
                continue
            except Exception:
                pass
        i += 1
    return sjis / n

# ── 청크 테이블 파싱 ──────────────────────────────────────────────────────────

def parse_chunk_table(data: bytes) -> list[tuple[int, int]]:
    """
    파일 앞부분 (0x000~0x3FF) 4-byte 엔트리 파싱.
    엔트리: [CX(2 LE), DX(2 LE)] → seek_pos = (CX<<16)|DX
    반환: [(seek_pos, compressed_size), ...] (seek 순 정렬)
    """
    seeks = []
    for off in range(0, 0x400, 4):
        if off + 4 > len(data):
            break
        cx = struct.unpack_from('<H', data, off)[0]
        dx = struct.unpack_from('<H', data, off + 2)[0]
        seek = (cx << 16) | dx
        if seek == 0:
            continue
        if seek >= len(data):
            continue
        seeks.append(seek)

    seeks = sorted(set(seeks))
    result = []
    for j, seek in enumerate(seeks):
        end = seeks[j + 1] if j + 1 < len(seeks) else len(data)
        result.append((seek, end - seek))
    return result

# ── 파서 1: 6e 00 67 대화 블록 ───────────────────────────────────────────────

def extract_dialogue_blocks(data: bytes, chunk_idx: int,
                            consumed: set) -> list[dict]:
    """6e 00 67 XX [텍스트] 72 XX ... 73 XX 패턴. 모든 텍스트를 lines로."""
    results = []
    i = 0
    n = len(data)

    while i < n - 3:
        if not (data[i] == 0x6e and data[i + 1] == 0x00
                and i + 2 < n and data[i + 2] == 0x67):
            i += 1
            continue

        block_start = i
        i += 4  # skip 6e 00 67 XX

        lines: list[dict] = []
        cur_chars: list[str] = []
        cur_offset = i
        found_end = False

        while i < n:
            b = data[i]
            if b == 0x73:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                i += 2
                found_end = True
                break
            elif b == 0x72:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                    cur_chars = []
                i += 2
                cur_offset = i
            elif b in (0x65, 0x6e, 0x62):
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    cur_chars.append(ch)
                i += 2
            else:
                i += 1

        if found_end:
            consumed.update(range(block_start, i))

        valid_lines = [l for l in lines if l['jp'] and l['jp'].strip()]
        if valid_lines:
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': block_start,
                'type':   'dialog',
                'jp':     '\n'.join(l['jp'] for l in valid_lines),
                'kr':     '',
                'lines':  valid_lines,
            })

    return results

# ── 파서 2: 6b 00 80 화자 없는 대화 블록 ────────────────────────────────────

def extract_6b_dialogue_blocks(data: bytes, chunk_idx: int,
                               consumed: set) -> list[dict]:
    """
    6b 00 80 77 00 [SJIS] 73 XX 패턴 — 화자 없는 대화.
    6b 00 81 65 = 빈 슬롯 (consume만, 엔트리 없음).
    청크 31 등 6e 00 67 이전 구간 대화 처리.
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 2:
        if i in consumed:
            i += 1
            continue

        if not (data[i] == 0x6b and data[i + 1] == 0x00):
            i += 1
            continue

        block_start = i

        if i + 2 >= n:
            i += 1
            continue

        subtype = data[i + 2]

        # 빈 슬롯: 6b 00 81 65
        if subtype == 0x81:
            if i + 3 < n and data[i + 3] == 0x65:
                consumed.update(range(i, i + 4))
                i += 4
            else:
                i += 1
            continue

        # 텍스트 블록: 6b 00 80 77 00 [text] 73 XX
        if subtype != 0x80 or i + 4 >= n:
            i += 1
            continue

        i += 5  # skip 6b 00 80 77 00

        lines: list[dict] = []
        cur_chars: list[str] = []
        cur_offset = i
        found_end = False

        while i < n:
            b = data[i]
            if b == 0x73:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                i += 2
                found_end = True
                break
            elif b == 0x72:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                    cur_chars = []
                i += 2
                cur_offset = i
            elif b in (0x65, 0x6e, 0x62, 0x6b):
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    cur_chars.append(ch)
                i += 2
            else:
                i += 1

        if found_end:
            consumed.update(range(block_start, i))

        valid_lines = [l for l in lines if l['jp'] and l['jp'].strip()]
        if valid_lines:
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': block_start,
                'type':   'dialog',
                'jp':     '\n'.join(l['jp'] for l in valid_lines),
                'kr':     '',
                'lines':  valid_lines,
            })

    return results

# ── 파서 3: 62 00 직접 텍스트 블록 ───────────────────────────────────────────

def extract_simple_blocks(data: bytes, chunk_idx: int,
                          consumed: set) -> list[dict]:
    """
    62 00 XX XX [SJIS 직접] 65 패턴 — 스킬/아이템 설명 등.

    6e 00 67 앵커 없이 텍스트가 직접 배치된 62 00 블록만 처리.
    내부 64 XX = 서브 레이블(소비 MP 등), 72 XX = 줄바꿈.

    조건:
    - block_start 가 consumed 에 없어야 함
    - 첫 콘텐츠 바이트가 유효 SJIS 쌍이어야 함 (코드 영역 필터)
    - 내부에 6e 00 67 이 있으면 스킵 (대화 블록 컨테이너)
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 4:
        if i in consumed:
            i += 1
            continue

        if not (data[i] == 0x62 and data[i + 1] == 0x00):
            i += 1
            continue

        block_start = i
        content_start = i + 4

        # 첫 콘텐츠가 SJIS 쌍이 아니면 코드 영역 → 스킵
        if (content_start + 1 >= n
                or not is_sjis_pair(data[content_start], data[content_start + 1])):
            i += 1
            continue

        # 내부에 6e 00 67 이 있으면 대화 컨테이너 → 스킵
        # 첫 65 까지만 미리 스캔
        has_dialogue_anchor = False
        j = content_start
        while j < n:
            b = data[j]
            if b == 0x65:
                break
            if j + 2 < n and b == 0x6e and data[j+1] == 0x00 and data[j+2] == 0x67:
                has_dialogue_anchor = True
                break
            if is_sjis_lead(b) and j + 1 < n and is_sjis_pair(b, data[j + 1]):
                j += 2
            else:
                j += 1
        if has_dialogue_anchor:
            i += 1
            continue

        # 블록 내용 추출
        i = content_start
        lines: list[dict] = []
        cur_chars: list[str] = []
        cur_offset = i
        found_end = False

        while i < n:
            b = data[i]

            if b == 0x65:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                found_end = True
                i += 1
                break

            elif b == 0x72:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                    cur_chars = []
                i += 2
                cur_offset = i

            elif b == 0x64:
                i += 2  # 줄바꿈 아님, 그냥 스킵

            elif b == 0x73:
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                i += 2
                found_end = True
                break

            elif b in (0x62, 0x6b, 0x6e, 0x6d):
                break

            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    cur_chars.append(ch)
                i += 2

            else:
                i += 1

        if not found_end:
            i = block_start + 1
            continue

        consumed.update(range(block_start, i))

        valid_lines = [l for l in lines if l['jp'] and l['jp'].strip()]
        if valid_lines:
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': block_start,
                'type':   'dialog',
                'jp':     '\n'.join(l['jp'] for l in valid_lines),
                'kr':     '',
                'lines':  valid_lines,
            })

    return results

# ── 파서 4: 64 XX 이름/레이블 블록 ───────────────────────────────────────────

def extract_name_blocks(data: bytes, chunk_idx: int,
                        consumed: set) -> list[dict]:
    """
    64 XX [SJIS 텍스트] 65 패턴 추출 (XX != 00).
    64 00 XX XX 계열은 extract_title_labels가 처리.
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 1:
        if i in consumed:
            i += 1
            continue

        if data[i] != 0x64 or data[i + 1] == 0x00:
            i += 1
            continue

        block_start = i
        i += 2  # skip 64 XX

        text_chars: list[str] = []
        text_start = i
        found_end = False

        while i < n and i < block_start + 100:
            b = data[i]
            if b == 0x65:
                found_end = True
                i += 1
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    text_chars.append(ch)
                i += 2
            elif b in (0x62, 0x64, 0x67, 0x6e, 0x72, 0x73, 0x6b, 0x75, 0x76):
                break
            else:
                i += 1

        if not found_end:
            i = block_start + 1
            continue

        jp = ''.join(text_chars).strip()
        if not jp:
            continue

        consumed.update(range(block_start, i))
        results.append({
            'file':  'DISK_B.DAT',
            'chunk': chunk_idx,
            'offset': block_start,
            'type':  'dialog',
            'jp':    jp,
            'kr':    '',
            'lines': [{
                'offset': text_start,
                'jp':     jp,
                'jp_len': len(jp.encode('shift_jis', errors='replace')),
                'kr':     '',
            }],
        })

    return results

# ── 파서 5: 6d 08 적/아이템 이름 블록 ────────────────────────────────────────

def extract_6d_name_blocks(data: bytes, chunk_idx: int,
                           consumed: set) -> list[dict]:
    """
    6d 08 [SJIS만] 65 패턴 — 적/아이템 이름 (청크 61-64 등).

    엄격 모드: SJIS 쌍만 허용, 32바이트 상한.
    혼합(코드+텍스트) 블록은 자동 제외됨.
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 1:
        if i in consumed:
            i += 1
            continue

        if not (data[i] == 0x6d and data[i + 1] == 0x08):
            i += 1
            continue

        block_start = i
        i += 2
        text_start = i
        text_chars: list[str] = []
        found_end = False

        while i < n and i < block_start + 34:  # 32바이트 콘텐츠 상한
            b = data[i]
            if b == 0x65:
                found_end = True
                i += 1
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    text_chars.append(ch)
                i += 2
            else:
                # SJIS 이외 바이트 → 이 블록은 혼합 데이터, 스킵
                found_end = False
                break

        if not found_end:
            i = block_start + 1
            continue

        jp = ''.join(text_chars).strip()
        if not jp:
            continue

        consumed.update(range(block_start, i))
        results.append({
            'file':  'DISK_B.DAT',
            'chunk': chunk_idx,
            'offset': block_start,
            'type':  'dialog',
            'jp':    jp,
            'kr':    '',
            'lines': [{
                'offset': text_start,
                'jp':     jp,
                'jp_len': len(jp.encode('shift_jis', errors='replace')),
                'kr':     '',
            }],
        })

    return results

# ── 파서 6: 64 00 XX XX 챕터 제목 ────────────────────────────────────────────

def extract_title_labels(data: bytes, chunk_idx: int,
                         consumed: set) -> list[dict]:
    """64 00 XX XX [SJIS 텍스트] 패턴 — 챕터 번호/제목."""
    results = []
    i = 0
    n = len(data)

    STOP_OPCODES = frozenset({0x62, 0x64, 0x65, 0x67, 0x6b, 0x6e,
                               0x72, 0x73, 0x74, 0x75, 0x76, 0xff})

    while i < n - 3:
        if i in consumed:
            i += 1
            continue

        if not (data[i] == 0x64 and data[i + 1] == 0x00):
            i += 1
            continue

        block_start = i
        i += 4  # skip 64 00 XX XX

        text_chars: list[str] = []
        text_start = i
        text_end = i

        while i < n:
            b = data[i]
            if b in STOP_OPCODES:
                break
            if is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    text_chars.append(ch)
                i += 2
                text_end = i
            else:
                i += 1

        jp = ''.join(text_chars).strip()
        if len(jp) >= 1:
            consumed.update(range(block_start, text_end))
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': block_start,
                'type':   'dialog',
                'jp':     jp,
                'kr':     '',
                'lines':  [{
                    'offset': text_start,
                    'jp':     jp,
                    'jp_len': len(jp.encode('shift_jis', errors='replace')),
                    'kr':     '',
                }],
            })

    return results

# ── SJIS 런 eligible 범위 계산 ────────────────────────────────────────────────

def find_block_ranges(data: bytes) -> set[int]:
    """
    62 00 XX XX ... 65 블록 내부 바이트 위치 집합.
    SJIS 런 폴백이 탐색해도 되는 영역을 정의.

    조건: 첫 콘텐츠 바이트 쌍이 유효 SJIS 쌍이어야 인정.
    → x86 코드 등 구조 없는 영역의 62 00 거짓 양성 제거.
    좌→우 SJIS 파싱으로 65 위치를 정확히 탐색.
    """
    eligible: set[int] = set()
    i = 0
    n = len(data)

    while i < n - 4:
        if not (data[i] == 0x62 and data[i + 1] == 0x00):
            i += 1
            continue

        block_start = i
        content_start = i + 4

        if (content_start + 1 >= n
                or not is_sjis_pair(data[content_start], data[content_start + 1])):
            i += 1
            continue

        # 좌→우 파싱으로 블록 종료 65 탐색
        j = content_start
        found = False
        while j < n:
            b = data[j]
            if b == 0x65:
                eligible.update(range(block_start, j + 1))
                i = j + 1
                found = True
                break
            elif is_sjis_lead(b) and j + 1 < n and is_sjis_pair(b, data[j + 1]):
                j += 2
            else:
                j += 1

        if not found:
            i += 1

    return eligible

# ── SJIS 런 추출 (폴백) ───────────────────────────────────────────────────────

def extract_sjis_runs(data: bytes, chunk_idx: int,
                      consumed: set,
                      block_ranges=None,
                      min_chars: int = 2) -> list[dict]:
    """
    연속 SJIS 런 추출 — 구조적 파서가 놓친 텍스트 보완.

    v5: block_ranges 가 주어지면 62 00 블록 내부로만 탐색 제한.
        x86 코드 등 구조 없는 영역의 노이즈 제거.
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 1:
        if i in consumed:
            i += 1
            continue

        if block_ranges is not None and i not in block_ranges:
            i += 1
            continue

        if not (is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1])):
            i += 1
            continue

        start = i
        chars: list[str] = []
        while i < n - 1:
            if i in consumed:
                break
            if block_ranges is not None and i not in block_ranges:
                break
            if not (is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1])):
                break
            ch = decode_sjis_char(data[i], data[i + 1])
            i += 2
            if not ch:
                break
            chars.append(ch)

        jp = ''.join(chars).strip()
        if len(jp) >= min_chars:
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': start,
                'type':   'dialog',
                'jp':     jp,
                'kr':     '',
                'lines':  [{
                    'offset': start,
                    'jp':     jp,
                    'jp_len': len(jp.encode('shift_jis', errors='replace')),
                    'kr':     '',
                }],
            })

    return results

# ── 기존 번역 보존 ────────────────────────────────────────────────────────────

def load_existing_kr(out_path: str) -> dict:
    if not os.path.exists(out_path):
        return {}
    try:
        with open(out_path, encoding='utf-8') as f:
            old = json.load(f)
    except Exception:
        return {}

    kr_map: dict[tuple, str] = {}

    def _collect(entry: dict) -> None:
        chunk = entry.get('chunk', -1)
        if entry.get('kr'):
            kr_map[(chunk, entry['offset'])] = entry['kr']
        for seg in entry.get('segments', []):
            if seg.get('kr'):
                kr_map[(chunk, seg['offset'])] = seg['kr']
        for line in entry.get('lines', []):
            if line.get('kr'):
                kr_map[(chunk, line['offset'])] = line['kr']

    for e in old.get('entries', []):
        _collect(e)
    return kr_map

def apply_existing_kr(entries: list[dict], kr_map: dict) -> None:
    for entry in entries:
        chunk = entry.get('chunk', -1)
        key = (chunk, entry['offset'])
        if key in kr_map and not entry['kr']:
            entry['kr'] = kr_map[key]
        for seg in entry.get('segments', []):
            k = (chunk, seg['offset'])
            if k in kr_map and not seg['kr']:
                seg['kr'] = kr_map[k]
        for line in entry.get('lines', []):
            k = (chunk, line['offset'])
            if k in kr_map and not line['kr']:
                line['kr'] = kr_map[k]

# ── 메인 ──────────────────────────────────────────────────────────────────────

# 청크 전체 SJIS 밀도 임계값 (이 미만 = 그래픽/코드 청크, 스킵)
TEXT_THRESHOLD = 0.05

# 명시적으로 지정된 노이즈 청크 (그래픽/비트맵 데이터 — SJIS 밀도가 높아도 텍스트 아님)
NOISE_CHUNKS = {8, 9, 37, 42, 44, 48, 58, 59}


def main(game_dir: str) -> None:
    title = os.path.basename(game_dir.rstrip('/\\'))

    disk_b = os.path.join(game_dir, 'DISK_B.DAT')
    if not os.path.exists(disk_b):
        print(f'오류: {disk_b} 없음')
        sys.exit(1)

    data = open(disk_b, 'rb').read()
    print(f'DISK_B.DAT 로드: {len(data):,} bytes')

    out_dir  = os.path.join(PROJECT_ROOT, 'translation', title)
    out_path = os.path.join(out_dir, 'translation.json')
    kr_map   = load_existing_kr(out_path)
    if kr_map:
        print(f'기존 번역 로드: {len(kr_map)}개 항목')

    # ── 1. 청크 테이블 파싱 & 압축 해제 ────────────────────────────────────
    chunks_info = parse_chunk_table(data)
    print(f'\n청크 수: {len(chunks_info)}개')

    chunks: list[tuple[int, bytes, float]] = []
    for idx, (seek, _) in enumerate(chunks_info):
        dec     = decompress(data, seek)
        density = sjis_density(dec)
        chunks.append((idx, dec, density))

    text_chunks = [(idx, dec, d) for idx, dec, d in chunks
                   if d >= TEXT_THRESHOLD and idx not in NOISE_CHUNKS]
    print(f'텍스트 청크 ({TEXT_THRESHOLD:.0%} 이상, 노이즈 제외): {len(text_chunks)}개')
    for idx, dec, d in text_chunks:
        print(f'  청크 {idx:2d}: {len(dec):6,}B  SJIS={d:.1%}')

    # ── 2. 텍스트 추출 ────────────────────────────────────────────────────
    all_entries: list[dict] = []

    for idx, dec, density in text_chunks:
        consumed: set[int] = set()

        # 구조화 파서 (consumed 채워가며 순서대로)
        all_entries.extend(extract_dialogue_blocks(dec, idx, consumed))
        all_entries.extend(extract_6b_dialogue_blocks(dec, idx, consumed))
        all_entries.extend(extract_simple_blocks(dec, idx, consumed))
        all_entries.extend(extract_name_blocks(dec, idx, consumed))
        all_entries.extend(extract_6d_name_blocks(dec, idx, consumed))
        all_entries.extend(extract_title_labels(dec, idx, consumed))

        # SJIS 런 폴백: 62 00 블록 내부로만 제한
        block_ranges = find_block_ranges(dec)
        all_entries.extend(
            extract_sjis_runs(dec, idx, consumed, block_ranges=block_ranges, min_chars=2)
        )

    # ── 3. 중복 제거 (chunk + offset 기반, 먼저 발견된 것 우선) ───────────────
    seen: dict[tuple, dict] = {}
    for entry in all_entries:
        key = (entry['chunk'], entry['offset'])
        if key not in seen:
            seen[key] = entry

    final_entries = sorted(seen.values(), key=lambda e: (e['chunk'], e['offset']))

    # ── 4. 기존 kr 복원 ────────────────────────────────────────────────────
    if kr_map:
        apply_existing_kr(final_entries, kr_map)

    # ── 5. 통계 ─────────────────────────────────────────────────────────
    type_count  = Counter(e['type'] for e in final_entries)
    chunk_count = Counter(e['chunk'] for e in final_entries)
    print(f'\n=== 최종 엔트리: {len(final_entries)}개 ===')
    print('타입별:')
    for t, c in type_count.most_common():
        print(f'  {t:10s}: {c:4d}개')
    print('상위 청크:')
    for ch, c in chunk_count.most_common(10):
        print(f'  청크 {ch:2d}     : {c:4d}개')

    # ── 6. 저장 ─────────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'entries': final_entries}, f, ensure_ascii=False, indent=2)
    print(f'\n저장: {out_path}')


if __name__ == '__main__':
    game_dir = sys.argv[1] if len(sys.argv) > 1 else 'original/kaitou'
    main(game_dir)
