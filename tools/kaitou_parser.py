"""
환세쾌도전 텍스트 추출기 v3
============================

사용법:
  python3 tools/kaitou_parser.py original/kaitou

DISK_B.DAT 에서 텍스트를 추출하여
translation/kaitou/translation.json 을 생성.

v3 변경점:
  - DISK_B.DAT LZ 압축 해제 후 파싱 (v2는 압축된 바이트를 직접 파싱했음)
  - 4-byte 청크 테이블 올바른 파싱 (v2는 8-byte 테이블로 오해)
  - 구조화된 상태 머신 파서:
      62 00 XX XX  = 스킬/아이템 블록 (name → stat → desc, 65로 종료)
      6e 00 67 XX  = 대화 블록 (화자 → 대화줄, 73 XX로 종료)
      64 00 XX XX  = 챕터 제목/레이블
  - SJIS 런 폴백 (구조적 파서가 놓친 메뉴/UI 텍스트)
  - 재실행 시 기존 kr 번역 보존 (chunk + offset 기반)

청크 구조:
  - DISK_B.DAT 앞부분: 4-byte 엔트리 테이블 (파일 offset 0x400까지)
    엔트리: [CX(2 LE), DX(2 LE)] → seek = (CX<<16)|DX
  - 각 청크는 compile_lz.decompress() 로 해제 (hukyou와 동일 알고리즘)
  - SJIS 밀도 > 5% 인 청크만 파싱

제어코드 (확정):
  62 00 XX XX  = 스킬/아이템 블록 시작 (인수 3바이트)
  64 XX        = 구분자 (인수 1바이트; XX=00이면 추가 2바이트)
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

# ── 스킬/아이템 블록 파서 ─────────────────────────────────────────────────────

def extract_skill_blocks(data: bytes, chunk_idx: int) -> list[dict]:
    """
    62 00 XX XX ... 65 패턴의 스킬/아이템 블록 추출.

    블록 구조:
      [62 00 XX XX]   헤더 (4바이트 스킵)
      [SJIS]          스킬명 (name)
      [64 XX]         구분자 (1바이트 인수)
      [SJIS]          소비 스탯 (stat)
      [72 XX]         줄바꿈 (1바이트 인수)
      [SJIS]          설명 줄 (desc, 여러 줄 가능)
      [65]            블록 종료
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 3:
        if data[i] != 0x62 or data[i + 1] != 0x00:
            i += 1
            continue

        block_offset = i
        i += 4  # skip 62 + 3 arg bytes

        segments: list[dict] = []
        cur_chars: list[str] = []
        cur_offset = i
        cur_type = 'name'

        while i < n:
            b = data[i]

            if b == 0x65:  # block end
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        segments.append({
                            'type': cur_type,
                            'offset': cur_offset,
                            'jp': jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr': '',
                        })
                i += 1
                break

            elif b == 0x64 and i + 1 < n:  # separator: flush → stat
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        segments.append({
                            'type': cur_type,
                            'offset': cur_offset,
                            'jp': jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr': '',
                        })
                    cur_chars = []
                i += 2  # skip 64 XX
                cur_offset = i
                cur_type = 'stat'

            elif b == 0x72 and i + 1 < n:  # line break: flush → desc
                if cur_chars:
                    jp = ''.join(cur_chars).strip()
                    if jp:
                        segments.append({
                            'type': cur_type if cur_type == 'name' else 'desc',
                            'offset': cur_offset,
                            'jp': jp,
                            'jp_len': len(jp.encode('shift_jis', errors='replace')),
                            'kr': '',
                        })
                    cur_chars = []
                i += 2  # skip 72 XX
                cur_offset = i
                cur_type = 'desc'

            elif b in (0x62, 0x6e, 0x73):  # unexpected opcode: broken block
                break

            elif is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    cur_chars.append(ch)
                i += 2

            else:
                i += 1  # skip unknown byte

        # 텍스트 있는 블록만 수집
        text_segs = [s for s in segments if s['jp']]
        if text_segs:
            jp_main = next((s['jp'] for s in text_segs if s['type'] == 'name'), text_segs[0]['jp'])
            results.append({
                'file':     'DISK_B.DAT',
                'chunk':    chunk_idx,
                'offset':   block_offset,
                'type':     'skill',
                'jp':       jp_main,
                'kr':       '',
                'segments': text_segs,
            })

    return results

# ── 대화 블록 파서 ────────────────────────────────────────────────────────────

