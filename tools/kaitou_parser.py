"""
환세쾌도전 텍스트 추출기 v4
============================

사용법:
  python3 tools/kaitou_parser.py original/kaitou

DISK_B.DAT 에서 텍스트를 추출하여
translation/kaitou/translation.json 을 생성.

v4 변경점:
  - extract_name_blocks() 추가:
      64 XX [SJIS] 65 패턴 파싱 (캐릭터명/적 이름/상태 레이블 등)
      스마ッシュ 등 SJIS 런 폴백이 잘라먹던 텍스트 올바르게 추출
  - Coverage 기반 SJIS 런 추출:
      구조화 파서가 소비한 바이트 구간은 런 추출 스킵
      → 파서 경계에서 잘리는 텍스트 제거
  - 화자 오인식 수정:
      6e 00 67 XX 뒤에 「로 시작하는 텍스트 = 화자명 아닌 첫 대사줄로 재분류
  - 노이즈 필터 완전 제거:
      looks_like_noise() 삭제, 분류는 번역 단계에서 수동으로
  - 중복 제거: jp 텍스트 기반 → (chunk, local_offset) 기반으로 변경
      동일 오프셋에서 여러 파서가 생성한 중복만 제거

청크 구조:
  - DISK_B.DAT 앞부분: 4-byte 엔트리 테이블 (파일 offset 0x400까지)
    엔트리: [CX(2 LE), DX(2 LE)] → seek = (CX<<16)|DX
  - 각 청크는 compile_lz.decompress() 로 해제 (hukyou와 동일 알고리즘)
  - SJIS 밀도 > 5% 인 청크만 파싱

제어코드 (확정):
  62 00 XX XX  = 스킬/아이템 블록 시작 (인수 3바이트)
  64 XX        = 이름/레이블 블록 or 구분자 (XX=00이면 추가 2바이트)
  65           = 블록 종료 (인수 없음)
  67 XX        = 화자 마커 (인수 1바이트)
  6b XX        = 씬 전환 (인수 1바이트)
  6e XX        = 대화 섹션 (인수 1바이트)
  72 XX        = 줄바꿈 (인수 1바이트)
  73 XX        = 대화 블록 종료 (인수 1바이트)
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

# ── 대화 블록 파서 ────────────────────────────────────────────────────────────

def extract_dialogue_blocks(data: bytes, chunk_idx: int,
                            consumed: set) -> list[dict]:
    """
    6e 00 67 XX [화자 SJIS] 72 XX [대화줄...] 73 XX 패턴 추출.
    소비한 바이트 범위를 consumed 에 기록.

    수정 (v4): 67 XX 직후 텍스트가 「로 시작하면 화자 없는 대사로 처리
               (기존: 모두 화자명으로 오인식)
    """
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

        speaker_start = i

        # 화자명 읽기 (72 XX 까지)
        speaker_chars: list[str] = []
        while i < n:
            b = data[i]
            if b == 0x72:
                i += 2  # skip 72 XX
                break
            elif b in (0x73, 0x65, 0x62, 0x6e, 0x6b):
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    speaker_chars.append(ch)
                i += 2
            else:
                i += 1
        speaker = ''.join(speaker_chars).strip()

        # v4 수정: 화자 텍스트가 「/『/　로 시작하면 실제로는 첫 대사줄
        prepend_line: dict | None = None
        if speaker and speaker[0] in ('「', '『', '　'):
            prepend_line = {
                'offset': speaker_start,
                'jp':     speaker,
                'jp_len': len(speaker.encode('shift_jis', errors='replace')),
                'kr':     '',
            }
            speaker = ''

        # 대화 줄 읽기 (73 XX 까지)
        lines: list[dict] = []
        if prepend_line:
            lines.append(prepend_line)

        cur_chars: list[str] = []
        cur_offset = i
        found_end = False

        while i < n:
            b = data[i]

            if b == 0x73:  # dialogue end
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        lines.append({
                            'offset': cur_offset,
                            'jp':     jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr':     '',
                        })
                i += 2  # skip 73 XX
                found_end = True
                break

            elif b == 0x72:  # line break
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
                i += 2  # skip 72 XX
                cur_offset = i

            elif b in (0x65, 0x6e, 0x62):  # block end
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

        # 실질 내용 있는 줄만 (「 단독, 　 단독 제외)
        valid_lines = [
            l for l in lines
            if l['jp'] and l['jp'].strip() not in ('「', '　', '「　', '')
        ]
        if valid_lines:
            jp_full = '\n'.join(l['jp'] for l in valid_lines)
            results.append({
                'file':    'DISK_B.DAT',
                'chunk':   chunk_idx,
                'offset':  block_start,
                'type':    'dialog',
                'jp':      jp_full,
                'kr':      '',
                'speaker': speaker,
                'lines':   valid_lines,
            })

    return results

# ── 이름/레이블 블록 파서 ─────────────────────────────────────────────────────

def extract_name_blocks(data: bytes, chunk_idx: int,
                        consumed: set) -> list[dict]:
    """
    64 XX [SJIS 텍스트] 65 패턴 추출 (XX != 00).
    캐릭터명(64 f6), 상태 효과(64 fc → 毒 등), UI 레이블 등.
    64 00 XX XX 계열(챕터 제목)은 extract_title_labels가 처리.

    이미 consumed 된 위치는 스킵.
    소비한 바이트 범위를 consumed 에 기록.
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

        while i < n and i < block_start + 100:  # 합리적 상한
            b = data[i]
            if b == 0x65:
                found_end = True
                i += 1  # past 65
                break
            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    text_chars.append(ch)
                i += 2
            elif b in (0x62, 0x64, 0x67, 0x6e, 0x72, 0x73, 0x6b, 0x75, 0x76):
                # 다른 제어코드 만나면 이 블록은 레이블 블록이 아님
                break
            else:
                # non-SJIS, non-opcode 바이트: 스킵 (공백 등)
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

