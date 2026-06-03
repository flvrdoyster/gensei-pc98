"""Compile 환세 시리즈 공유 스크립트 파서.

디컴프레스된 청크(또는 CMD)를 **오피코드 스트림**으로 워킹해 텍스트를 추출한다.
희담(`kitan_parser.extract_dialogs`)에서 검증된 오피코드 모델을 일반화한 것으로,
쾌도전·포물장이 공유한다. 같은 회사 게임이라 제어코드 체계가 유사하다는 전제.

설계 원칙
---------
- **오피코드를 정확히 모델링**해 어디가 텍스트고 어디가 제어/인자인지 구분한다.
  인자 바이트가 우연히 SJIS 쌍을 이뤄도 텍스트로 오인하지 않는다.
- 따라서 **사후 노이즈 필터가 필요 없다**. 찌꺼기가 나오면 그건 오피코드 모델이
  불완전하다는 신호 → 필터가 아니라 모델(이 파일)을 고친다.
- 블록 오프너·인라인 마커·줄 임계값 등 **타이틀별로 다를 수 있는 부분은 설정(Spec)**으로,
  블록 내부 오피코드 처리는 공통 베이스로 둔다.

확장(새 타이틀)
--------------
- 기본은 `BASE_SPEC` 그대로 시도. 안 잡히는 블록이 있으면 그 타이틀의 오프너/마커를
  Spec에 추가한다(override). 새 오피코드(인자 길이)가 보이면 `SKIP_OPCODES`에 추가.
"""

from dataclasses import dataclass, field

# compile_lz의 SJIS 판별/디코드를 그대로 사용 (단일 소스)
from compile_lz import is_sjis, read_sjis_char


# ── 오피코드 스펙 ──────────────────────────────────────────────────────────────

@dataclass
class ScriptSpec:
    """타이틀별로 달라질 수 있는 스크립트 파라미터.

    openers: 블록을 새로 여는 오피코드 시퀀스 → 블록 종류 태그.
             가변 길이(2바이트, 4바이트 등) 시퀀스를 그대로 매칭한다.
    markers: 블록 *밖*에서 SJIS 직전에 와 본문 시작을 알리는 마커 시퀀스.
             (시퀀스 직후가 SJIS일 때만 발동)
    skip_opcodes: [opcode bytes] → 총 길이. 인자를 텍스트로 오인하지 않도록 통째로 건너뜀.
    break_lead: 이 바이트(+다음 1바이트)는 줄 구분자(개행/페이지/클리어/항목경계)로 처리.
    min_chars: 줄로 인정할 최소 글자 수. 1이면 `「`·단일 글자까지 전부 캡처(완전 파싱).
    """
    openers: dict = field(default_factory=dict)
    markers: dict = field(default_factory=dict)
    skip_opcodes: dict = field(default_factory=dict)
    break_lead: frozenset = field(default_factory=frozenset)
    min_chars: int = 1
    lookahead: int = 40   # 오프너 직후 이 범위 내 SJIS 없으면 바이너리 이벤트 블록으로 간주
    implicit_text: bool = True  # 오프너 없는 2자+ SJIS 런을 텍스트 블록으로 암묵 재진입


# 환세 시리즈 공통 베이스 (희담에서 검증)
BASE_SPEC = ScriptSpec(
    openers={
        (0x6b, 0x00):             'dialog',   # 화자 대화 블록
        (0x6e, 0x00, 0x67, 0x01): 'speaker',  # 화자 prefix 블록
        (0x62, 0x00):             'def',      # 정의/스킬/아이템 설명 블록
        (0x6d, 0x08):             'name',     # 적/아이템 이름 블록
    },
    markers={
        (0x01, 0x02): 'text',   # 화자/감정 코드 후 본문
        (0x76, 0x1a): 'text',   # 화면 클리어 후 본문
        (0x02, 0x65): 'text',   # 화자 코드 체인 종료 후 본문
    },
    skip_opcodes={
        (0x6a, 0x01): 4,   # 2바이트 인자 오피코드
        (0x64, 0x00): 4,   # 포트레이트/캐릭터 코드 + 2바이트 인자
        (0x81, 0x65): 2,   # 다이얼로그 박스 제어 (')
    },
    break_lead=frozenset({0x72, 0x73, 0x76}),  # 개행 / 페이지 / 클리어
    min_chars=1,
)


def _match(data, i, seq):
    """data[i:] 가 seq(바이트 튜플)로 시작하면 True."""
    if i + len(seq) > len(data):
        return False
    return all(data[i + k] == seq[k] for k in range(len(seq)))


def _has_sjis_nearby(data, start, limit):
    end = min(start + limit, len(data) - 1)
    for j in range(start, end):
        if is_sjis(data, j):
            return True
    return False


# ── 워커 ──────────────────────────────────────────────────────────────────────

