# 환세풍광전 역공학 노트

**대상 게임**: 환세풍광전 / 幻世風狂伝 (Compile Inc., 1994, PC-98)  
**상태**: 텍스트 추출 완료, 번역 완료, 최종 검수 중  
**역공학 방법**: GF2.COM 디스어셈블 → 런타임 분석

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
| `65 00/01 [SJIS/ctrl]` | 대화 블록 시작 (01 = 이벤트, ctrl = 62/63/64/66/76) |
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

핵심 판별 기준: `65 00/01` 다음 바이트가 Shift-JIS 선행 바이트 범위
(`0x81~0x9F`, `0xE0~0xFC`) 또는 제어바이트(`62/63/64/66/76`)인지 여부로 대화/비대화 구분.  
제어바이트 확장은 `in_dialog=False`일 때만 적용 — 블록 내부 `65 00`은 서브항목 종료자로 유지.

#### 오탐 방지

- **`is_sjis` 디코딩 검증**: 바이트 범위만으로는 실제 Shift-JIS에 없는 코드(예: 0x8865, 0xFC65)를 걸러내지 못함.  
  `data[i:i+2].decode('shift_jis')`로 실제 디코딩 성공 여부 검증 (0x85XX 가이지는 별도 처리이므로 제외).
- **`68` 시작 오탐 차단**: `68 XX [SJIS lead] 6B` 패턴은 바이너리에서 빈번.  
  직후 `6B`가 오면 텍스트 길이=1로 유효 대화가 아니므로 `is_68_start`에서 제외.

---

## 가이지 (外字, 0x85XX) 인코딩

게임의 일부 텍스트(상점 가격, 몬스터명, UI 등)는 표준 Shift-JIS 대신 **가이지 영역(0x85XX)** 으로 인코딩.  
가이지 텍스트는 ASCII도 2바이트로 표현되므로, 인서터에서 `use_gaiji=True`로 인코딩해야 함.

### 매핑 구조 (`compile_lz.py`)

| 가이지 코드 | 내용 | 변환 공식 |
|-------------|------|-----------|
| `0x8540~0x859D` | ASCII 0x21~0x7E | trail − 0x1F (또는 − 0x20) |
| `0x859F~0x85DD` | 반각 카타카나 63자 (`_HW_KANA`) | trail − 0x9F → 인덱스 |
| `0x85E3~0x85F8` | 탁점 카타카나 (확장) | `_GAIJI_EXT` 딕셔너리 |

### 확장 가이지 (`_GAIJI_EXT`)

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
- ASCII 문장부호·숫자·영문: 전각 자동 변환 (`ASCII_TO_FULLWIDTH`)  
  예) `+` → `＋`(817B), `2` → `２`(8251), `H` → `Ｈ`(8267)  
  ※ 게임 렌더러가 1바이트 ASCII를 표시하지 못하므로 전각 필수

---

## 파서 구조 (상태 머신)

### 대화 파서 (`extract_dialogs`)

```
상태: OUT_OF_DIALOG / IN_DIALOG

IN_DIALOG 진입: 65 00/01 [SJIS lead 또는 제어바이트(62-76, out-of-dialog만)]
IN_DIALOG 종료: 6B 또는 다음 65 00

IN_DIALOG 내부:
  72 XX    → 줄바꿈 (cur_text → cur_lines)
  64 XX    → 서브항목 구분 (제어 바이트 스킵 후 새 오프셋)
  45 00    → 바이너리 섹션 마커 → 6B까지 스킵
  65 00    → 서브항목 종료자 (오프셋 갱신)
  SJIS     → cur_text에 추가, cur_end 갱신
  그 외    → 스킵
```

각 라인 항목: `{offset, jp, jp_len, kr, gaiji?, tag?}`  
`jp_len` = `cur_end - cur_offset` (실제 바이트 수, 가이지 불완전 디코딩 대응)  
`gaiji` = 원본 바이트에 0x85XX 포함 시 `true`  
`tag` = 수동 분류 태그

#### `generate_json()` 재실행 시 기존 데이터 보존

