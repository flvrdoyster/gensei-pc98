# 환세풍광전 역공학 노트

**대상**: 환세풍광전 / 幻世風狂伝 (Compile, 1994, PC-98)  
**상태**: 완료  
**도구**: `hukyou_parser.py` (추출) · `hukyou_inserter.py` (재삽입)

---

## 개요

### 파일 구성

```
original/hukyou/
  GF2.COM          로더 (자가 압축 해제 + CMD 로드)
  STAGE1~8.CMD     메인 스크립트 (대화·메뉴)
  OPEN.CMD         오프닝 컷씬
  ENDING.CMD       엔딩 컷씬
  MESSAGE.CMD      아이템 데이터
```

**텍스트 소스**: CMD 파일 전체. GF2.COM은 UI 문자열만 (`extract_ui`, 하드코딩 오프셋).

### 추출기 × 파일 적용 범위

| 추출기 | MESSAGE.CMD | STAGE/OPEN/ENDING.CMD | GF2.COM |
|--------|:-----------:|:---------------------:|:-------:|
| `extract_dialogs` | O (독백) | O (메인 대화) | ✗ 바이너리 오탐 |
| `extract_menus` | — | O | ✗ 바이너리 오탐 |
| `extract_orphan_items` | — | O | ✗ 바이너리 오탐 |
| `extract_items` | O (아이템) | ✗ 바이너리 오탐 | ✗ 바이너리 오탐 |
| `extract_ui` | — | — | O (하드코딩 오프셋) |

MESSAGE.CMD는 아이템 영역과 대화 영역이 분리되어 있어 추출기 교차 적용 주의.

---

## 작업 흐름

### 1. 압축 해제

GF2.COM과 CMD 파일 모두 동일한 LZ 알고리즘으로 압축. `compile_lz.decompress()` 사용.

LZ 알고리즘 (`compile_lz.py`에 구현):
```
al = *si++
if al == 0:      종료
if al & 0x80:    back-reference — length=(al&0x7f)+3, offset=*si++＋1
else:            literal copy — length=al
```

GF2.COM 구조:
- `0x000~0x070`: x86 자가 압축 해제 루틴 (부트스트랩) — 인서터에서 그대로 보존
- `0x071~`: LZ 압축 데이터

주요 상수:
- `GF2_BOOTSTRAP_SIZE = 0x71` — LZ 데이터 시작 오프셋
- `GF2_PAD_SIZE = 236` — 해제 출력의 실제 데이터 이전 패딩 (인서터 오프셋 보정용)

### 2. 제어코드

| 바이트 | 역할 | 비고 |
|--------|------|------|
| `65 00/01 [SJIS/ctrl]` | 대화 블록 시작 | 01=이벤트, ctrl=62/63/64/66/76 |
| `72 XX` | 줄바꿈 | |
| `6B` | 대화 블록 종료 | |
| `65 00` (블록 내부) | 서브항목 종료자 | |
| `45 00` | 바이너리 섹션 마커 | 이후 `6B`까지 스킵 |
| `13 00 [ptr…]` | 메뉴 선택지 블록 | 포인터 테이블 + 항목 |
| `64 XX` | 라인 구분 / 아이템 상태 구분 | |
| `0F 03` | 아이템 항목 시작 | MESSAGE.CMD 전용 |
| `64 02` | 아이템 설명 줄 구분 | MESSAGE.CMD 전용 |

메뉴 블록(`13 00`) 구조:
```
13 00 [ptr0_lo ptr0_hi] [ptr1_lo ptr1_hi] …
각 포인터 위치: 64 00 [2B ID] [SJIS 텍스트] 65 00
포인터 수: n = (first_ptr - current_pos) / 2
```

대화 블록 진입 판별: `65 00/01` 다음 바이트가 SJIS 선행 바이트(`0x81~0x9F`, `0xE0~0xFC`) 또는 제어 바이트(`62~76`)인지 확인.

