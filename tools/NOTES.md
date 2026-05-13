# 환세풍광전 CMD 파서 — 구현 방식 노트

## 배경

**대상 게임**: 환세풍광전 / 幻世風狂伝 (Compile Inc., 1994, PC-98)  
**역공학 방법**: 정공법 (GF2.COM 디스어셈블 → 런타임 분석)

---

## 핵심 발견 순서

### 1단계 — 실행파일 압축 확인

GF2.COM을 디스어셈블(`objdump -b binary -m i8086`).  
`0x000~0x070`: x86 자가 압축 해제 루틴 (COM 부트스트랩).  
`0x071~`: LZ 압축 데이터 시작.

```
0x12b 루프 (부트스트랩 내부):
  al = *si++
  if al == 0: 종료
  if al & 0x80: back-reference (length = (al&0x7f)+3, offset = *si++ +1)
  else: literal copy (length = al)
```

Python으로 동일 알고리즘 구현 → 60364바이트로 해제 성공.

**GF2.COM 주요 상수**:
- `GF2_BOOTSTRAP_SIZE = 0x71` — 부트스트랩 크기 (LZ 데이터 시작 오프셋)
- `GF2_PAD_SIZE = 236` — 해제 출력에서 실제 데이터 이전 패딩 바이트 수  
  (파서의 `decompress(raw)` 오프셋과 삽입기의 `decompress(raw, start=0x71)` 오프셋 차이)

### 2단계 — CMD 파일 포맷 파악

압축 해제된 GF2.COM에서:
- `call 0x6f60`: 파일 로드 (INT 21h AH=3Fh)
- `call 0x1417` → `call 0x12f0`: **동일한 LZ 알고리즘으로 CMD 파일 압축 해제**

즉 CMD 파일은 압축된 상태. 런타임에 해제 후 인터프리트.

STAGE1.CMD를 동일 알고리즘으로 해제 → Shift-JIS 텍스트 블록 확인.

### 3단계 — 스크립트 제어코드 파악

압축 해제된 CMD 파일에서 텍스트 주변 바이트 분석.

| 바이트 | 역할 |
|--------|------|
| `65 00/01 [SJIS lead]` | 대화 블록 시작 (01 = 이벤트/보물상자/재방문 NPC) |
| `72 XX` | 줄바꿈 (XX는 부가 파라미터) |
| `6B` | 대화 블록 명시 종료 |
| `65 00` (블록 내부) | 서브항목 종료자 |
| `45 00` | 바이너리 섹션 마커 — 이후 `6B`까지 스킵 |
| `13 00 [ptr…]` | 메뉴 선택지 블록 (포인터 테이블 + 항목) |
| `64 XX` | 라인 구분 / 아이템 상태 구분 |
| `0F 03` | 아이템 항목 시작 (MESSAGE.CMD) |
| `64 02` | 아이템 설명 줄 구분 |
| `64 XX` (XX≠02) | 아이템 수치 구분 |

#### 메뉴 블록 (`13 00`) 구조

```
13 00 [ptr0_lo ptr0_hi] [ptr1_lo ptr1_hi] … → 포인터 테이블
각 포인터가 가리키는 곳:
  64 00 [2B ID] [SJIS 텍스트] 65 00
```

포인터 수 계산: `n = (first_ptr - current_pos) / 2`  
유효성 검사: `n > 0 and n <= 10 and first_ptr > current_pos`

핵심 판별 기준: `65 00` 다음 바이트가 Shift-JIS 선행 바이트 범위
(`0x81~0x9F`, `0xE0~0xFC`)인지 여부로 대화/비대화 구분.

---

## 가이지 (外字, 0x85XX) 인코딩

게임의 모든 텍스트는 표준 Shift-JIS 대신 **가이지 영역(0x85XX)** 으로 인코딩되어 있음.

### 매핑 구조 (`compile_lz.py`)

| 가이지 코드 | 내용 | 변환 공식 |
|-------------|------|-----------|
| `0x8540~0x859D` | ASCII 0x21~0x7E | trail − 0x1F (또는 − 0x20) |
| `0x859F~0x85DD` | 반각 카타카나 63자 (`_HW_KANA`) | trail − 0x9F → 인덱스 |
| `0x85E3~0x85F8` | 탁점 카타카나 (확장) | `_GAIJI_EXT` 딕셔너리 |

### 확장 가이지 (`_GAIJI_EXT`)

표준 반각 카타카나에 없는 탁점/반탁점 카타카나가 0x85DD 이후에 위치:

| 코드 | 문자 | 코드 | 문자 |
|------|------|------|------|
| `0x85E3` | ヴ | `0x85F1` | デ |
| `0x85E6` | グ | `0x85F2` | ド |
| `0x85EA` | ジ | `0x85F5` | ビ |
| — | — | `0x85F6` | ピ |
| — | — | `0x85F8` | プ |

그 외 0x85XX 코드는 Python `shift_jis` 코덱으로 fallback 디코딩.

### 한글 인코딩 (삽입기)

- 한글 자모: `charmap.json` (KS X 1001 기반, JIS 2수준 한자 영역에 매핑)
- ASCII 문장부호·숫자: 전각 자동 변환 (`ASCII_TO_FULLWIDTH`)  
  예) `+` → `＋`(817B), `2` → `２`(8251)  
  ※ 게임 렌더러가 1바이트 ASCII를 표시하지 못하므로 전각 필수

---

## 파서 구조 (상태 머신)

### 대화 파서 (`extract_dialogs`)