파서를 재실행하면 기존 `translation.json`에서 `kr`·`tag` 값을 오프셋 기반으로 복원.  
**복원 키 우선순위:**
1. `(dialog['file'], offset)` — 오프셋 정확 매칭 (1차)
2. `(dialog['file'], jp)` — 텍스트 기반 fallback (2차, 파서 개선으로 오프셋 변경 시)

**자동 백업:** 파서 재실행 시 translation.json에 미커밋 변경이 있으면 자동 git commit.

### 메뉴 파서 (`extract_menus`)

```
13 00 감지 → 포인터 테이블 읽기 → 각 포인터 위치의 항목 파싱
항목: 64 00 [2B ID] [SJIS 텍스트] 65 00
```

### 독립 메뉴 파서 (`extract_orphan_items`)

```
13 00 블록 밖의 64 00 [2B ID] [SJIS text] 65 00 패턴 추출.
FFFD(디코딩 실패) 포함 항목 제외.
```

### 아이템 파서 (`extract_items`, MESSAGE.CMD)

```
상태: name / stat / desc
name 진입: 0F 03
stat 진입: 64 XX (XX != 02)
desc 진입: 64 02
구분: 72 01 → 줄바꿈 / 65 00 → 아이템 종료
```

---

## 재삽입 (`hukyou_inserter.py`)

### 교체 방식

- 정상 텍스트: `jp.encode('shift_jis')` 원본 바이트 검증 후 교체
- 가이지 텍스트: `jp_len` 기반 길이 교체 + `use_gaiji=True` 인코딩
- GF2.COM: 부트스트랩 보존 후 LZ 재압축, `GF2_PAD_SIZE` 오프셋 보정

오프셋 **내림차순** 처리 — 앞쪽 오프셋 보존.  
짧으면 전각 공백(`\x81\x40`) 패딩, 길면 SJIS 경계에서 잘라냄.

---

## 추출기 × 파일 교차 검증

| 추출기 | MESSAGE.CMD | STAGE/OPEN/ENDING.CMD | GF2.COM |
|--------|:-----------:|:---------------------:|:-------:|
| `extract_dialogs` | O (속마음 독백) | O (메인 스크립트) | ✗ 바이너리 오탐 |
| `extract_menus` | 해당 없음 | O | ✗ 바이너리 오탐 |
| `extract_items` | O (아이템 데이터) | ✗ 바이너리 오탐 | ✗ 바이너리 오탐 |
| `extract_ui` | 해당 없음 | 해당 없음 | O (하드코딩 오프셋) |

- MESSAGE.CMD는 아이템(offset 98~2730)과 대화(offset 2928~)가 영역 분리됨

---

## 에디터 태그 시스템

`tag` 필드로 분류 (dialog/monolog/cutscene/char/battle/item/menu/location/system).

**자동 분류 규칙**: STAGE1/2 수동 분류를 기반으로 나머지 파일에 적용.  
- 파일 기반: ENDING/OPEN.CMD→cutscene, MESSAGE.CMD→monolog
- 정확 텍스트 매칭: 동일 텍스트를 다른 STAGE에서 동일 태그로
- 패턴 매칭: 보물상자 메시지→item, 파일 끝 전투 블록→battle

---

## translation.json 출력 형식

```json
{
  "dialogs": [
    {
      "file": "STAGE1.CMD",
      "index": 1,
      "lines": [
        {"offset": 18462, "jp": "「あら　いらっしゃい！", "jp_len": 22, "kr": "", "tag": "ui"},
        {"offset": 24724, "jp": "５０Gold", "jp_len": 12, "kr": "", "gaiji": true}
      ]
    }
  ],
  "items": [
    {
      "offset": 96,
      "name": {"offset": 98,  "jp": "鉄の剣",     "jp_len": 6,  "kr": ""},
      "stat": {"offset": 106, "jp": "攻撃力＋２０", "jp_len": 12, "kr": ""},
      "desc": [{"offset": 120, "jp": "鉄製の長剣", "jp_len": 10, "kr": ""}]
    }
  ],
  "ui": [
    {"offset": 28854, "category": "system", "jp": "セーブ", "jp_len": 6, "kr": ""}
  ]
}
```
