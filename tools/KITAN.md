# 환세희담 역공학 노트

**대상**: 환세희담 / 幻世喜譚 (Compile, 1995, PC-98)  
**상태**: 완료  
**도구**: `kitan_parser.py` (추출) · `kitan_inserter.py`/`kitan_demo_inserter.py` (재삽입, 본편/오프닝)

---

## 개요

### 파일 구성

**FDI 이미지 3장** — 시스템(`kitan-system.fdi`)·데이터(`kitan-data.fdi`)·데모
(`kitan-demo.fdi`). `original/kitan/`에 디스크별로 나눠서 그 안의 파일을 개별로 추출해
둔다.

```
original/kitan/
  data/     데이터 디스크에서 추출한 CMD·CNS·DAT 등 게임 파일
  system/   시스템 디스크에서 추출한 파일
  demo/     데모 디스크에서 추출한 파일
```

에뮬레이터는 두 페이지로 나뉜다. `emulator/kitan.html`이 본편(system + data 디스크)이고
`emulator/kitan-opening.html`이 오프닝(demo + data 디스크)인데, ⛁ 버튼으로 서로 전환할
수 있다.

### demo 디스크 파일 구성

FAT12 MEGDOS 포맷이라 `pc98disk.py`로 추출할 수 있다.

```
SP1.COM       메인 데모 플레이어 (x86 실행 파일)
SONG.DAT      FMP 포맷 음악 ("ESC @" 헤더)
TITLE0.DAT    타이틀 화면 B bitplane (Compile LZ)
TITLE1.DAT    타이틀 화면 R bitplane (Compile LZ)
TITLE2.DAT    타이틀 화면 G bitplane (Compile LZ)
TITLE3.DAT    타이틀 화면 E bitplane (Compile LZ)
KIRINASI.CNS  삽입 화면 (CNS 형식 A: 4 스트림)
DATA01C.CNS   씬 이미지 (CNS 형식 B: 단일 스트림)
…DATA10C.CNS  (동일)
DATA_OP.CNS   애니메이션 시퀀스 테이블 (단일 스트림)
DATA1~11.DAT  소형 씬 요소/오버레이
AAA.DAT       용도 미확인
BPLAY.COM, FPLAY.COM, FDS.COM, GSC.COM   서브 실행 파일
```

### DISK_B.DAT 아카이브 포맷 (시스템 디스크)

시스템 FDI 안의 DISK_B.DAT는 130개 이상의 파일을 담은 독자 아카이브 포맷이다.

```
[0x000]  00 00 00 04   매직 (4바이트)
[0x004]  N×4바이트     파일 종료 오프셋 테이블
[0x400~] 파일 데이터   파일 0 시작 오프셋 = 0x400
```

오프셋은 4바이트 엔트리마다 이렇게 인코딩된다.

```python
high = struct.unpack_from('<H', entry, 0)[0]
low  = struct.unpack_from('<H', entry, 2)[0]
end_offset = high * 65536 + low   # 파일 N의 끝 = 파일 N+1의 시작
```

파일 N의 시작은 이전 엔트리의 end_offset이고(파일 0은 0x400), 크기는 `entry[N] −
entry[N−1]`이다. 엔트리 수는 `(0x400 − 4) / 4 = 255`개가 최대지만 실제 파일 수는 더
적고, `end_offset == 0`인 엔트리가 나오면 거기서 끝이다.

**kitan-data.fdi(DISK_C)**는 FAT가 없는 raw 파티션이다. FDI 파일의 `0x3C00` 오프셋부터
DISK_C 데이터가 시작하고, DISK_B.DAT의 같은 오프셋 표를 참조해서 파일 범위를 계산한 뒤
그 범위를 DISK_C 데이터에서 읽는다.

### 패치 대상 파일 (아카이브 내 인덱스)

