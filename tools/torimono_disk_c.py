"""포물장 DISK_C.DAT 스프라이트/타일 청크(2, 5~50) 디코드·인코드·재조립.

포맷 상세는 tools/TORIMONO.md "DISK_C.DAT 그래픽 포맷" 참조.
- 청크 1개 = 256타일 × 160바이트(5블록×32바이트), 디코드 시 256×256 RGBA.
- 편집용 PNG는 512×512(2배 최근접 확대)로 내보내고, 인코드 시 다시 2배 축소.
- 팔레트: 기본 PAL0(청크 2, 5~44, 47 등 대부분). 다른 팔레트가 필요한 청크(45·46·48~50)는
  --palette 로 R,G,B 16개를 직접 전달.
"""
import sys
import os
import struct
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_lz import decompress, compress
from compilegfx.container import chunked, tilesheet
from PIL import Image

PAL0 = [(0, 0, 0), (153, 170, 204), (85, 119, 136), (0, 85, 255), (0, 17, 170), (119, 187, 153),
        (51, 136, 68), (255, 187, 153), (221, 136, 102), (255, 0, 0), (136, 68, 34), (255, 238, 0),
        (187, 170, 17), (255, 221, 204), (255, 119, 187), (255, 255, 255)]

TILE_BYTES = 160
CHUNK_BYTES = 256 * TILE_BYTES  # 40960
NATIVE_SIZE = 256


def parse_chunk_table(data: bytes) -> list[int]:
    """0x000~0x3FF 테이블의 0이 아닌 seek 값 (마지막 원소는 EOF 경계).

    포맷은 幻世 엔진 공통이라 compile-gfx로 옮겼다.
    """
    return chunked.chunk_offsets(data)


def decode_tile_chunk(raw: bytes, palette=PAL0) -> Image.Image:
    """청크 하나(256타일)를 256x256 RGBA로. 디코딩은 compile-gfx가 담당.

    포맷 자체(5플레인 타일, plane 0 = 투명 마스크)는 이 타이틀 고유가 아니라
    幻世 엔진 공통이라 `compilegfx.container.tilesheet`로 옮겼다. 여기 남은 건
    이 프로젝트의 편집 워크플로 제약 — 청크는 정확히 256타일이어야 하고
    (인코더가 같은 크기로 되돌려놔야 재삽입이 성립), 기본 팔레트는 PAL0.
    """
    assert len(raw) == CHUNK_BYTES, f'청크 크기 {len(raw)} != {CHUNK_BYTES} (스프라이트/타일 포맷 아님)'
    return tilesheet.decode(raw, palette, cols=16)


def _nearest_palette_index(rgb, palette) -> int:
    best_i, best_d = 0, None
    for i, (r, g, b) in enumerate(palette):
        d = (rgb[0] - r) ** 2 + (rgb[1] - g) ** 2 + (rgb[2] - b) ** 2
        if best_d is None or d < best_d:
            best_d, best_i = d, i
    return best_i


