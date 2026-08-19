#!/usr/bin/env python3
"""번역 검수 lint — translation.json의 품질 문제를 한 번에 점검.

사용법:
  python3 tools/lint.py <title>          # 요약
  python3 tools/lint.py <title> -v       # 상세(각 항목 위치까지)

4타이틀 전부 지원한다. entries 포맷(kaitou·torimono)과 dialogs 포맷(hukyou·kitan)의
구조 차이는 walk_lines() 가 흡수한다.

검사 항목:
  미번역      : 카나 포함 2자+ 원문인데 kr이 빈 줄 (tag=ignore는 의도적 제외라 안 셈)
  잘림        : encode_korean(kr) 가 jp_len(슬롯)을 초과 → 인서트 시 잘림
  깨진문자    : kr 에 U+FFFD 포함
  일관성      : 같은 jp 에 서로 다른 kr (용어/표현 불일치 후보)
  offset 정합 : (kaitou 전용) jp 가 실제 디컴프 위치에 없음(어긋남) / 선행 글자 누락

종료코드: 버그류(잘림·깨진문자·offset)가 하나라도 있으면 1, 아니면 0.
  → 배포/빌드 전 게이트로 쓸 수 있다. 미번역·일관성은 검수 정보라 코드에 반영 안 함.

editor.py 통합:
  analyze(title, check_offset=...) 로 결과 dict 를 얻는다. offset 검사는 원본
  디컴프가 필요해 무거우므로, 빌드 토스트용 호출은 check_offset=False 로 끈다.
"""

import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hukyou_inserter import load_charmap, encode_korean

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kana(s):
    return any(0x3040 <= ord(c) <= 0x30FF for c in s)


def enc_len(kr, cm):
    """인코딩 후 바이트 길이. 인코딩 불가 문자가 있으면 None(잘림 검사 skip).

    U+FFFD 같은 문자는 전각·반각 어느 쪽으로도 인코딩이 안 된다. 그 줄은 어차피
    '깨진문자'로 따로 잡히므로, 여기서 예외를 터뜨려 검사 전체를 죽이지 않는다.
    """
    for kwargs in ({}, {'use_halfwidth': True}):
        try:
            return len(encode_korean(kr, cm, **kwargs))
        except UnicodeEncodeError:
            continue
    return None


def _textchar(pair):
    """2바이트가 가나/한자 SJIS 1글자면 그 글자, 아니면 None."""
    try:
        ch = pair.decode('shift_jis')
    except Exception:
        return None
    if len(ch) != 1:
        return None
    o = ord(ch)
    return ch if (0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF) else None


def _check_offset_kaitou(d):
    """kaitou 전용: jp 가 원본 디컴프 위치에 실제로 있는지 + 선행 글자 누락.

    반환 (mismatch, leading). 원본/파서가 없으면 (None, None) — 검사 skip.
    """
    try:
        from compile_lz import decompress
        import kaitou_parser as kp
    except Exception:
        return None, None
    disk = os.path.join(PROJECT_ROOT, 'original', 'kaitou', 'DISK_B.DAT')
    if not os.path.exists(disk):
        return None, None
    data = open(disk, 'rb').read()
    chunks = kp.parse_chunk_table(data)
    decs = {}

    def dec_of(ci):
        if ci not in decs:
            decs[ci] = decompress(data, chunks[ci][0])
        return decs[ci]

    covered = defaultdict(set)
    for e in d['entries']:
        ci = e.get('chunk')
        if ci is None or ci >= len(chunks):
            continue
        for l in e['lines']:
            enc = l['jp'].encode('shift_jis', 'replace')
            for b in range(l['offset'], l['offset'] + len(enc)):
                covered[ci].add(b)

    mismatch, leading = [], []
    for e in d['entries']:
        ci = e.get('chunk')
        if ci is None or ci >= len(chunks):
            continue
        dec = dec_of(ci)
        for l in e['lines']:
            jp, off = l['jp'], l['offset']
            try:
                enc = jp.encode('shift_jis')
            except Exception:
                continue
            # offset 어긋남: 실제 위치가 jp 와 다름.
            #   1글자 기호 제외 / 실제 저장이 반각(0x85)이면 전각 jp 와 비교 불가 → 가짜양성
            if len(jp) >= 2:
                actual = dec[off:off + len(enc)]
                if b'\x85' not in actual and actual != enc:
                    mismatch.append((f"c{ci}:{off}", jp))
            # 선행 글자 누락: 텍스트 라인 바로 앞의 미점유 가나/한자
            #   (64 00 XX XX 제어 인자, 예 도감 헤더 蓬 은 제외)
            if len(jp) >= 2 and kana(jp):
                p = off - 2
                if p >= 0 and p not in covered[ci] and dec[p - 2:p] != b'\x64\x00':
                    ch = _textchar(dec[p:off])
                    if ch:
                        leading.append((f"c{ci}:{off}", ch, jp[:16]))
    return mismatch, leading


