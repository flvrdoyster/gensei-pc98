"""환세쾌도전 인서터.

translation/kaitou/translation.json 의 KR 을 DISK_B.DAT 에 재삽입한다.

구조
----
DISK_B.DAT = [0x400 청크 테이블] + [LZ 압축 청크들 순차]
- 테이블: 4바이트 엔트리(CX,DX LE) → seek_pos = (CX<<16)|DX. 청크 시작 위치.
- 각 청크는 compile_lz 로 압축돼 있음.

삽입 절차
--------
1. 청크 디컴프레스
2. KR 을 **JP 바이트 길이 안에서** in-place 패치 (텍스트가 밀리면 청크 내부
   포인터 테이블이 깨지므로 길이 불변 필수 — 희담/풍광전과 동일 제약)
3. 패치된 청크만 재압축 (나머지는 원본 압축 그대로)
4. 재조립: 청크 순차 배치 + 테이블 seek 갱신 (재압축 크기 차이 흡수)

KR 길이 제약
-----------
청크 내부에 텍스트를 가리키는 포인터 테이블이 있어(`6c 01 [ptr]`, 스킬/맵 대사),
텍스트가 밀리면 깨진다. 따라서 KR 인코딩 결과는 JP 바이트 수 이하여야 한다.
초과 시 경고 후 건너뜀.
"""

import json
import os
import struct
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_lz import decompress, compress

TABLE_SIZE = 0x400


def read_table(data):
    """청크 테이블 슬롯 읽기 → [(slot_offset, seek), ...] (비-제로만)."""
    slots = []
    for off in range(0, TABLE_SIZE, 4):
        cx = struct.unpack_from('<H', data, off)[0]
        dx = struct.unpack_from('<H', data, off + 2)[0]
        seek = (cx << 16) | dx
        if seek:
            slots.append((off, seek))
    return slots


def reassemble(data, chunk_bytes):
    """원본 data + {seek: 새 압축바이트} → 재조립된 DISK_B.DAT.

    chunk_bytes 에 없는 seek 은 원본 압축 바이트를 그대로 사용.
    청크는 원본 seek 오름차순으로 0x400 뒤에 순차 배치, 테이블 seek 갱신.
    """
    slots = read_table(data)
    seeks = sorted(set(s for _, s in slots))
    # 원본에서 각 청크의 압축 바이트 범위 (seek ~ 다음 seek 또는 EOF)
    orig = {}
    for i, sk in enumerate(seeks):
        end = seeks[i + 1] if i + 1 < len(seeks) else len(data)
        orig[sk] = data[sk:end]

    # 새 레이아웃: seek 순서대로, 0x400부터 순차
    out = bytearray(data[:TABLE_SIZE])
    new_off = {}
    cur = TABLE_SIZE
    for sk in seeks:
        comp = chunk_bytes.get(sk, orig[sk])
        new_off[sk] = cur
        out += comp
        cur += len(comp)

    # 테이블 슬롯 갱신 (같은 seek 을 가리키던 모든 슬롯을 새 오프셋으로)
    for slot_off, sk in slots:
        no = new_off[sk]
        struct.pack_into('<HH', out, slot_off, (no >> 16) & 0xFFFF, no & 0xFFFF)

    return bytes(out)


from hukyou_inserter import encode_korean, fit_length, load_charmap


def _has_halfwidth_lead(data):
    """SJIS 바이트열에 0x85 *lead* 바이트(반각 영역)가 있는지.
    0x85가 trail 바이트인 경우(예: ュ = 0x83 0x85)는 반각이 아니므로 제외."""
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x85:
            return True
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n:
            i += 2  # SJIS 쌍 — trail 바이트 건너뜀
        else:
            i += 1
    return False


def _split_cost_suffix(buf, offset, jp_len):
    """원본 바이트에서 이름(전각)/코스트(반각 0x85) 경계를 찾는다.

    스킬 라벨(`爆炎の呪文(MP8)`)은 전각 이름 + 반각 코스트 `(MP8)`(인라인 64 01 포함).
    이름만 번역하고 코스트는 보존해야 하므로 경계를 잡아준다.
    코스트가 있으면 (name_end, cost_end), 없으면 (None, None).
    """
    n = len(buf)
    name_limit = min(offset + jp_len, n)
    i = offset
    name_end = None
    while i < name_limit:
        b = buf[i]
        if b == 0x85:               # 반각 코스트 시작
            name_end = i
            break
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n:
            i += 2                  # 전각 이름 SJIS 쌍
        else:
            return None, None       # 제어 바이트 — 코스트 라벨 아님
    if name_end is None or name_end == offset:
        return None, None
    # 코스트 끝: 반각(0x85) 쌍 + 인라인 자릿수 제어(64 01), 종결자 전까지
    j = name_end
    while j < n:
        b = buf[j]
        if b == 0x85 and j + 1 < n:
            j += 2
        elif b == 0x64 and j + 1 < n and buf[j + 1] == 0x01:
            j += 2
        else:
            break
    return name_end, j