def _downsample_2x(img: Image.Image) -> Image.Image:
    """2배 최근접 확대본을 원래 해상도로 복원 (2x2 블록 다수결)."""
    w, h = img.size
    out = Image.new('RGBA', (w // 2, h // 2))
    src, dst = img.load(), out.load()
    warned = 0
    for by in range(h // 2):
        for bx in range(w // 2):
            block = [src[bx * 2 + dx, by * 2 + dy] for dx in (0, 1) for dy in (0, 1)]
            if len(set(block)) > 1 and {p[3] for p in block} != {0}:
                warned += 1
                if warned <= 20:
                    print(f'  경고: 2x2 블록 불일치 (px {bx*2},{by*2}): {block}', file=sys.stderr)
            counts = {}
            for p in block:
                counts[p] = counts.get(p, 0) + 1
            dst[bx, by] = max(counts, key=counts.get)
    if warned:
        print(f'  총 {warned}개 블록이 2배 격자를 벗어나 다수결로 처리 — 편집 확인 권장', file=sys.stderr)
    return out


def encode_tile_chunk(img: Image.Image, palette=PAL0) -> bytes:
    img = img.convert('RGBA')
    if img.size == (512, 512):
        img = _downsample_2x(img)
    elif img.size != (NATIVE_SIZE, NATIVE_SIZE):
        raise ValueError(f'지원하지 않는 이미지 크기: {img.size} (256x256 또는 512x512만 가능)')
    px = img.load()
    out = bytearray(CHUNK_BYTES)
    for tile in range(256):
        tr, tc = divmod(tile, 16)
        base = tile * TILE_BYTES
        for ry in range(16):
            w0 = w1 = w2 = w3 = w4 = 0
            for bit in range(16):
                x, y = tc * 16 + bit, tr * 16 + ry
                r, g, b, a = px[x, y]
                if a < 128:
                    continue  # p0=0, 나머지 비트도 0으로 남김
                shift = 15 - bit
                w0 |= 1 << shift
                idx4 = _nearest_palette_index((r, g, b), palette)
                if idx4 & 1: w1 |= 1 << shift
                if idx4 & 2: w2 |= 1 << shift
                if idx4 & 4: w3 |= 1 << shift
                if idx4 & 8: w4 |= 1 << shift
            for p, w in enumerate((w0, w1, w2, w3, w4)):
                off = base + p * 32 + ry * 2
                out[off] = (w >> 8) & 0xFF
                out[off + 1] = w & 0xFF
    return bytes(out)


def cmd_decode(args):
    with open(args.src, 'rb') as f:
        data = f.read()
    seeks = parse_chunk_table(data)
    raw = decompress(data, seeks[args.chunk])
    img = decode_tile_chunk(raw)
    img = img.resize((512, 512), Image.NEAREST)
    out = args.out or f'c{args.chunk:02d}.png'
    img.save(out)
    print(f'chunk {args.chunk} → {out} (512x512, 2배 확대)')


def rebuild_disk_c(data: bytes, edits: dict) -> bytes:
    """원본 DISK_C.DAT 바이트 + {chunk_idx: png_path} → 재조립된 DISK_C.DAT 바이트.

    edits 에 없는 청크는 원본 압축 바이트를 그대로 재사용(무손실).
    edits 에 있는 청크는 PNG(256x256 또는 512x512)를 인코드+재압축해 교체.
    torimono_inserter.py 의 DISK_C_EDITS 재삽입에도 재사용된다.
    """
    seeks = parse_chunk_table(data)  # 마지막 원소는 EOF 경계
    n_chunks = len(seeks) - 1
    compressed = []
    for i in range(n_chunks):
        start, end = seeks[i], seeks[i + 1]
        if i in edits:
            img = Image.open(edits[i])
            raw = encode_tile_chunk(img)
            comp = compress(raw)
            print(f'chunk {i}: {edits[i]} 인코드+재압축 ({end-start}B → {len(comp)}B)')
            compressed.append(comp)
        else:
            compressed.append(data[start:end])  # 원본 압축 바이트 그대로 재사용

    # 테이블 재계산: 슬롯 0..n_chunks-1 = 청크 시작, 슬롯 n_chunks = EOF 경계
    table = bytearray(0x400)
    pos = 0x400
    new_seeks = []
    for comp in compressed:
        new_seeks.append(pos)
        pos += len(comp)
    new_seeks.append(pos)  # EOF 경계

    for i, seek in enumerate(new_seeks):
        struct.pack_into('<HH', table, i * 4, seek >> 16, seek & 0xFFFF)

    return bytes(table) + b''.join(compressed)


def cmd_encode(args):
    with open(args.src, 'rb') as f:
        data = f.read()

    edits = {}
    for spec in args.edit:
        idx_str, png_path = spec.split('=', 1)
        edits[int(idx_str)] = png_path

    out_data = rebuild_disk_c(data, edits)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'wb') as f:
        f.write(out_data)
    print(f'{args.out} 생성 ({len(out_data)}B, 원본 {len(data)}B)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_dec = sub.add_parser('decode', help='청크를 편집용 PNG로 추출')
    p_dec.add_argument('chunk', type=int)
    p_dec.add_argument('out', nargs='?')
    p_dec.add_argument('--src', default='original/torimono/DISK_C.DAT')
    p_dec.set_defaults(func=cmd_decode)

    p_enc = sub.add_parser('encode', help='편집된 PNG를 재삽입해 DISK_C.DAT 재조립')
    p_enc.add_argument('edit', nargs='+', metavar='CHUNK=PNG', help='예: 31=translation/torimono/graphics/c31.png')
    p_enc.add_argument('--src', default='original/torimono/DISK_C.DAT')
    p_enc.add_argument('--out', default='build/torimono/DISK_C.DAT')
    p_enc.set_defaults(func=cmd_encode)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