# 정규화 키: 공백·약물·특수문자를 빼고 글자(가나·한자·영숫자)만 남긴다.
# editor.py 의 normJp() 와 문자 범위가 반드시 일치해야 매칭된다.
_NORM_KEEP = re.compile(r'[0-9A-Za-z０-ｚ぀-ヿ一-鿿｡-ﾟ]+')


def _norm_jp(s):
    return ''.join(_NORM_KEEP.findall(s or ''))


def walk_lines(d):
    """포맷 무관하게 (위치라벨, 번역 line dict) 를 산출.

    kaitou·torimono: entries[].lines
    hukyou·kitan   : dialogs[].lines + items[].name·stat·desc + ui·gsovl·demo[]

    위치라벨은 청크 기반이면 `c12:3456`, 파일 기반이면 `STAGE1.CMD:3456`,
    파일이 없는 묶음은 `items:3456`·`ui:3456` 처럼 섹션명을 쓴다.
    """
    def emit(prefix, line):
        return f"{prefix}:{line.get('offset', '?')}", line

    if 'entries' in d:
        for e in d['entries']:
            prefix = f"c{e['chunk']}" if 'chunk' in e else str(e.get('file', '?'))
            for l in e.get('lines', []):
                yield emit(prefix, l)
    else:
        for dl in d.get('dialogs', []):
            prefix = str(dl.get('file', 'dialogs'))
            for l in dl.get('lines', []):
                yield emit(prefix, l)
        for it in d.get('items', []):
            for l in (it.get('name'), it.get('stat')):
                if l:
                    yield emit('items', l)
            for l in it.get('desc', []):
                yield emit('items', l)
        for k in ('ui', 'gsovl', 'demo'):
            for l in d.get(k, []):
                yield emit(k, l)


def iter_lines(d):
    """walk_lines 의 line 부분만 (용어집 등 위치가 필요 없는 곳에서 사용)."""
    for _, l in walk_lines(d):
        yield l


SERIES_TITLES = ['hukyou', 'kitan', 'kaitou', 'torimono']


def series_glossary(prefer_title=None):
    """시리즈 전 타이틀의 jp → {kr, t(출처 타이틀)} 맵.

    같은 jp가 여러 타이틀에 있으면 prefer_title 의 번역을 우선한다(신규 타이틀 작업 시
    자기 번역을 우선하되, 없으면 다른 타이틀 번역을 placeholder 로 제안).
    """
    order = ([prefer_title] if prefer_title in SERIES_TITLES else []) \
        + [t for t in SERIES_TITLES if t != prefer_title]
    g = {}
    for t in reversed(order):  # 뒤→앞 순회: prefer 가 마지막에 덮어써 최우선
        path = os.path.join(PROJECT_ROOT, 'translation', t, 'translation.json')
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding='utf-8'))
        for l in iter_lines(d):
            jp = (l.get('jp') or '').strip()
            kr = (l.get('kr') or '').strip()
            if jp and kr:
                g[_norm_jp(jp)] = {'kr': kr, 't': t}
    return g