def collect_chunk_replacements(translation, charmap):
    """청크별 교체 목록: {chunk: [(offset, jp_len, kr_str), ...]}.

    인코딩·접미사 보존은 patch_chunk(원본 바이트 접근 가능)에서 처리.
    """
    by_chunk = {}
    skipped = []
    for e in translation.get('entries', []):
        ch = e['chunk']
        for line in e.get('lines', []):
            if line.get('tag') == 'ignore':
                continue
            kr = line.get('kr', '')
            if not kr.strip():
                continue
            offset = line['offset']
            jp = line['jp']
            jp_len = line.get('jp_len', len(jp.encode('shift_jis', errors='replace')))
            try:
                old = jp.encode('shift_jis')
            except UnicodeEncodeError:
                old = None
            # jp 길이 불일치/인코딩 불가는 패치 위험 → 스킵 (0x85는 lead만 체크 — 코스트 라벨은
            # jp 인코딩상 전각이라 통과하고, patch_chunk가 원본 바이트로 코스트 보존)
            if old is None or len(old) != jp_len or _has_halfwidth_lead(old):
                skipped.append((ch, offset, jp, kr))
                continue
            by_chunk.setdefault(ch, []).append((offset, jp_len, kr))
    return by_chunk, skipped


def patch_chunk(dec, replacements, charmap):
    """디컴프레스된 청크에 in-place 교체 (길이 불변). 코스트 접미사는 보존."""
    buf = bytearray(dec)
    for offset, jp_len, kr in sorted(replacements, key=lambda r: r[0], reverse=True):
        try:
            kr_enc = encode_korean(kr, charmap)
        except UnicodeEncodeError:
            kr_enc = encode_korean(kr, charmap, use_halfwidth=True)
        name_end, cost_end = _split_cost_suffix(buf, offset, jp_len)
        if name_end is not None:
            # 코스트 라벨: 이름 영역만 교체, 코스트(반각 + 인라인 64 01) 보존
            name_bytes = bytes(buf[offset:name_end])
            cost_bytes = bytes(buf[name_end:cost_end])
            kr_fit = fit_length(name_bytes, kr_enc, context=f'0x{offset:X}: {kr}')
            buf[offset:cost_end] = kr_fit + cost_bytes
        else:
            old = bytes(buf[offset:offset + jp_len])
            buf[offset:offset + jp_len] = fit_length(old, kr_enc, context=f'0x{offset:X}: {kr}')
    return bytes(buf)


def _compress_one(args):
    """병렬 워커: (seek, 패치된 디컴프레스 바이트) → (seek, 압축 바이트)."""
    seek, dec2 = args
    return seek, compress(dec2)


def run(game_dir):
    """KR 패치 → build/<title>/DISK_B.DAT. (컨벤션: 데이터만 출력, FDI는 patch_fdi)."""
    import kaitou_parser as kp
    from multiprocessing import Pool
    path = os.path.join(game_dir, 'DISK_B.DAT')
    data = open(path, 'rb').read()
    title = os.path.basename(game_dir.rstrip('/\\'))
    tj = json.load(open(os.path.join(PROJECT_ROOT, 'translation', title, 'translation.json'), encoding='utf-8'))
    charmap = load_charmap()

    by_chunk, skipped = collect_chunk_replacements(tj, charmap)
    chunks = kp.parse_chunk_table(data)

    # 패치된 청크 디컴프레스 + in-place 교체
    work = []
    n_lines = 0
    for idx, (seek, _) in enumerate(chunks):
        if idx not in by_chunk:
            continue
        dec = decompress(data, seek)
        work.append((seek, patch_chunk(dec, by_chunk[idx], charmap)))
        n_lines += len(by_chunk[idx])

    # 재압축 병렬화 (청크는 서로 독립)
    if work:
        with Pool() as pool:
            chunk_bytes = dict(pool.map(_compress_one, work))
    else:
        chunk_bytes = {}

    rebuilt = reassemble(data, chunk_bytes)
    out_dir = os.path.join(PROJECT_ROOT, 'build', title)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'DISK_B.DAT')
    with open(out_path, 'wb') as f:
        f.write(rebuilt)
    print(f'패치: {n_lines}줄 / {len(by_chunk)}청크, 반각 라벨 스킵 {len(skipped)}건')
    print(f'DISK_B.DAT: {len(data)} → {len(rebuilt)} bytes  →  {out_path}')
    return out_path, skipped