def walk(data, spec=BASE_SPEC):
    """디컴프레스된 바이트열을 워킹해 블록 리스트를 반환.

    반환: [{'type': str, 'offset': int, 'lines': [{'offset': int, 'jp': str}]}]
    노이즈 필터 없음 — 오피코드 모델이 잡는 텍스트를 전부 캡처한다.
    """
    blocks = []
    cur_block = None      # {'type', 'offset', 'lines'}
    cur_text = ''
    cur_offset = 0
    in_block = False
    i = 0
    n = len(data)

    def flush_line():
        nonlocal cur_text, cur_offset
        if cur_block is not None and len(cur_text.strip()) >= spec.min_chars:
            cur_block['lines'].append({'offset': cur_offset, 'jp': cur_text})
        cur_text = ''
        cur_offset = i

    def flush_block():
        nonlocal cur_block
        flush_line()
        if cur_block is not None and cur_block['lines']:
            blocks.append(cur_block)
        cur_block = None

    def open_block(btype, advance):
        nonlocal cur_block, in_block, cur_text, cur_offset, i
        flush_block()
        in_block = _has_sjis_nearby(data, i + advance, spec.lookahead)
        i += advance
        cur_text = ''
        cur_offset = i
        if in_block:
            cur_block = {'type': btype, 'offset': i, 'lines': []}

    while i < n - 1:
        # 1) 스킵 오피코드 (인자 통째로 건너뜀 — 텍스트 오인 방지)
        matched = False
        for seq, length in spec.skip_opcodes.items():
            if _match(data, i, seq):
                # 81 6b 류처럼 직후가 SJIS면 실제 문자일 수 있는 케이스는
                # skip_opcodes에 넣지 않는다(아래 81 6b 특례 참고). 여기선 무조건 스킵.
                i += min(length, n - i)
                cur_text = ''
                cur_offset = i
                matched = True
                break
        if matched:
            continue

        # 2) 블록 오프너
        for seq, btype in spec.openers.items():
            if _match(data, i, seq):
                open_block(btype, len(seq))
                matched = True
                break
        if matched:
            continue

        # 3) 인라인 텍스트 시작 마커 (직후가 SJIS일 때만)
        for seq, _tag in spec.markers.items():
            if _match(data, i, seq) and is_sjis(data, i + len(seq)):
                # 02 65 처럼 블록 내부에서도 줄을 끊고 재시작하는 마커
                if in_block:
                    flush_line()
                else:
                    flush_block()
                    cur_block = {'type': 'text', 'offset': i + len(seq), 'lines': []}
                in_block = True
                i += len(seq)
                cur_text = ''
                cur_offset = i
                matched = True
                break
        if matched:
            continue

        if not in_block:
            # 블록 밖 — 오프너 없이 포인터 테이블로 참조되는 맵 대사 등.
            # 제어/포인터 바이트는 SJIS 쌍을 못 이루므로, 2자+ SJIS 런이 시작되면
            # 텍스트 블록으로 암묵 재진입 (스크립트 청크에 한해 안전).
            if spec.implicit_text and is_sjis(data, i) and i + 2 < n and is_sjis(data, i + 2):
                in_block = True
                cur_block = {'type': 'text', 'offset': i, 'lines': []}
                cur_text = ''
                cur_offset = i
                continue
            # 단독 SJIS 쌍(다음이 바이너리)은 정렬 유지 위해 2바이트 건너뜀
            i += 2 if is_sjis(data, i) else 1
            continue

        # 4) 줄/페이지/클리어/항목 구분자 — 줄 종결
        b = data[i]
        nb = data[i + 1] if i + 1 < n else 0
        if b in spec.break_lead:
            flush_line()
            i += 2
            cur_offset = i
            continue
        # 64 XX (XX≠00): 메뉴 항목 경계 (64 00은 skip_opcodes에서 처리됨)
        if b == 0x64:
            flush_line()
            i += 2
            cur_offset = i
            continue
        # 65: 1바이트 종료/줄 구분자.
        # 직후 바이트가 다음 텍스트의 첫 글자일 수 있어 2바이트로 소비하면 첫 글자를 먹는다.
        if b == 0x65:
            flush_line()
            i += 1
            cur_offset = i
            continue
        # 6d 00: 항목 표시 종료
        if b == 0x6d and nb == 0x00:
            flush_line()
            i += 2
            cur_offset = i
            continue
        # 81 6b (〔): 직후가 SJIS면 실제 문자, 아니면 제어코드
        if b == 0x81 and nb == 0x6b and not is_sjis(data, i + 2):
            i += 2
            continue

        # 5) SJIS 텍스트
        if is_sjis(data, i):
            if not cur_text:
                cur_offset = i
            cur_text += read_sjis_char(data, i)
            i += 2
            continue

        # 6) 그 외 바이너리 — 스킵 + 텍스트 리셋 (우연한 SJIS 쌍 오인 방지)
        cur_text = ''
        i += 1

    flush_block()
    return blocks