def analyze(title, check_offset=True):
    """검사 결과를 dict 로 반환 (CLI·editor 공용).

    키: unsupported / untrans / trunc / broken / conflicts / mismatch / leading / bugs
    """
    path = os.path.join(PROJECT_ROOT, 'translation', title, 'translation.json')
    if not os.path.exists(path):
        return {'error': f'{path} 없음'}
    d = json.load(open(path, encoding='utf-8'))
    cm = load_charmap()

    untrans, trunc, broken = [], [], []
    jp_kr = defaultdict(lambda: defaultdict(list))
    for loc, l in walk_lines(d):
        jp = l.get('jp') or ''
        kr = l.get('kr') or ''
        if kr.strip():
            if '�' in kr:
                broken.append((loc, kr))
            jl = l.get('jp_len')
            if jl:
                el = enc_len(kr.strip(), cm)
                if el is not None and el > jl:
                    trunc.append((loc, kr, el, jl))
            jp_kr[jp.strip()][kr.strip()].append(loc)
        elif kana(jp) and len(jp) >= 2 and l.get('tag') != 'ignore':
            untrans.append((loc, jp))

    conflicts = [(jp, dict(krs)) for jp, krs in jp_kr.items() if jp and len(krs) >= 2]
    mismatch = leading = None
    if check_offset and title == 'kaitou':
        mismatch, leading = _check_offset_kaitou(d)

    bugs = len(trunc) + len(broken) + (len(mismatch or [])) + (len(leading or []))
    return {
        'untrans': untrans, 'trunc': trunc, 'broken': broken,
        'conflicts': conflicts, 'mismatch': mismatch, 'leading': leading,
        'bugs': bugs,
    }


def main(title, verbose=False):
    r = analyze(title, check_offset=True)
    if r.get('error'):
        print('오류:', r['error']); return 2

    untrans, trunc, broken = r['untrans'], r['trunc'], r['broken']
    conflicts, mismatch, leading = r['conflicts'], r['mismatch'], r['leading']
    print(f"=== lint: {title} ===")
    print(f"  미번역(실텍스트) : {len(untrans)}")
    print(f"  잘림(슬롯 초과)  : {len(trunc)}")
    print(f"  깨진 문자        : {len(broken)}")
    print(f"  일관성(jp동일·kr상이): {len(conflicts)}")
    if mismatch is None:
        print(f"  offset 정합      : (skip)")
    else:
        print(f"  offset 어긋남    : {len(mismatch)}")
        print(f"  선행 글자 누락   : {len(leading)}")

    def dump(name, rows, fmt):
        if not rows:
            return
        print(f"\n--- {name} ({len(rows)}) ---")
        for row in rows:
            print("  " + fmt(row))

    if verbose or trunc:
        dump("잘림", trunc, lambda r: f"{r[0]}  {r[3]}B 슬롯에 {r[2]}B  {r[1]!r}")
    if verbose or broken:
        dump("깨진 문자", broken, lambda r: f"{r[0]}  {r[1]!r}")
    if mismatch:
        dump("offset 어긋남", mismatch, lambda r: f"{r[0]}  {r[1]!r}")
    if leading:
        dump("선행 글자 누락", leading, lambda r: f"{r[0]}  누락선행='{r[1]}'  jp={r[2]!r}")
    if verbose:
        dump("미번역", untrans, lambda r: f"{r[0]}  {r[1]!r}")
        if conflicts:
            print(f"\n--- 일관성 ({len(conflicts)}) ---")
            for jp, krs in sorted(conflicts, key=lambda x: -sum(len(v) for v in x[1].values())):
                print(f"  {jp!r}")
                for kr, locs in sorted(krs.items(), key=lambda x: -len(x[1])):
                    print(f"      {kr!r}  [{', '.join(locs)}]")

    bugs = r['bugs']
    print(f"\n{'❌ 버그류 ' + str(bugs) + '건 — 빌드 전 수정 필요' if bugs else '✅ 버그류 없음'}"
          f"  (미번역 {len(untrans)} · 일관성 {len(conflicts)}는 검수 정보)")
    return 1 if bugs else 0


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    verbose = '-v' in sys.argv
    title = args[0] if args else 'kaitou'
    sys.exit(main(title, verbose))