def extract_dialogue_blocks(data: bytes, chunk_idx: int) -> list[dict]:
    """
    6e 00 67 XX [화자 SJIS] 72 XX [대화줄...] 73 XX 패턴 추출.

    블록 구조:
      [6e 00]         대화 섹션 시작 (2바이트)
      [67 XX]         화자 마커 (2바이트)
      [SJIS]          화자명
      [72 XX]         줄바꿈 (화자명 끝)
      [SJIS]          대화 텍스트
      [72 XX]         줄바꿈 (다음 줄)
      ...
      [73 XX]         대화 블록 종료
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 3:
        if not (data[i] == 0x6e and data[i + 1] == 0x00
                and i + 2 < n and data[i + 2] == 0x67):
            i += 1
            continue

        block_offset = i
        i += 4  # skip 6e 00 67 XX

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

        # 대화 줄 읽기 (73 XX 까지)
        lines: list[dict] = []
        cur_chars: list[str] = []
        cur_offset = i

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

        # 실질 내용이 있는 줄만 (「 단독, 　 단독 제외)
        valid_lines = [
            l for l in lines
            if l['jp'] and l['jp'].strip() not in ('「', '　', '「　', '')
        ]
        if valid_lines:
            jp_full = '\n'.join(l['jp'] for l in valid_lines)
            results.append({
                'file':    'DISK_B.DAT',
                'chunk':   chunk_idx,
                'offset':  block_offset,
                'type':    'dialog',
                'jp':      jp_full,
                'kr':      '',
                'speaker': speaker,
                'lines':   valid_lines,
            })

    return results

# ── 챕터 제목 파서 ────────────────────────────────────────────────────────────

def extract_title_labels(data: bytes, chunk_idx: int) -> list[dict]:
    """
    64 00 XX XX [SJIS 텍스트] 패턴 추출.
    챕터 번호/제목 등에 사용. SJIS 밀도 > 30% 청크에서만 적용.
    """
    results = []
    i = 0
    n = len(data)

    STOP_OPCODES = frozenset({0x62, 0x64, 0x65, 0x67, 0x6b, 0x6e,
                               0x72, 0x73, 0x74, 0x75, 0x76, 0xff})

    while i < n - 3:
        if not (data[i] == 0x64 and data[i + 1] == 0x00):
            i += 1
            continue

        block_offset = i
        i += 4  # skip 64 00 XX XX

        text_chars: list[str] = []
        text_offset = i

        while i < n:
            b = data[i]
            if b in STOP_OPCODES:
                break
            if is_sjis_lead(b) and i + 1 < n and is_sjis_pair(b, data[i + 1]):
                ch = decode_sjis_char(b, data[i + 1])
                if ch:
                    text_chars.append(ch)
                i += 2
            else:
                i += 1

        jp = ''.join(text_chars).strip()
        if len(jp) >= 2:
            results.append({
                'file':   'DISK_B.DAT',
                'chunk':  chunk_idx,
                'offset': block_offset,
                'type':   'title',
                'jp':     jp,
                'kr':     '',
                'lines':  [{
                    'offset': text_offset,
                    'jp':     jp,
                    'jp_len': len(jp.encode('shift_jis', errors='replace')),
                    'kr':     '',
                }],
            })

    return results

# ── SJIS 런 추출 (폴백) ───────────────────────────────────────────────────────

def extract_sjis_runs(data: bytes, chunk_idx: int,
                      min_chars: int = 4) -> list[dict]:
    """
    연속 SJIS 런 추출 (구조적 파서가 놓친 메뉴·UI 텍스트 보완).
    최소 min_chars 글자 이상인 런만 수집.
    """
    results = []
    i = 0
    n = len(data)

    while i < n - 1:
        if not (is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1])):
            i += 1
            continue

        start = i
        chars: list[str] = []
        while i < n - 1 and is_sjis_lead(data[i]) and is_sjis_pair(data[i], data[i + 1]):
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
                'type':   'unknown',
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

# ── 노이즈 필터 ───────────────────────────────────────────────────────────────

def looks_like_noise(text: str) -> bool:
    """기계어 바이트가 우연히 SJIS로 디코딩된 노이즈 판별."""
    if len(text) < 2:
        return True

    # 코드 포인트 순차 나열 (폰트 테이블, 기계어 패턴)
    if len(text) >= 4:
        seq = sum(
            1 for k in range(len(text) - 1)
            if abs(ord(text[k + 1]) - ord(text[k])) <= 1
        )
        if seq >= len(text) - 2:
            return True

    # 반복 문자 (폰트 테이블: 迦迦迦, 求硅求求硅...)
    if len(text) >= 3:
        from collections import Counter
        max_freq = Counter(text).most_common(1)[0][1]
        if max_freq / len(text) >= 0.45:
            return True

    # 일본어 문자 유형 체크:
    # 히라가나, 가타카나, 통상 CJK, ASCII 전각/반각이 하나도 없는 텍스트는 노이즈
    has_japanese = any(
        '぀' <= ch <= 'ヿ'  # 히라가나/가타카나
        or '一' <= ch <= '鿿'  # CJK 통합 한자
        or '！' <= ch <= 'ﾟ'  # 전각 ASCII + 반각 가타카나
        or '0' <= ch <= '9'
        or 'A' <= ch <= 'z'
        or ch in '「」、。！？…　'
        for ch in text
    )
    if not has_japanese:
        return True

    return False

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
        # 최상위 kr
        if entry.get('kr'):
            kr_map[(chunk, entry['offset'])] = entry['kr']
        # segments (skill)
        for seg in entry.get('segments', []):
            if seg.get('kr'):
                kr_map[(chunk, seg['offset'])] = seg['kr']
        # lines (dialog / title / unknown)
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

# SJIS 밀도 임계값
TEXT_THRESHOLD = 0.05   # 이 미만 청크는 스킵
TITLE_THRESHOLD = 0.20  # 챕터 제목 파서 적용 최소 밀도

# 타입 우선순위 (낮을수록 우선)
TYPE_PRIORITY = {'skill': 0, 'dialog': 1, 'title': 2, 'unknown': 3}


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

    text_chunks = [(idx, dec, d) for idx, dec, d in chunks if d >= TEXT_THRESHOLD]
    print(f'텍스트 청크 ({TEXT_THRESHOLD:.0%} 이상): {len(text_chunks)}개')
    for idx, dec, d in text_chunks:
        print(f'  청크 {idx:2d}: {len(dec):6,}B  SJIS={d:.1%}')

    # ── 2. 텍스트 추출 ────────────────────────────────────────────────────
    all_entries: list[dict] = []

    for idx, dec, density in text_chunks:
        # 스킬/아이템 블록
        all_entries.extend(extract_skill_blocks(dec, idx))
        # 대화 블록
        all_entries.extend(extract_dialogue_blocks(dec, idx))
        # 챕터 제목 (밀도 높은 청크에서만)
        if density >= TITLE_THRESHOLD:
            all_entries.extend(extract_title_labels(dec, idx))
        # SJIS 런 폴백
        all_entries.extend(extract_sjis_runs(dec, idx, min_chars=4))

    # ── 3. 중복 제거 ───────────────────────────────────────────────────────
    # 구조화 엔트리(skill/dialog/title): 같은 jp가 여러 청크에 나올 때
    # → segments/lines가 많은(내용 풍부한) 쪽 우선
    def _entry_score(e: dict) -> int:
        return len(e.get('segments', [])) + len(e.get('lines', []))

    best_structured: dict[str, dict] = {}  # jp → best entry

    for entry in all_entries:
        if entry['type'] not in ('skill', 'dialog', 'title'):
            continue
        jp = entry['jp']
        if looks_like_noise(jp):
            continue
        if jp not in best_structured or _entry_score(entry) > _entry_score(best_structured[jp]):
            best_structured[jp] = entry

    # structured sub-text 집합 (desc/stat/lines jp — unknown dedup 제외용)
    structured_sub_texts: set[str] = set()
    for entry in best_structured.values():
        for seg in entry.get('segments', []):
            if seg['jp']:
                structured_sub_texts.add(seg['jp'])
        for line in entry.get('lines', []):
            if line['jp']:
                structured_sub_texts.add(line['jp'])

    # unknown 런: 노이즈 제거 + structured에 이미 포함된 텍스트 제거
    seen_unknown_jp: set[str] = set()
    unknown_entries: list[dict] = []

    for entry in all_entries:
        if entry['type'] != 'unknown':
            continue
        jp = entry['jp']
        if looks_like_noise(jp):
            continue
        if jp in best_structured or jp in structured_sub_texts:
            continue  # structured 엔트리에 포함된 텍스트
        if jp in seen_unknown_jp:
            continue
        seen_unknown_jp.add(jp)
        unknown_entries.append(entry)

    # 청크·오프셋 순 정렬
    final_entries = sorted(
        list(best_structured.values()) + unknown_entries,
        key=lambda e: (e['chunk'], e['offset'])
    )

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