```
상태: OUT_OF_DIALOG / IN_DIALOG

IN_DIALOG 진입: 65 00/01 [SJIS lead]
IN_DIALOG 종료: 6B 또는 다음 65 00

IN_DIALOG 내부:
  72 XX    → 줄바꿈 (cur_text → cur_lines)
  64 XX    → 서브항목 구분 (제어 바이트 스킵 후 새 오프셋)
  45 00    → 바이너리 섹션 마커 → 6B까지 스킵
  65 00    → 서브항목 종료자 (오프셋 갱신)
  SJIS     → cur_text에 추가, cur_end 갱신
  그 외    → 스킵
```

각 라인 항목: `{offset, jp, jp_len, kr}`  
`jp_len` = `cur_end - cur_offset` (실제 바이트 수, 가이지 불완전 디코딩 대응)

### 메뉴 파서 (`extract_menus`)

```
13 00 감지 → 포인터 테이블 읽기 → 각 포인터 위치의 항목 파싱
항목: 64 00 [2B ID] [SJIS 텍스트] 65 00
출력: dialog 배열에 index='menu1', 'menu2', … 로 병합
```

### 아이템 파서 (`extract_items`, MESSAGE.CMD)

```
상태: name / stat / desc

name 진입: 0F 03
stat 진입: 64 XX (XX != 02)
desc 진입: 64 02

구분:
  72 01    → 줄바꿈 (현재 상태 유지)
  65 00    → 아이템 종료
  0F 03    → 다음 아이템 시작
```

---

## 재삽입 (`hukyou_inserter.py`)

### 교체 방식

- 정상 텍스트: `jp.encode('shift_jis')` 원본 바이트 검증 후 교체
- 가이지 포함 텍스트: `jp_len` 기반 길이 교체 (바이트 검증 생략)
- GF2.COM: 부트스트랩 보존 후 LZ 재압축, `GF2_PAD_SIZE` 오프셋 보정

### 패치 순서

오프셋 **내림차순** 처리 — 앞쪽 오프셋을 보존하기 위해.

### 길이 맞춤 (`fit_length`)

- 짧으면 전각 공백(`\x81\x40`)으로 패딩
- 길면 뒤에서 자름 (SJIS 선행 바이트 경계 보정)

---

## 출력 형식 (translation.json)

```json
{
  "dialogs": [
    {
      "file": "STAGE1.CMD",
      "index": 1,
      "lines": [
        {"offset": 18462, "jp": "「あら　いらっしゃい！", "jp_len": 22, "kr": ""},
        {"offset": 18484, "jp": "　今日はどーしたの？",   "jp_len": 20, "kr": ""}
      ]
    },
    {
      "file": "OPEN.CMD",
      "index": "menu1",
      "lines": [
        {"offset": 1228, "jp": "初めから遊ぶ", "jp_len": 12, "kr": ""},
        {"offset": 1246, "jp": "続きを楽しむ", "jp_len": 12, "kr": ""},
        {"offset": 1264, "jp": "ディスプレイ", "jp_len": 12, "kr": ""}
      ]
    }
  ],
  "items": [
    {
      "offset": 96,
      "name": {"offset": 98,  "jp": "鉄の剣",     "jp_len": 6,  "kr": ""},
      "stat": {"offset": 106, "jp": "攻撃力＋２０", "jp_len": 12, "kr": ""},
      "desc": [
        {"offset": 120, "jp": "鉄製の長剣", "jp_len": 10, "kr": ""}
      ]
    }
  ],
  "ui": [
    {"offset": 28854, "category": "system", "jp": "セーブ", "jp_len": 6, "kr": ""}
  ]
}
```

- `offset`: 압축 해제 후 바이트 오프셋
- `jp_len`: 원본 바이트 수 (가이지 포함 항목의 정확한 길이 보장)
- `index`: 정수(대화 블록) 또는 `"menuN"` (메뉴 선택지 블록)
- `stat` 키: 수치 없는 아이템은 키 자체 없음

---

## 다른 Compile 타이틀 적용 시 체크리스트

### 압축 알고리즘 동일 여부
- COM 파일 0x100이 `FC 60 8C C8…`으로 시작하면 동일 구조
- `0x113~0x114 = F3 A5` (REP MOVSW) 확인
- Python `decompress()` 함수 그대로 사용 가능

### 제어코드 차이 가능성
같은 개발사라도 타이틀마다 스크립트 포맷이 다를 수 있음.
아래 순서로 재분석:

1. CMD 파일 압축 해제
2. Shift-JIS 텍스트 4자 이상 연속 구간 검색
3. 텍스트 직전/직후 1~4바이트 패턴 집계
4. 자주 등장하는 바이트 = 제어코드 후보

```python
# 제어코드 후보 탐색 예시
from collections import Counter
pre_bytes = Counter()
for i in range(len(data)-1):
    if is_sjis(data, i):
        pre_bytes[data[i-1]] += 1
```

5. 0x65, 0x6b, 0x72 등 동일 코드 쓸 가능성 높음 (같은 엔진이면)
6. 차이가 있으면 새 파서로 분기

---

## 파일 목록

| 파일 | 역할 |
|------|------|
| `compile_lz.py` | LZ 압축/해제 + SJIS/가이지 유틸 (Compile社 공통) |
| `hukyou_parser.py` | 환세풍광전 CMD 파서 (대화/메뉴/아이템/UI 추출 + JSON 생성) |
| `hukyou_inserter.py` | 환세풍광전 번역 재삽입 (한글 인코딩 + LZ 재압축) |
| `editor.py` | 웹 번역 에디터 (Flask-less HTTP 서버, localhost:8421) |
| `charmap.json` | 한글↔가이지 코드 매핑 |
| `../translation/hukyou/translation.json` | 번역 파일 (오프셋 + JP/KR 쌍 + jp_len) |
