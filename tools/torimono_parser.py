"""
환세포물장 텍스트 추출기
========================

사용법:
  python3 tools/torimono_parser.py original/torimono

DISK_B.DAT 에서 텍스트를 추출하여
translation/torimono/translation.json 을 생성.

확정 제어코드:
  62 00 XX XX  = 블록 시작 (직접 텍스트 또는 대화 컨테이너)
  64 XX        = 이름/레이블 블록 (XX=00이면 64 00 XX XX 챕터 제목)
  64 0a / 0c   = 스탯 라벨 (인수 없음)
  65           = 블록 종료
  67 XX        = 화자 마커
  6b 00 80 77 00 = 화자 없는 대화 블록
  6b 00 81 65    = 빈 대화 슬롯
  6d 08        = 적/아이템 이름 블록
  6e 00 67     = 대화 블록 앵커
  72 01 [85XX] = UI 컬럼 헤더 (반각 문자열)
  72 02 [SJIS] = 스탯 이름
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
from compile_lz import decompress
from compilegfx.container import chunked
from compile_script import walk as walk_script, BASE_SPEC
from dataclasses import replace

# 엔딩 평가 화면의 랭크 제목 『…』 은 `63 fb 『…』 63 ff` 로 감싸여 있다.
# BASE_SPEC 워커는 0x63 을 미지 바이트로 보고 누적 텍스트를 버려(cur_text='')
# 제목 줄을 통째로 놓친다. 직후가 SJIS 일 때만 발동하는 마커로 처리해 캡처한다.
# (BASE_SPEC 은 쾌도전과 공유하므로 건드리지 않고 포물장 전용 스펙으로 분기)
TORI_SPEC = replace(
    BASE_SPEC,
    markers={**BASE_SPEC.markers, (0x63, 0xfb): 'text', (0x63, 0xff): 'text'},
)

# ── SJIS 유틸 ─────────────────────────────────────────────────────────────────

def is_sjis_pair(b1: int, b2: int) -> bool:
    # compile_lz.is_sjis_lead는 0xe0-0xfc까지 허용하지만,
    # 0xf0-0xfc 범위는 x86 코드 오인식이 많아 표준 범위(0xe0-0xef)로 제한
    std_lead = (0x81 <= b1 <= 0x9f) or (0xe0 <= b1 <= 0xef)
    return std_lead and (0x40 <= b2 <= 0xFC) and b2 != 0x7F

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
    """청크 테이블 → [(seek_pos, compressed_size), ...] (seek 순 정렬).

    테이블 포맷(0x000~0x3FF, 4바이트 엔트리)은 幻世 엔진 공통이라
    compile-gfx가 들고 있다. 여기서는 압축 크기까지 붙여 돌려준다.
    """
    offsets = chunked.chunk_offsets(data)
    return [(offsets[i], offsets[i + 1] - offsets[i]) for i in range(len(offsets) - 1)]

# ── 메인 ──────────────────────────────────────────────────────────────────────

# 명시적으로 지정된 노이즈 청크 (그래픽/비트맵 데이터 — SJIS 밀도가 높아도 텍스트 아님)
NOISE_CHUNKS = {8, 22, 35, 54, 55, 59, 60, 69, 70, 71}


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

    # ── 1. 청크 테이블 파싱 & 압축 해제 ────────────────────────────────────
    chunks_info = parse_chunk_table(data)
    print(f'\n청크 수: {len(chunks_info)}개')

    chunks: list[tuple[int, bytes, float]] = []
    for idx, (seek, _) in enumerate(chunks_info):
        dec     = decompress(data, seek)
        density = sjis_density(dec)
        chunks.append((idx, dec, density))

    text_chunks = [(idx, dec, d) for idx, dec, d in chunks
                   if idx not in NOISE_CHUNKS]
    print(f'처리 청크 (노이즈 제외): {len(text_chunks)}개')
    for idx, dec, d in text_chunks:
        print(f'  청크 {idx:2d}: {len(dec):6,}B  SJIS={d:.1%}')

    # ── 2. 텍스트 추출 (공유 오피코드 워커) ────────────────────────────────────
    # compile_script.walk: 환세 시리즈 공유 워커. 오피코드를 인자 길이만큼 정확히
    # 소비해 텍스트만 캡처한다. 사후 노이즈 필터 없음 — 완전 파싱이 목표.
    all_entries: list[dict] = []
    for idx, dec, density in text_chunks:
        for blk in walk_script(dec, TORI_SPEC):
            lines = []
            for ln in blk['lines']:
                jp = ln['jp']
                lines.append({
                    'offset': ln['offset'],
                    'jp':     jp,
                    'jp_len': len(jp.encode('shift_jis', errors='replace')),
                    'kr':     '',
                })
            if not lines:
                continue
            all_entries.append({
                'file':   'DISK_B.DAT',
                'chunk':  idx,
                'offset': blk['offset'],
                'type':   blk['type'],
                'jp':     '\n'.join(l['jp'] for l in lines),
                'kr':     '',
                'lines':  lines,
            })

    final_entries = sorted(all_entries, key=lambda e: (e['chunk'], e['offset']))

    # ── 3. 기존 번역(kr) 무손실 이식 ──────────────────────────────────────────
    #  a) 정확한 (chunk, offset) 매칭
    #  b) 어긋나면 같은 청크·동일 JP를 근접(±8) 매칭 — 라벨 offset 이동 흡수
    #  c) 그래도 못 붙인 kr 줄은 옛 엔트리를 통째로 carry-over → 번역 무손실
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as f:
            old_json = json.load(f)
        old_lines = []   # (chunk, offset, jp, kr, tag, speaker)
        for e in old_json.get('entries', []):
            for l in e.get('lines', []):
                old_lines.append((e['chunk'], l['offset'], l['jp'],
                                  l.get('kr', ''), l.get('tag'), l.get('speaker')))

        by_key, by_cjp = {}, {}
        for e in final_entries:
            for l in e['lines']:
                by_key[(e['chunk'], l['offset'])] = l
                by_cjp.setdefault((e['chunk'], l['jp']), []).append(l)

        kr_total = n_attach = n_carry = 0
        carry: dict = {}
        for chunk, off, jp, kr, tag, speaker in old_lines:
            target = by_key.get((chunk, off))
            if target is None:
                cands = [l for l in by_cjp.get((chunk, jp), []) if abs(l['offset'] - off) <= 8]
                if cands:
                    target = min(cands, key=lambda l: abs(l['offset'] - off))
            if kr.strip():
                kr_total += 1
            if target is not None:
                if tag is not None:
                    target['tag'] = tag
                if speaker is not None:
                    target['speaker'] = speaker
                if kr.strip() and not target['kr']:
                    target['kr'] = kr
                    n_attach += 1
            elif kr.strip():
                line = {'offset': off, 'jp': jp,
                        'jp_len': len(jp.encode('shift_jis', errors='replace')), 'kr': kr}
                if tag is not None:
                    line['tag'] = tag
                if speaker is not None:
                    line['speaker'] = speaker
                carry.setdefault(chunk, []).append(line)
                n_carry += 1

        for chunk, lns in carry.items():
            for l in lns:
                off = l['offset']
                # 줄 offset 이 lines 범위에 드는 같은 청크 entry 를 찾아 그 안에 삽입한다.
                # (별도 top-level carried 엔트리로 빼면 entry 단위 정렬에 밀려 위치가
                #  어긋남 — 예: 「いた！(5688)가 같은 블록의 うおー(5697)보다 뒤로 감)
                host = None
                for e in final_entries:
                    if e['chunk'] == chunk and e.get('lines'):
                        offs = [x['offset'] for x in e['lines']]
                        if min(offs) <= off <= max(offs):
                            host = e
                            break
                if host is not None:
                    host['lines'].append(l)
                    host['lines'].sort(key=lambda x: x['offset'])
                else:
                    # 어느 블록 범위에도 안 들면 별도 carried 엔트리로 (기존 동작)
                    final_entries.append({
                        'file': 'DISK_B.DAT', 'chunk': chunk, 'offset': off,
                        'type': 'carried', 'jp': l['jp'], 'kr': l['kr'], 'lines': [l],
                    })
        final_entries.sort(key=lambda e: (e['chunk'], e['offset']))
        print(f'\nkr 이식: 총 {kr_total} → 부착 {n_attach} + carry-over {n_carry} '
              f'(손실 {kr_total - n_attach - n_carry})')

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
    game_dir = sys.argv[1] if len(sys.argv) > 1 else 'original/torimono'
    main(game_dir)
