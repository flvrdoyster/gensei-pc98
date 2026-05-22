"""GS.OVL 캐릭터 이름 한글 패치"""
import sys, json, os
try:
    _d = os.path.dirname(os.path.abspath(__file__))
    _TOOLS = _d if os.path.exists(os.path.join(_d, 'compile_lz.py')) else os.path.join(os.getcwd(), 'tools')
except NameError:
    _TOOLS = os.path.join(os.getcwd(), 'tools')
sys.path.insert(0, _TOOLS)
from compile_lz import decompress, compress

with open(os.path.join(_TOOLS, 'charmap.json')) as f:
    charmap = json.load(f)

def encode_kr(text):
    result = bytearray()
    for ch in text:
        if ch in charmap:
            code = charmap[ch]
            result.append(int(code[:2], 16))
            result.append(int(code[2:], 16))
        else:
            raise ValueError(f'charmap에 없음: {ch!r}')
    return bytes(result)

NAMES = [
    (0x5638, bytes.fromhex('8358837d836283568385'), '스마슈'),
    (0x564f, bytes.fromhex('83748340815b838a8393'), '화린'),
    (0x5666, bytes.fromhex('834c838a'),             '키리'),
    (0x5677, bytes.fromhex('8379836783448380'),     '페톰'),
    (0x568c, bytes.fromhex('8341835e815b837a815b'), '아타호'),
    (0x56a3, bytes.fromhex('8356815b8389'),         '실라'),
]

src = sys.argv[1] if len(sys.argv) > 1 else 'original/kitan/data/GS.OVL'

with open(src, 'rb') as f:
    raw = f.read()
data = bytearray(decompress(raw))

for offset, orig_bytes, kr in NAMES:
    new_bytes = encode_kr(kr)
    end = offset + len(orig_bytes)
    assert data[end] == 0x65, f'0x{offset:X}: 0x65 없음 (got 0x{data[end]:02X})'
    sep = end + 1
    while data[sep:sep+2] != bytes([0x64, 0xF6]):
        sep += 1
    slot = sep - offset
    fill = slot - len(new_bytes) - 1
    assert fill >= 0 and fill % 2 == 0, f'fill={fill}'
    data[offset:sep] = new_bytes + b'\x65' + b'\x00\xF4' * (fill // 2)
    print(f'0x{offset:X}: {orig_bytes.decode("shift_jis")} -> {kr} ({len(orig_bytes)}->{len(new_bytes)}B, fill={fill//2})')

recompressed = compress(bytes(data))
print(f'원본: {len(raw)}B, 재압축: {len(recompressed)}B')

with open(src, 'wb') as f:
    f.write(recompressed)
print('저장 완료')