def patch_fdi(game_dir='original/kaitou'):
    """build/<title>/DISK_B.DAT 를 배포 FDI(emulator/rom/kaitou_kr.fdi)에 교체 →
    build/<title>/kaitou_kr.fdi 생성. 희담/풍광전과 동일하게 run()과 분리.

    베이스는 배포 FDI 자체. DISK_B는 항상 원본 소스에서 새로 패치하고 CONFIG.SYS
    EMM386 제거도 멱등이라, 배포 FDI를 베이스로 반복 패치해도 결과는 동일.
    (별도 원본 kaitou.fdi 불필요)"""
    import shutil, subprocess
    from pc98disk import prepare_output_copy
    title = os.path.basename(game_dir.rstrip('/\\'))
    out_dir = os.path.join(PROJECT_ROOT, 'build', title)
    disk_b = os.path.join(out_dir, 'DISK_B.DAT')
    base_fdi = os.path.join(PROJECT_ROOT, 'emulator', 'rom', 'kaitou_kr.fdi')
    if not os.path.exists(disk_b):
        raise FileNotFoundError(f'{disk_b} 없음 — run() 먼저 실행')
    out_fdi = prepare_output_copy(base_fdi, out_dir, 'kaitou_kr.fdi')
    pc98 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pc98disk.py')
    subprocess.run([sys.executable, pc98, 'add', out_fdi, disk_b], check=True)

    # 웹 에뮬(Emscripten np2kai)은 EMM386(386 보호모드)을 못 돌려 부팅이 멈춘다.
    # 게임은 EMM386 없이도 동작하므로 CONFIG.SYS에서 제거 (dos=umb,high → dos=high).
    # 실기/RetroArch는 EMM386 OK — 이건 웹 포팅 전용 적응.
    # pc98disk add 는 로컬 파일명을 그대로 쓰므로 basename 이 'CONFIG.SYS' 여야 교체됨
    import tempfile
    cfg_dir = tempfile.mkdtemp(prefix='kaitou-cfg-')
    cfg_tmp = os.path.join(cfg_dir, 'CONFIG.SYS')
    subprocess.run([sys.executable, pc98, 'get', out_fdi, 'CONFIG.SYS', cfg_tmp], check=True)
    cfg_lines = open(cfg_tmp, encoding='cp932', errors='replace').read().splitlines()
    cfg_lines = [l for l in cfg_lines if 'emm386' not in l.lower()]
    cfg_lines = ['dos=high' if l.strip().lower().startswith('dos=') else l for l in cfg_lines]
    open(cfg_tmp, 'w', encoding='cp932', errors='replace').write('\n'.join(cfg_lines) + '\n')
    subprocess.run([sys.executable, pc98, 'add', out_fdi, cfg_tmp], check=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    print('CONFIG.SYS: EMM386 제거 (웹 에뮬 호환)')

    print(f'FDI: {out_fdi}')
    return out_fdi


def _selftest(game_dir):
    """패치 없이 재조립 → 각 청크 디컴프레스가 원본과 동일한지 검증."""
    import kaitou_parser as kp
    path = os.path.join(game_dir, 'DISK_B.DAT')
    data = open(path, 'rb').read()
    chunks = kp.parse_chunk_table(data)

    # 모든 청크 재압축 → chunk_bytes
    chunk_bytes = {}
    for seek, _ in chunks:
        dec = decompress(data, seek)
        chunk_bytes[seek] = compress(dec)

    rebuilt = reassemble(data, chunk_bytes)
    rb_chunks = kp.parse_chunk_table(rebuilt)
    print(f'원본 {len(data)}B → 재조립 {len(rebuilt)}B, 청크 {len(chunks)}→{len(rb_chunks)}')

    ok = bad = 0
    for (s0, _), (s1, _) in zip(chunks, rb_chunks):
        d0 = decompress(data, s0)
        d1 = decompress(rebuilt, s1)
        if d0 == d1:
            ok += 1
        else:
            bad += 1
            print(f'  ✗ 청크 불일치 (원 seek 0x{s0:x})')
    print(f'디컴프레스 동등: {ok}/{ok + bad} 청크')
    return bad == 0


if __name__ == '__main__':
    game_dir = sys.argv[1] if len(sys.argv) > 1 else 'original/kaitou'
    if '--selftest' in sys.argv:
        _selftest(game_dir)
    else:
        run(game_dir)
        if '--no-fdi' not in sys.argv:
            patch_fdi(game_dir)
