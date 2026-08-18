# 환세풍광전 역공학 노트

**대상**: 환세풍광전 / 幻世風狂伝 (Compile, 1994, PC-98)  
**상태**: 완료  
**도구**: `hukyou_parser.py` (추출) · `hukyou_inserter.py` (재삽입)

---

## 개요

### 파일 구성

**FDI 이미지 1장.** `original/hukyou/`에 그 안의 파일을 개별로 추출해 둔다. 그래픽
(`BG*.DAT`·`MONST*.DAT` 등)·음악·세이브(`PLAY*.INF`) 등 다수 파일이 있지만, 텍스트가
있어 실제로 패치되는 건 아래가 전부다.

### 패치 대상 파일

```
GF2.COM          로더 (자가 압축 해제 + CMD 로드) — UI 문자열만 패치
STAGE1~7.CMD     메인 스크립트 (대화·메뉴)
OPEN.CMD         오프닝 컷씬
ENDING.CMD       엔딩 컷씬
MESSAGE.CMD      아이템 데이터 + 독백 대사
```

텍스트 소스는 CMD 파일 전체이고, GF2.COM은 UI 문자열만(`extract_ui`, 하드코딩 오프셋) 다룬다.

### 추출기 × 파일 적용 범위

| 추출기 | MESSAGE.CMD | STAGE/OPEN/ENDING.CMD | GF2.COM |
|--------|:-----------:|:---------------------:|:-------:|
| `extract_dialogs` | O (독백) | O (메인 대화) | ✗ 바이너리 오탐 |
| `extract_menus` | — | O | ✗ 바이너리 오탐 |
| `extract_orphan_items` | — | O | ✗ 바이너리 오탐 |
| `extract_items` | O (아이템) | ✗ 바이너리 오탐 | ✗ 바이너리 오탐 |
| `extract_ui` | — | — | O (하드코딩 오프셋) |

MESSAGE.CMD는 아이템 영역과 대화 영역이 한 파일 안에 나뉘어 있어서, 추출기를 교차 적용하면
오탐이 난다.

---

## 작업 흐름

### 1. 압축 해제

GF2.COM과 CMD 파일 모두 같은 LZ 알고리즘으로 압축되어 있어 `compile_lz.decompress()`를
그대로 쓴다.

```
al = *si++
if al == 0:      종료
if al & 0x80:    back-reference — length=(al&0x7f)+3, offset=*si++＋1
else:            literal copy — length=al
```

GF2.COM은 `0x000~0x070`이 x86 자가 압축 해제 루틴(부트스트랩)이라 인서터에서 그대로
보존하고, `0x071~`부터가 LZ 압축 데이터다. `GF2_BOOTSTRAP_SIZE = 0x71`이 그 시작 오프셋이고,
`GF2_PAD_SIZE = 236`은 해제 출력에서 실제 데이터 앞에 붙는 패딩이라 인서터 오프셋 보정에
쓴다.

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

메뉴 블록(`13 00`)은 다음 구조다.

```
13 00 [ptr0_lo ptr0_hi] [ptr1_lo ptr1_hi] …
각 포인터 위치: 64 00 [2B ID] [SJIS 텍스트] 65 00
포인터 수: n = (first_ptr - current_pos) / 2
```

대화 블록에 들어왔는지는 `65 00/01` 다음 바이트가 SJIS 선행 바이트(`0x81~0x9F`,
`0xE0~0xFC`)인지, 아니면 제어 바이트(`62~76`)인지로 판별한다.

### 3. 반각 (0x85XX)

상점 가격·몬스터명·UI 등 일부 텍스트는 표준 SJIS 대신 반각 영역(`0x85XX`)을 쓴다. 인코딩
상세(ASCII·반각 카타카나·탁점 카타카나 매핑)는 `compile_lz.py`를 참조하고, 처리는
`compile_lz.read_sjis_char()`/`encode_halfwidth_char()`가 맡는다.