`kitan_inserter.py`의 `DISK_B_INDEX`/`DISK_C_INDEX`가 파일명과 아카이브 엔트리 번호를
고정으로 매핑해 둔다(예: `GS.OVL`→0, `START.CMD`→2, `SC1A.CMD`→11 — 전체 매핑은
`kitan_inserter.py`의 두 딕셔너리가 원본이라 여기 다시 옮기지 않는다). 번역 텍스트가
있는 CMD 파일은 그 두 딕셔너리에 있는 게 전부이고, 나머지 130여 개 엔트리 중 거기
없는 건 그래픽·음악 등 텍스트가 아닌 데이터라 건드리지 않는다.

**DISK_C (kitan-data.fdi)**: `PARTY7.CMD` → 인덱스 81 (본편에서 유일하게 DISK_C에 있는
텍스트 파일). 나머지는 전부 DISK_B(kitan-system.fdi)에 있다.

**demo 디스크**: `SP1.COM`만 별도로 패치한다(`kitan_demo_inserter.py`, "demo 디스크
파일 구성" 절 참조).

---

## 작업 흐름

### 1. 압축 해제

모든 CMD 파일은 Compile LZ로 압축되어 있어 `compile_lz.decompress()`로 푼다.

### 2. 제어코드

**대화 제어코드**:

| 코드 | 의미 |
|------|------|
| `6b 00` | 대화 블록 경계 (새 블록 시작 + 이전 블록 종료) |
| `72 XX` | 줄바꿈 |
| `73 XX` | 페이지 표시 후 대기 |
| `76 XX` | 화면 클리어 후 계속 |
| `64 XX` | 항목 구분 (stat/desc 분기) |
| `13 00` | 메뉴 선택지 포인터 테이블 |

대화 블록은 다음 패턴을 따른다.

```
6b 00 [선택: 80 77 00 등 캐릭터 코드]
SJIS 텍스트 [72 01 줄바꿈 | 73 30 페이지 | 76 1a 클리어]
...
6b 00  ← 다음 블록 시작 (이 블록 종료)
```

`6b 00` 이후 30바이트 안에 SJIS가 없으면 바이너리 이벤트 블록으로 보고 건너뛴다
(`_DIALOG_LOOKAHEAD = 30`).

**아이템 포맷(MESSAGE.CMD)**은 다음과 같다.

```
62 00 0f 03  SJIS이름  64 XX  SJIS스탯  72 01  SJIS설명줄  72 01  ...
62 00 0f 03  (다음 항목)
```

`62 00`이 항목 시작 프리픽스, `0f 03`이 아이템 데이터 시작 마커다. `64 XX`에서
`XX≠02`면 스탯(소비MP/SP, 공격력 등)이고 `64 02`면 설명 줄 시작이며, 스탯 이후 첫
`72 01`이 설명 줄로 전환되는 지점이다.

스크립트 파일은 다음과 같이 구성된다.

```
START.CMD
SC1A.CMD SC1B.CMD
SC2A.CMD ~ SC2G.CMD
SC3A.CMD ~ SC3E.CMD
SC4A.CMD ~ SC4E.CMD
SC5A.CMD ~ SC5F.CMD
SC6A.CMD ~ SC6D.CMD
SC7A.CMD
PARTY2~4.CMD PARTY6~7.CMD  (PARTY1, PARTY5 없음)
BTL_PC.CMD   전투 AI (바이너리 전용, 텍스트 없음)
ENDING.CMD   엔딩
MESSAGE.CMD  아이템 DB
```

### 3. 반각 (0x85XX)

풍광전과 같은 방식으로 `charmap.json` 기반(`encode_korean_kitan`)으로 한글 반각을
인코딩한다. 사용법과 전체 매핑(한글 71+2자, ASCII 94자)은 `tools/NOTES.md`의 "반각 한글"
섹션에 있다.

`battle` 태그 스킬명 중 일부는 `[SJIS 이름][반각 코스트 0x85XX…]`가 구분자 없이 붙어
있다. 원본에는 `大撃剣` + `85 47 85 72 85 6F 85 50 85 4F 85 48`(`(SP10)`의 반각)처럼
저장돼 있는데, 파서는 `0x85`를 만나면 추출을 멈춰서 `jp`에는 스킬명만 담고 `jp_len`도
그 길이까지만 잡는다. 인서터는 `jp_len` 범위만 패치하므로 반각 영역은 자연히 보존된다.

**반각 폭이 넘치는 문제**: 원본이 `0x85XX` 반각으로 저장한 텍스트(예: `リフレッシュの水`은
반각 6자 + 전각 2자 = 시각 폭 5)는 원본 게임이 좁은 슬롯에 맞추려고 반각으로 우회한
것이다. KR을 그냥 전각 한글로 번역하면(`리프레시워터` = 6자, 시각 폭 6) 슬롯 픽셀 폭을
넘어서 다음 텍스트 위치를 밀어내거나 그리기 잔상이 남는 문제가 생긴다. 해결책은 아래
"반각 한글 마커"의 `/X` 시퀀스로 KR도 똑같이 반각 처리하는 것이다(예:
`/리/프/레/시워터`). 인서터의 `_compute_visual_width`+`_truncate_overwidth_kr`이 안전망
역할을 한다 — JP 바이트를 스캔해 시각 폭을 계산하고(반각·반각 ASCII는 0.5, 전각 SJIS는
1.0) KR이 그 폭을 넘으면 글자 단위로 잘라내면서 경고를 내서, 번역자에게 `/X` 적용이
필요하다는 신호를 준다.

**반각 한글 마커(적용 완료)**: KR 텍스트에서 `/X` 형태로 시작하는 두 글자는 반각
한글로 해석한다. 인서터(`encode_korean_kitan`)가 `/리`를 `0x85A4`로 인코딩하고 폭
계산도 0.5로 처리한다. 처음엔 `0x95XX` 한자 영역에 넣어봤는데 게임 렌더러가 전각으로
출력해서 실패했고, 지금은 PC-98 폰트의 반각 카나 영역(`0x85A4~0x85EC`)에 한글 글리프를
추가하는 방식을 쓴다 — 이쪽은 게임이 dot-by-dot 반각으로 출력해서 정상 동작한다. 희담
안에서 `리프레시워터` 류 41건이 이렇게 `/리/프/레/시워터` 형태로 변환됐다.

### 4. 파싱

`tools/kitan_parser.py`가 위 포맷을 파싱해 `translation/kitan/translation.json`을
만든다.

```bash
python3 tools/kitan_parser.py original/kitan/data
```

출력 JSON은 세 섹션으로 나뉜다.

```json
{
  "dialogs": [...],   // CMD 파일 대화·메뉴 (파일별 그룹)
  "gsovl":  [...],   // GS.OVL 고정 오프셋 문자열 (배틀 메뉴·UI 라벨·캐릭터 이름)
  "items":  [...]    // MESSAGE.CMD 아이템 DB
}
```

추출 패턴은 다음과 같다.

| 패턴 | 대상 파일 | 내용 | 함수 |
|------|-----------|------|------|
| `6b 00` 블록 | 모든 CMD | 일반 대화 / 메뉴 항목 | `extract_dialogs` |
| `6e 00 67 01 [SJIS]` 블록 | 모든 CMD | 화자 prefix 후 본문 진입 | `extract_dialogs` |
| `01 02 [SJIS]` 블록 | 모든 CMD | 감정/화자 코드 체인 후 본문 (블록 외부 한정) | `extract_dialogs` |
| `76 1a [SJIS]` 블록 | 모든 CMD | 화면 클리어 직후 본문 (블록 외부 한정) | `extract_dialogs` |
| `02 65 [SJIS]` 블록 | 모든 CMD | 화자 체인 종료 후 본문 (in_dialog 무관, flush 동반) | `extract_dialogs` |
| `13 00` 포인터 블록 | 모든 CMD | 분기 메뉴 선택지 | `extract_menus` |
| `64 01 / 64 03 / 6d 04 / 6d 11 [SJIS] 65 XX` | 모든 CMD (MESSAGE 제외) | 세이브/메뉴 라벨 (`64 03` = 슬롯 선택, `6d 04` = 메뉴 두 번째 셋, `6d 11` = SC6B 층수 prefix) | `extract_labeled_text` |
| `63 08 [SJIS] 65 XX` | ENDING.CMD 전용 | 제작진 크레딧 | `extract_labeled_text` |
| `6d 08 [SJIS] 65` | PARTY2~7.CMD 전용 | 적/NPC 이름 | `extract_labeled_text` |
| bare SJIS + `65` | SC6A/6B/6C.CMD | 층수 이름 (`　４階　` 등) | `extract_bare_sjis65` |
| `[SJIS] 72 01 ... 65` | MESSAGE.CMD 전용 | 스토리 대화; 0x1290~EOF 연속 배치 | `extract_message_dialog` |
| 상점 인벤토리 (`64 00 96 48 [name] 64 XX [price] 72 01 [desc] ...`) | SC1A/3A/4A/6D/7A | 이 영역도 `extract_dialogs`가 통째로 처리한다 — `64 00`이 4바이트 portrait 오피코드로 `96 48`까지 스킵되어 자연스럽게 `name`부터 잡힌다 | `extract_dialogs` |
| `0f 03` 블록 | MESSAGE.CMD 전용 | 아이템 DB (이름/스탯/설명) | `extract_items` |

MESSAGE.CMD는 `extract_dialogs`가 `_MSG_DIALOG_START`(0x1290) 이전 영역만 스캔한다 —
스토리 대화 영역에서 중복 추출되는 걸 막기 위해서다.

**파싱하면서 실제로 걸렸던 것들:**

- `6d 08 [SJIS] 65` 패턴에서 `65`는 1바이트 종결자다(2바이트 오피코드가 아니다). 다음
  항목의 `6d 08`이 `65` 바로 뒤에 이어지기 때문에 `j += 1`로 처리해야 연속 항목이
  안 빠진다 — `j += 2`로 처리하면 홀수 번째 항목만 추출되는 버그가 있었다.
- `extract_dialogs`에서 `64 00`은 portrait/캐릭터 코드 + 2바이트 인수라 총 4바이트
  오피코드다. 인수 바이트가 우연히 SJIS를 형성해 텍스트에 붙는 걸 막으려고 4바이트를
  스킵하면서 텍스트도 리셋한다. 비-SJIS 바이트가 나오면 마찬가지로 텍스트를
  리셋하는데, 이건 이벤트 데이터 안의 우연한 SJIS 쌍이 누적되는 걸 막기 위해서다.
  `6d 04 [SJIS] 6d 00 65` 형식에서는 `6d 00`이 flush 트리거가 되어 텍스트가 정상
  추출된다.
- `extract_message_dialog`에서 `00 02` 프리픽스는 섹션이 처음 시작할 때(0x128E)만
  붙고, 이후 블록은 `65` 종료 직후 바로 다음 블록이 시작된다. 반각가나 등 비-SJIS
  바이트는 리셋 없이 그냥 스킵한다.

### 5. 재삽입

`tools/kitan_inserter.py`가 CMD 파일을 패치한 뒤 FDI에 직접 삽입한다(본편, system+data
디스크 대상). `tools/kitan_demo_inserter.py`는 같은 구조를 오프닝(demo+data 디스크)에
적용하는 대응 스크립트다.

```bash
# 1. CMD 빌드 (build/kitan/ 생성)
#    인수는 게임 파일 소스 디렉토리 (system/data 디스크 파일이 모두 여기 있음)
python3 tools/kitan_inserter.py original/kitan/data

# 2. FDI 패치 — system·data 양쪽 FDI에 각각 호출 (editor.py "번들 생성"이 내부적으로 수행)
#    patch_fdi()가 FDI 타입을 자동 감지해 해당 인덱스 맵 적용
from kitan_inserter import patch_fdi
result, patched = patch_fdi(fdi_data_system, 'build/kitan')  # → DISK_B_INDEX 파일 삽입
result, patched = patch_fdi(fdi_data_data,   'build/kitan')  # → DISK_C_INDEX 파일 삽입
```

텍스트 길이는 원본 바이트 크기로 고정이라 넘치면 잘림 경고를 내고 truncate한다. FDI
삽입은 DISK_B.DAT 오프셋 테이블로 슬롯 위치와 크기를 계산해서 그 범위 안에서
overwrite한다 — 파일 크기가 안 바뀌니 오프셋 테이블을 갱신할 필요가 없다. 슬롯보다
크면 건너뛴다. 대부분의 CMD는 `kitan-system.fdi` 안 DISK_B.DAT(base `0x14400`)를 쓰고,
`PARTY7.CMD`만 `kitan-data.fdi`(base `0x3C00`)를 쓴다.

패치 대상은 태그로 분류된다.

| tag | 내용 |
|-----|------|
| `battle` | 배틀 메뉴 (공격·마법·특기·도망·아이템, 스킬명) |
| `status` | 상태 표시 라벨 (精神力·魔力·特技·魔法·正常·毒·気絶) |
| `name` | 캐릭터 이름 — 스테이터스 창(0x5638) + HUD 상시 표시(0x58A8) 두 곳에 각각 |
| `stat` | 스탯 창 라벨 (レベル·生命力·経験値·攻撃力·素早さ·防御力·武器·防具·道具·所持金) |
| `misc` | 기타 (残金·誰が持つ？) |

압축 해제한 뒤 KR 바이트로 교체하고 남는 슬롯은 `00 F4`로 채운다. 슬롯 크기는 원본
SJIS 바이트 수 그대로고, 넘치면 경고 후 건너뛴다.

파서가 비텍스트 바이트를 SJIS로 잘못 읽는 경우가 있다(예: `'＄喪'`, `'殳舩'` 같은
깨진 한자열). 이런 항목은 `tag == 'ignore'`로 표시해 두면 인서터가 항상 패치 대상에서
빼고, 에디터에서도 `ignore`를 적용하면 KR이 자동으로 비워져서 잘못된 패치 사고를
막는다.

**GS.OVL 패치**: `GS.OVL`은 배틀 메뉴·UI 라벨·캐릭터 이름 등 게임 전반의 UI 문자열을
담고 있다. `kitan_parser.py`가 고정 오프셋에서 문자열을 추출해 `translation.json`의
`gsovl` 섹션에 저장하고, `kitan_inserter.py`가 그걸 읽어 패치한 뒤
`build/kitan/GS.OVL`을 낸다. GS.OVL은 DISK_B_INDEX 0번이라 `patch_fdi` 호출 시 system
FDI에 자동으로 들어간다.

> **고정 오프셋 누락 = 그 문자열은 번역이 안 된다.** GS.OVL 추출은 `_GSOVL_OFFSETS`
> 하드코딩 테이블에만 의존하고 스캔하지 않는다. 테이블에 없는 오프셋의 문자열은
> 추출조차 안 돼서 게임에 일본어 원문이 그대로 노출된다. 인서터는 json 기반이라, 누락된
> 라벨은 파서를 다시 돌리지 않고 `translation.json`의 `gsovl`에 `{offset, tag, jp,
> jp_len, kr}` 항목을 직접 추가하면 패치된다(다음에 파서를 다시 돌려도 보존되게 하려면
> `_GSOVL_OFFSETS`에도 같은 오프셋을 추가해 둬야 한다). 실제로 전투 중 상태이상 라벨
> `毒`(0x45AF)·`気絶`(0x45BC)과 메뉴 상태목록의 `毒`(0x582B)이 테이블에서 빠져 무번역으로
> 남아 있던 걸 이렇게 3건 추가해서 해결했다.

### 6. 빌드

`editor.py`의 빌드 버튼이 인서터→FDI 패치→`file_packager.py` 번들 교체를
오케스트레이션한다. 풍광전·쾌도전과 같은 구조다.

---

## 디버깅 — 패치가 게임 그래픽/로직을 깨뜨릴 때

번역 패치를 적용한 뒤 원본에 없던 시각적 깨짐이 보이면, 다음 순서로 원인 파일·entry를
좁혀 나간다.

**1. 원본 FDI 확보.** 희담 원본 FDI는 커밋 `9ee4c97` 시점에 추가돼 있다.

```bash
mkdir -p /tmp/kitan-orig
git show 9ee4c97:emulator/rom/kitan-system.fdi > /tmp/kitan-orig/kitan-system.fdi
git show 9ee4c97:emulator/rom/kitan-data.fdi   > /tmp/kitan-orig/kitan-data.fdi
```

네이티브 NP2kai에 띄워서 원본에서도 같은 문제가 있는지 먼저 확인한다.

**2. 파일 단위 이진 탐색.** `build/kitan/`에서 의심되는 파일 한두 개만 골라
`patch_fdi`로 임시 FDI를 만든다.

```python
import sys, shutil, os
sys.path.insert(0, 'tools')
from kitan_inserter import patch_fdi

# 의심 파일만 골라 임시 build 디렉토리 구성
tmp_build = '/tmp/build_subset'
os.makedirs(tmp_build, exist_ok=True)
shutil.copy('build/kitan/SC1A.CMD', tmp_build)   # 의심 파일만

with open('/tmp/kitan-orig/kitan-system.fdi', 'rb') as f:
    fdi = f.read()
patched, files = patch_fdi(fdi, tmp_build)
with open('/tmp/test.fdi', 'wb') as f:
    f.write(patched)
```

**3. CMD 파일 내 offset 범위 분할.** 특정 CMD가 범인으로 좁혀지면, 그 안의 entry를
offset 절반씩 나눠서 적용해 본다. `collect_replacements()`가 낸 `[(offset, old,
new), ...]`를 offset으로 정렬해서 반씩 나누고, `patch_data()` + `compress()`로 재빌드한
뒤 `patch_fdi`로 슬롯에 넣는다. 수십 줄짜리 1회용 스크립트로 충분하고, 절반씩 줄여
가면 보통 5~7회 안에 단일 entry까지 좁혀진다.

**4. 흔한 원인 패턴**은 세 가지였다.

- fill-bar를 잘못 써서 엉뚱한 entry에 메뉴 텍스트가 채워지고, 폭주한 KR이 비텍스트
  영역을 침범한 경우 — `ignore` 태그를 걸고 KR을 비운다.
- 파서가 바이너리 영역을 SJIS로 잘못 해석한 경우(jp가 깨진 한자, jp_len이 비정상적으로
  큼).
- 반각 경계 문제 — GS.OVL처럼 텍스트와 반각이 혼합된 영역에서 반각을 덮어쓰는 경우.
  파서가 `0x85` 경계에서 멈춰야 한다.

---

## 그래픽 포맷 (데모 화면)

공통 사항: 해상도는 640×400 16색(bitplane 방식)이고, bitplane 하나는 640×400/8 =
32000바이트다. LZ 압축은 `compile_lz.decompress()`를 공통으로 쓰고, 픽셀 인덱스는
`idx = B | (R<<1) | (G<<2) | (E<<3)`(B=A800, R=B000, G=B800, E=E000)로 조합한다.

**타이틀 화면(TITLE0-3.DAT)**은 파일 하나가 bitplane 하나이고 4개가 독립적으로
압축돼 있다.

```
TITLE0.DAT → A800 (B plane), 해제 시 32000 bytes
TITLE1.DAT → B000 (R plane)
TITLE2.DAT → B800 (G plane)
TITLE3.DAT → E000 (E plane)
```

팔레트는 `SP1.COM`의 `0x0b50`에 있고, 4바이트 엔트리 `[idx, R, G, B]`(값 범위 0-15,
×17로 0-255 변환)로 구성된다.

```
[0]#553300  [1]#000000  [2]#002222  [3]#224444
[4]#446666  [5]#668888  [6]#99aaaa  [7]#551122
[8]#991111  [9]#bb2200  [A]#ee4422  [B]#885500
[C]#bb8833  [D]#ddbb77  [E]#ffffbb  [F]#ffffff
```

**CNS 형식 A — KIRINASI.CNS(확인 완료)**: null-terminated LZ 스트림 4개가 연속으로
이어진 구조다. 각 스트림을 풀면 32000바이트로 bitplane 하나가 되고, 순서는
[B, R, G, E]다.

```python
# 다중 스트림 해제 (compile_lz.decompress의 0x00 종료 활용)
def decompress_multi(data):
    streams = []
    i = 0
    while i < len(data):
        output = bytearray()
        while i < len(data):
            al = data[i]; i += 1
            if al == 0: break
            if al & 0x80:
                length = (al & 0x7f) + 3
                offset = data[i] + 1; i += 1
                for _ in range(length):
                    pos = len(output) - offset
                    output.append(output[pos] if pos >= 0 else 0)
            else:
                output.extend(data[i:i + length]); i += length
        if output: streams.append(bytes(output))
        else: break
    return streams  # streams[0]=B, [1]=R, [2]=G, [3]=E
```

**CNS 형식 B — DATA01C-DATA10C.CNS(미해독)**: 단일 LZ 스트림인데 해제 크기가 파일마다
달라서 32000의 배수가 아니다. 2차 시도(아래)에서 `bgput_sub` 포맷 자체는 확인했지만
이 파일들 본체에 적용되진 않는 것으로 보여 역공학은 다시 중단, 에뮬 방식으로 넘어갔다.

**참고 — SP1.COM 구조(부분)**:

```
0x0b50    타이틀 화면 팔레트 (16 × 4-byte)
0x3883    CNS 파일명 테이블
0x7618    CNS 파일명 확장 테이블
0x23B0    LZ 디컴프레서 (ES:DI = VRAM 직접 쓰기)
0x7cb9    bgput_sub — VRAM 블릿 루틴 (아래 참고)
0x7a6b    graphic_sub — EGC 포트(0xa2/0xa4/0xa6/0x7c/0x7e/0xa8/0xaa/0xac/0xae)
          조작 루틴 다수. 화면clear·팔레트 설정은 확인했지만 나머지는 미확인
0x7616    "A:DATA31C.CNS"~"A:DATA34C.CNS" 파일명 문자열 — 코드엔 있는데
          `original/kitan/demo`엔 해당 파일 없음(추출 누락인지 사용 안 하는
          죽은 경로인지 미확인)
```

### `bgput_sub` 역공학 기록 (2차 시도 — 부분 성공, 본체 미해결)

**확인된 것**: `SP1.COM`을 `ndisasm`으로 디스어셈블해서 `bgput_sub`(VRAM에 사각형을
그리는 실제 블릿 루틴)를 찾았다. 알고리즘:

```
si, ds = (전달받은 오프셋, 세그먼트) — 그려질 사각형 데이터가 담긴 버�터를 가리킴
루프(si != 0 인 동안):
    si -= 2;  di = word[si]     # VRAM 목적지 오프셋
    si -= 1;  ah = byte[si]     # 한 줄당 바이트 수 (가로 = ah*8 px)
    si -= 2;  bx = word[si]     # 줄 수 (세로 px)
    각 플레인(E=0xE000, G=0xB800, R=0xB000, B=0xA800 순서로 4번):
        si -= ah*bx             # 이 플레인의 픽셀 바이트 (헤더 바로 앞)
        VRAM[di]에서 시작해 한 줄에 ah바이트씩, 한 줄마다 di -= 0x50(=80,
        한 스캔라인)씩 올라가며 bx줄 복사
```

즉 파일 끝에서부터 거꾸로 `[4플레인 픽셀][di][ah][bx]` 5바이트 헤더+데이터 단위를
반복해서 읽는 구조. **픽셀 디코드 파이프라인(팔레트·비트순서·플레인조합 idx공식)은
이미 확인 완료인 `KIRINASI.CNS`로 재검증해서 100% 정확함을 확인**했다(동일 코드로
렌더하면 삽입화면이 그대로 나옴).

**안 되는 것**: 이 5바이트 헤더 형식으로 `DATA01C.CNS` 전체(13만 바이트)를 파일 끝부터
쭉 읽어보면 처음 한두 개는 그럴듯한 값(가로 448px×56줄 등)이 나오지만, **전체 13만
바이트에 대해 모든 시작 위치로 무차별 대입**해본 결과 si가 정확히 0까지 소진되는
지점은 **0개**, 레코드 3개 이상 연속으로 말이 되는 지점도 8개뿐(최대 4개 연속)이었다.
`ah≤80,bx≤400`이라는 느슨한 유효성 조건은 무작위 바이트로도 절반 확률로 통과하므로,
13만 바이트 중 우연히 3~4개 맞아떨어지는 지점이 몇 군데 나오는 건 통계적으로
당연하다 — 즉 **처음 "성공"으로 보였던 레코드는 우연의 일치였을 가능성이 높다.**

**결론**: `bgput_sub` 자체는 실재하는 VRAM 블릿 루틴이 맞고 포맷도 위와 같이 확인했지만,
`DATA01C~10C.CNS` 본체 대부분을 그리는 데는 이 루틴이 직접 쓰이지 않는 것으로 보임.
`graphic_sub` 쪽에 EGC 포트(0x7c·0x7e 등)를 건드리는 코드가 있어 하드웨어 가속
블릿/패턴채우기(소프트웨어 memcpy가 아닌 별도 메커니즘)일 가능성이 있으나 미확인.
또한 `bgput_sub`가 읽는 si/ds 상태 변수(`0xa478`·`0xa47a`·`0xa47c`·`0xa47e`)를
실제로 채워 넣는 "로더" 코드는 직접 주소 참조로는 못 찾음(간접 addressing 사용 추정,
추가 역공학 필요).

### `DATA_OP.CNS` 구조 (부분 해독)

압축 해제 후 16비트 LE 워드로 읽으면 **"짧게 증가하는 정수 몇 개 + 0으로 채워진
패딩"이 반복되는 구조**가 뚜렷하게 보인다(이건 우연이 아니라 파일 전체에서 일관됨):

```
1,2,3,4, [0×16], 5,6,7,8,9, [0×15], 10,11,12,13,14, [0×15], 15,16,17,18,19,20, [0×16], ...
```

값이 항상 순증가하지는 않고(`...50,24,...`처럼 뒤로 떨어지는 경우 있음), 파일 뒷부분엔
`0x8000` 비트가 붙은 값과 안 붙은 값이 섞여 나옴(예: `32931(=0x8000+163), 164,
32933(=0x8000+165), ...` — 164만 플래그 없음). **여러 오브젝트/트랙의 프레임 구간을
번갈아 나열하는 스크립트**로 추정되나(0x8000 비트 = "신규 정의" 플래그 등), 각 구간이
`DATA1~11.DAT` 어느 파일의 몇 번째 프레임을 가리키는지는 아직 매칭 못 함. "애니메이션
시퀀스 테이블"이라는 정체성은 확실하고, 다음에 이어서 팔 만한 각도로는 이게
`DATA01C~10C.CNS`보다 훨씬 유망함(구조가 명확하고 통계적 우연이 아님).