# ── 챕터 제목 파서 ────────────────────────────────────────────────────────────

def extract_title_labels(data: bytes, chunk_idx: int,
                         consumed: set) -> list[dict]:
    """
    64 00 XX XX [SJIS 텍스트] 패턴 추출.
    챕터 번호/제목 등에 사용.
    이미 consumed 된 위치는 스킵.
    소비한 바이트 범위를 consumed 에 기록.
    """
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

# ── SJIS 런 추출 (폴백) ───────────────────────────────────────────────────────

def extract_sjis_runs(data: bytes, chunk_idx: int,
                      consumed: set,
                      min_chars: int = 2) -> list[dict]:
    """
    연속 SJIS 런 추출 (구조적 파서가 놓친 메뉴·UI 텍스트 보완).

    v4: consumed 셋에 포함된 위치는 스킵 → 구조화 파서 경계에서 잘리는 문제 방지.
    min_chars: 최소 글자 수 (기본 2).
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 1:
        # 구조화 파서가 소비한 구간은 스킵
        if i in consumed:
            i += 1
            continue

        if not (is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1])):
            i += 1
            continue

        start = i
        chars: list[str] = []
        while i < n - 1:
            # 중간에 consumed 구간이 시작되면 런 종료
            if i in consumed:
                break
            if not (is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1])):
                break
            ch = decode_sjis_char(data[i], data[i + 1])
            i += 2  # 항상 전진 (decode 실패해도)
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
    """
    기존 translation.json에서 kr 값을 로드.
    키: (chunk, offset) → kr 문자열
    """
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
    """추출된 엔트리에 기존 kr 값 복원."""
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

        # 구조화 파서 순서대로 실행 — consumed 를 채워가며 진행
        all_entries.extend(extract_dialogue_blocks(dec, idx, consumed))
        all_entries.extend(extract_name_blocks(dec, idx, consumed))
        all_entries.extend(extract_title_labels(dec, idx, consumed))

        # SJIS 런 폴백: 위 파서가 소비하지 않은 구간만 추출
        all_entries.extend(extract_sjis_runs(dec, idx, consumed, min_chars=2))

    # ── 3. 중복 제거 (chunk + offset 기반, 먼저 발견된 것 우선) ───────────────
    seen: dict[tuple, dict] = {}
    for entry in all_entries:
        key = (entry['chunk'], entry['offset'])
        if key not in seen:
            seen[key] = entry

    # 청크·오프셋 순 정렬
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