한글도 좁은 슬롯(전투 적 이름·UI 아이템 라벨)에는 같은 방식으로 반각을 쓴다.
`0x85A4~0x85EC` 슬롯에 한글 글리프를 그려 넣고 `/X` 마커로 인코딩했다. 적 이름은
에디터의 `enemy` 태그로 식별하고, 반각 한글의 전체 절차는 `tools/NOTES.md`의 "반각 한글"
섹션에 있다.

### 4. 파싱

`hukyou_parser.py`를 실행하면 `translation/hukyou/translation.json`이 생성된다. 파서를
재실행해도 기존 `kr`·`tag` 값은 `(file, offset)` 정확 매칭을 1차로, 안 되면 `(file, jp)`
텍스트 기반 매칭을 2차로 써서 보존한다.

`translation.json`의 최상위 키는 `dialogs`(대화)·`items`(아이템)·`ui`(UI 문자열)다. 각
항목은 `file`, `offset`, `jp`, `jp_len`, `kr`, `tag`를 공통으로 갖고, 반각이 포함된
항목에는 `halfwidth: true`가 붙는다. 태그는 `dialog`/`monolog`/`cutscene`/`char`/
`battle`/`item`/`menu`/`location`/`system`이다.

### 5. 재삽입

`hukyou_inserter.py`를 실행하면 `build/hukyou/`에 결과가 나온다. 오프셋은 내림차순으로
처리해서 앞쪽 오프셋이 안 밀리게 하고, 정상 텍스트는 `jp.encode('shift_jis')`로 검증한
뒤 교체한다. 반각 텍스트는 `jp_len` 기준 길이로 교체하면서 `use_halfwidth=True`로
인코딩한다. 교체한 KR이 원문보다 짧으면 전각 공백(`\x81\x40`)으로 채우고, 길면 SJIS
경계에서 잘라낸다.

### 6. 빌드

GF2.COM은 부트스트랩(`0x000~0x070`)을 보존한 채로 수정된 내용만 LZ로 재압축하고,
`GF2_PAD_SIZE` 오프셋 보정을 적용한다.

---

## 참고

**SJIS 범위 검증이 꼭 필요하다.** 바이트 범위만 보면 실제 SJIS에 없는 코드(`0x8865`,
`0xFC65` 등)를 걸러내지 못하기 때문에, `data[i:i+2].decode('shift_jis')`로 검증한다
(0x85XX 반각은 예외).

**1바이트 ASCII는 화면에 직접 못 띄운다.** 게임 렌더러가 raw 1바이트 ASCII(`0x41` 등)를
직접 표시하지 못해서, 기본은 전각으로 자동 변환하고(`ASCII_TO_FULLWIDTH`) 반각이 필요하면
`/X` 시퀀스로 2바이트 SJIS 반각 영역(`0x85XX`)을 쓴다.

**MESSAGE.CMD는 이중 구조다.** 다른 CMD 파일과 달리 아이템 데이터와 대화가 한 파일에
같이 있다. 앞부분은 `extract_items`로, 뒷부분은 `extract_dialogs`로 처리해야 하고, 교차
적용하면 오탐이 난다.

**크레딧 체인의 첫 항목이 빠지는 문제(ENDING.CMD)도 있었다.** 크레딧은 `63 08 [텍스트]
65 00`이 반복되는 구조인데, `extract_dialogs`는 `65 00` 뒤에 `63`이 올 때 진입해서
(`is_65_start`의 0x63 분기) *다음* 항목을 잡는다. 그래서 체인의 첫 항목은 앞에 여는
`65 00 63`이 없어서 빠진다. 실제로 ENDING의 첫 크레딧 `企画`(offset 1539)가 이렇게
빠져 있어 `기획`으로 수동 추가했다. 파서를 고쳐서 잡으려 하면 다른 파일의 `63 08`
노이즈까지 같이 잡힐 위험이 있어서, 이런 단건은 수동 보완이 더 안전하다고 판단했다.