### 3. 반각 (0x85XX)

일부 텍스트(상점 가격, 몬스터명, UI 등)는 표준 SJIS 대신 반각 영역(`0x85XX`) 사용.  
인코딩 상세(ASCII·반각 카타카나·탁점 카타카나 매핑)는 `compile_lz.py` 참조.  
`compile_lz.read_sjis_char()` / `encode_halfwidth_char()` 처리.

**한글 반각 적용**: 좁은 슬롯(전투 적 이름·UI 아이템 라벨)에 한글이 들어갈 때  
`0x85A4~0x85EC` 슬롯에 한글 글리프를 그려넣고 `/X` 마커로 인코딩.  
적 이름 식별은 에디터의 `enemy` 태그. 상세 절차는 `tools/NOTES.md` "반각 한글" 섹션 참조.

### 4. 파싱

`hukyou_parser.py` 실행 → `translation/hukyou/translation.json` 생성.

파서 재실행 시 기존 `kr`·`tag` 값 보존:
1. `(file, offset)` 정확 매칭 (1차)
2. `(file, jp)` 텍스트 기반 fallback (2차)

`translation.json` 최상위 키: `dialogs` (대화) · `items` (아이템) · `ui` (UI 문자열).  
각 항목 공통 필드: `file`, `offset`, `jp`, `jp_len`, `kr`, `tag`.  
반각 포함 항목에는 `halfwidth: true`. 태그: `dialog` / `monolog` / `cutscene` / `char` / `battle` / `item` / `menu` / `location` / `system`.

### 5. 재삽입

`hukyou_inserter.py` 실행 → `build/hukyou/` 출력.

- 오프셋 **내림차순** 처리 — 앞쪽 오프셋 보존
- 정상 텍스트: `jp.encode('shift_jis')` 검증 후 교체
- 반각 텍스트: `jp_len` 기반 길이 교체 + `use_halfwidth=True` 인코딩
- 짧으면 전각 공백(`\x81\x40`) 패딩, 길면 SJIS 경계에서 잘라냄

### 6. 빌드

GF2.COM 처리:
- 부트스트랩(`0x000~0x070`) 보존
- 수정된 내용 LZ 재압축
- `GF2_PAD_SIZE` 오프셋 보정 적용

---

## 참고

- **SJIS 범위 검증 필수**: 바이트 범위만으로는 실제 SJIS에 없는 코드(예: `0x8865`, `0xFC65`)를 걸러내지 못함 → `data[i:i+2].decode('shift_jis')` 검증 (0x85XX 반각 제외)
- **1바이트 ASCII 표시 불가**: 게임 렌더러가 raw 1바이트 ASCII(`0x41` 등) 직접 표시 불가 → 기본은 전각으로 자동 변환 (`ASCII_TO_FULLWIDTH`), 반각이 필요하면 `/X` 시퀀스로 2바이트 SJIS halfwidth 영역(`0x85XX`) 사용
- **MESSAGE.CMD 이중 구조**: 다른 CMD 파일과 달리 아이템 데이터와 대화가 한 파일에 공존한다. 앞부분은 `extract_items`로, 뒷부분은 `extract_dialogs`로 처리 — 교차 적용 시 오탐 발생.
- **크레딧 체인 첫 항목 누락 (ENDING.CMD)**: 크레딧은 `63 08 [텍스트] 65 00` 반복이고, `extract_dialogs`는 `65 00` 뒤에 `63`이 올 때 진입(`is_65_start`의 0x63 분기)해 *다음* 항목을 잡는다. 그래서 체인 **첫 항목은 앞에 여는 `65 00 63`이 없어 누락**된다. 사례: ENDING 첫 크레딧 `企画`(offset 1539) → translation.json에 수동 추가(번역 `기획`). 파서를 고치면 다른 파일의 `63 08` 노이즈까지 잡힐 위험이 있어, 단건은 수동 보완이 안전.
