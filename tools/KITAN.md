# 환세희담 역공학 노트

**대상**: 환세희담 / 幻世喜譚 (Compile, 1995, PC-98)  
**상태**: 완료  
**도구**: `kitan_parser.py` (추출) · `kitan_inserter.py`/`kitan_demo_inserter.py` (재삽입, 본편/오프닝)

---

## 개요

### 파일 구성

```
original/kitan/
  unpacked/ 시스템 디스크 DISK_B 아카이브(CMD류) + 데이터 디스크 DISK_C·그래픽/음악 자산을
            낱개 파일로 언패킹해 모아둔 작업 폴더 (파서·인서터가 여기서 읽고 씀)
  system/   시스템 디스크에서 추출한 파일 (DISK_B.DAT 원본 아카이브 포함)
  demo/     데모 디스크에서 추출한 파일
```

`unpacked/`의 CMD 파일 중 상당수는 물리적으로 `system/DISK_B.DAT` 안에 패킹돼 있던 걸 풀어놓은
것이라, 재삽입 시 다시 `kitan-system.fdi`(시스템 디스크)에 써넣는다 — 폴더 이름만 보고
"data → kitan-data.fdi로만 감"이라고 오해하지 않도록 주의. 정확한 파일별 목적지는 아래
"패치 대상 파일" 표 참조.

에뮬레이터:
- `emulator/kitan.html` — 게임 플레이 (system + data 디스크)
- `emulator/kitan-opening.html` — 오프닝 (demo + data 디스크)
- ⛁ 버튼으로 두 페이지 간 전환 가능

### demo 디스크 파일 구성

FAT12 MEGDOS 포맷. `pc98disk.py`로 추출 가능.

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

시스템 FDI 내 DISK_B.DAT는 130개 이상의 파일을 담은 독자 아카이브.

```
[0x000]  00 00 00 04   매직 (4바이트)
[0x004]  N×4바이트     파일 종료 오프셋 테이블
[0x400~] 파일 데이터   파일 0 시작 오프셋 = 0x400
```

**오프셋 인코딩** (각 4바이트 엔트리):
```python
high = struct.unpack_from('<H', entry, 0)[0]
low  = struct.unpack_from('<H', entry, 2)[0]
end_offset = high * 65536 + low   # 파일 N의 끝 = 파일 N+1의 시작
```

- 파일 N의 시작 = 이전 엔트리의 end_offset (파일 0은 0x400)
- 파일 N의 크기 = entry[N] − entry[N−1]
- 엔트리 수 = (0x400 − 4) / 4 = 255 (최대), 실제 파일 수는 더 작음  
  → `end_offset == 0` 인 엔트리가 나오면 종료

**kitan-data.fdi (DISK_C)**:

FAT 없는 raw 파티션. FDI 파일 내 0x3C00 오프셋부터 DISK_C 데이터.  
DISK_B.DAT의 동일 오프셋 표를 참조해 파일 범위를 계산, 그 범위를 DISK_C 데이터에서 읽음.

### 패치 대상 파일 (아카이브 내 인덱스)

`kitan_inserter.py`의 `DISK_B_INDEX`/`DISK_C_INDEX`가 파일명 ↔ 아카이브 엔트리 번호를 고정 매핑.
번역 텍스트가 있는 CMD 파일은 이게 전부이며, 나머지 엔트리(약 130여 개 중 여기 없는 것)는
그래픽·음악 등 비텍스트 데이터라 건드리지 않는다.

**DISK_B.DAT (kitan-system.fdi)**:

| 파일 | 인덱스 | 파일 | 인덱스 | 파일 | 인덱스 |
|---|---:|---|---:|---|---:|
| GS.OVL | 0 | SC2G.CMD | 20 | SC5A.CMD | 77 |
| START.CMD | 2 | PARTY3.CMD | 29 | SC5B.CMD | 78 |
| MESSAGE.CMD | 3 | PARTY4.CMD | 30 | SC5C.CMD | 79 |
| PARTY2.CMD | 4 | PARTY6.CMD | 31 | SC6A.CMD | 89 |
| BTL_PC.CMD | 6 | SC3A.CMD | 43 | SC6B.CMD | 90 |
| SC1A.CMD | 11 | SC3B.CMD | 44 | SC6C.CMD | 91 |
| SC1B.CMD | 12 | SC3C.CMD | 45 | SC6D.CMD | 93 |
| SC2A.CMD | 14 | SC3D.CMD | 46 | SC7A.CMD | 115 |
| SC2B.CMD | 15 | SC3E.CMD | 47 | SC4E.CMD | 116 |
| SC2C.CMD | 16 | SC5D.CMD | 52 | ENDING.CMD | 119 |
| SC2D.CMD | 17 | SC5E.CMD | 53 | | |
| SC2E.CMD | 18 | SC5F.CMD | 54 | | |
| SC2F.CMD | 19 | SC4A.CMD~SC4D.CMD | 57~60 | | |

**DISK_C (kitan-data.fdi)**: `PARTY7.CMD` → 인덱스 81 (본편에서 유일하게 DISK_C에 있는 텍스트 파일).

**demo 디스크**: `SP1.COM`만 별도 패치 (`kitan_demo_inserter.py`, "demo 디스크 파일 구성" 절 참조).

---

## 작업 흐름

### 1. 압축 해제

모든 CMD 파일은 Compile LZ 압축 (`compile_lz.decompress()`).

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

**대화 블록 패턴**:
```
6b 00 [선택: 80 77 00 등 캐릭터 코드]
SJIS 텍스트 [72 01 줄바꿈 | 73 30 페이지 | 76 1a 클리어]
...
6b 00  ← 다음 블록 시작 (이 블록 종료)
```

`6b 00` 이후 30바이트 이내에 SJIS가 없으면 바이너리 이벤트 블록 → 스킵 (`_DIALOG_LOOKAHEAD = 30`).

**아이템 포맷 (MESSAGE.CMD)**:

```
62 00 0f 03  SJIS이름  64 XX  SJIS스탯  72 01  SJIS설명줄  72 01  ...
62 00 0f 03  (다음 항목)
```

- `62 00` = 항목 시작 프리픽스
- `0f 03` = 아이템 데이터 시작 마커
- `64 XX (XX≠02)` → 스탯 (소비MP/SP, 공격력 등)
- `64 02` → 설명 줄 시작
- 스탯 이후 첫 `72 01` = 설명 줄로 전환

**스크립트 파일 목록**:

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

풍광전과 동일하게 `charmap.json` 기반(`encode_korean_kitan`)으로 한글 반각 인코딩.  
상세 사용법·전체 반각 매핑(한글 71+2자 / ASCII 94자)은 `tools/NOTES.md` "반각 한글" 섹션 참조.

**반각 접미사 보존**:  
`battle` 태그 스킬명 일부는 `[SJIS 이름][반각 코스트 0x85XX…]`가 구분자 없이 붙어 있음.  
원본 데이터는 `大撃剣` + `85 47 85 72 85 6F 85 50 85 4F 85 48`(`(SP10)` 반각) 처럼 저장됨.  
파서는 `0x85`를 만나면 추출을 중단해 jp에는 스킬명만 담고 jp_len도 그 길이까지만 설정.  
인서터는 단순히 jp_len 범위만 패치하므로 반각 영역은 자연스레 보존됨.

**반각(반각 카나) 폭 자동 trim**

원본이 `0x85XX` 반각로 저장된 텍스트(예: `リフレッシュの水` = 반각 6자 + 전각 2자 = **시각 폭 5**)는  
원본 게임이 좁은 슬롯에 맞추려 반각으로 우회한 것. KR을 그냥 전각 한글로 번역하면(`리프레시워터` = 6자, 시각 폭 6) 슬롯 픽셀 폭을 초과해서  
다음 텍스트 위치를 밀어내거나 그리기 잔상이 남는 문제 발생.

해결: 아래 "반각 한글 마커" 섹션의 `/X` 시퀀스로 동일하게 반각 처리 (예: `/리/프/레/시워터`).

인서터(`_compute_visual_width` + `_truncate_overwidth_kr`)는 안전망으로 동작:
- JP 바이트를 스캔해서 시각 폭 계산 (반각·반각 ASCII = 0.5, 전각 SJIS = 1.0)
- KR이 그 폭을 넘으면 char 단위로 trim 후 경고 출력 → 번역자에게 `/X` 적용 필요 신호

**반각 한글 마커 (적용 완료)**

KR 텍스트에서 `/X` 형태로 시작하는 두 글자는 **반각 한글**로 해석.  
인서터(`encode_korean_kitan`)가 `/리` → `0x85A4` 식으로 인코딩, 폭 계산도 0.5로 처리.

**초기 시도**(0x95XX 한자 영역)는 게임 렌더러가 전각으로 출력해 실패.  
**현재 적용**: PC-98 폰트의 반각 카나 영역 `0x85A4~0x85EC`에 한글 글리프 추가.  
이쪽은 게임이 dot-by-dot 반각으로 출력하므로 정상 동작.

희담에서 `리프레시워터` 류 41건 entry가 `/리/프/레/시워터` 형태로 변환됨.

### 4. 파싱

`tools/kitan_parser.py` — 위 포맷을 파싱해 `translation/kitan/translation.json` 생성.

```bash
python3 tools/kitan_parser.py original/kitan/unpacked
```

출력 JSON 구조:
```json
{
  "dialogs": [...],   // CMD 파일 대화·메뉴 (파일별 그룹)
  "gsovl":  [...],   // GS.OVL 고정 오프셋 문자열 (배틀 메뉴·UI 라벨·캐릭터 이름)
  "items":  [...]    // MESSAGE.CMD 아이템 DB
}
```

**추출 패턴 전체**:

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

상점 인벤토리 영역(SC1A/3A/4A/6D/7A의 `64 00 96 48 [name] 64 XX [price] 72 01 [desc] ...`)은 `extract_dialogs`가 통째로 처리. `64 00`이 4바이트 portrait opcode로 96 48까지 스킵하므로 자연스럽게 `name` 부터 잡힘.
| `0f 03` 블록 | MESSAGE.CMD 전용 | 아이템 DB (이름/스탯/설명) | `extract_items` |

MESSAGE.CMD는 `extract_dialogs`를 `_MSG_DIALOG_START`(0x1290) 이전 영역만 스캔 — 스토리 대화 영역에서 중복 추출 방지.

**6d 08 연속 항목 주의사항**

`6d 08 [SJIS] 65` 패턴에서 `65`는 1바이트 종결자 (2바이트 오피코드 아님).  
다음 항목의 `6d 08`이 `65` 직후에 바로 이어지므로 `j += 1`로 처리해야 연속 항목 누락 없음.  
(`j += 2`로 처리하면 홀수 번째 항목만 추출됨 — 수정 완료)

**extract_dialogs 제어코드 처리 메모**

- `64 00` = portrait/캐릭터 코드 + 2바이트 인수 = **총 4바이트 오피코드**  
  인수 바이트가 우연히 SJIS를 형성해 텍스트에 붙는 것 방지 → 4바이트 스킵 + 텍스트 리셋
- 비-SJIS 바이트 = 텍스트 **리셋** (이벤트 데이터 내 우연한 SJIS 쌍 누적 방지)
- `6d 04 [SJIS] 6d 00 65` 형식: `6d 00` 이 flush 트리거 → 텍스트 정상 추출됨

**extract_message_dialog 포맷 메모**

`00 02` 프리픽스는 섹션 최초(0x128E)에만 붙고, 이후 블록은 `65` 종료 직후 바로 다음 블록  
시작. 비-SJIS 바이트(반각가나 등)는 리셋 없이 스킵.

### 5. 재삽입

`tools/kitan_inserter.py` — CMD 파일 패치 후 FDI에 직접 삽입 (본편, system+data 디스크 대상).  
`tools/kitan_demo_inserter.py` — 동일 구조를 오프닝(demo+data 디스크)에 적용하는 대응 스크립트.

```bash
# 1. CMD 빌드 (build/kitan/ 생성)
#    인수는 게임 파일 소스 디렉토리 (system/data 디스크 파일이 모두 여기 있음)
python3 tools/kitan_inserter.py original/kitan/unpacked

# 2. FDI 패치 — system·data 양쪽 FDI에 각각 호출 (editor.py "번들 생성"이 내부적으로 수행)
#    patch_fdi()가 FDI 타입을 자동 감지해 해당 인덱스 맵 적용
from kitan_inserter import patch_fdi
result, patched = patch_fdi(fdi_data_system, 'build/kitan')  # → DISK_B_INDEX 파일 삽입
result, patched = patch_fdi(fdi_data_data,   'build/kitan')  # → DISK_C_INDEX 파일 삽입
```

**구조**:

- **텍스트 길이**: 원본 바이트 크기 고정 — 초과 시 잘림 경고 후 truncate
- **FDI 삽입**: DISK_B.DAT 오프셋 테이블로 슬롯 위치·크기 계산 → 범위 내 overwrite
  - 파일 크기 불변 → 오프셋 테이블 갱신 불필요
  - 슬롯보다 크면 skipping (초과 텍스트 잘려야 함)
- **DISK_B_INDEX**: 대부분의 CMD는 `kitan-system.fdi` 내 DISK_B.DAT (base `0x14400`)
- **DISK_C_INDEX**: `PARTY7.CMD`만 `kitan-data.fdi` (base `0x3C00`)

**패치 대상 분류 (tag)**:

| tag | 내용 |
|-----|------|
| `battle` | 배틀 메뉴 (공격·마법·특기·도망·아이템, 스킬명) |
| `status` | 상태 표시 라벨 (精神力·魔力·特技·魔法·正常·毒·気絶) |
| `name` | 캐릭터 이름 — 스테이터스 창(0x5638) + HUD 상시 표시(0x58A8) 두 곳에 각각 |
| `stat` | 스탯 창 라벨 (レベル·生命力·経験値·攻撃力·素早さ·防御力·武器·防具·道具·所持金) |
| `misc` | 기타 (残金·誰が持つ？) |

**패치 방식** (압축 해제 후):  
KR 바이트로 교체 후 남은 슬롯은 `00 F4`로 채움. 슬롯 크기 = 원본 SJIS 바이트 수.  
초과 시 경고 출력 후 건너뜀.

**제외 태그(`tag == 'ignore'`)**:  
파서가 비텍스트 바이트를 SJIS로 오인하는 경우(예: `'＄喪'`, `'殳舩'` 같은 깨진 한자열)를 위해,  
인서터는 `ignore` 태그 항목을 항상 패치 대상에서 제외함.  
에디터에서도 `ignore` 적용 시 KR이 자동으로 비워져 잘못된 패치 사고를 방지.

**GS.OVL 패치**:

`GS.OVL`은 배틀 메뉴·UI 라벨·캐릭터 이름 등 게임 전반의 UI 문자열을 담음.  
`kitan_parser.py`가 고정 오프셋에서 문자열을 추출해 `translation.json`의 `gsovl` 섹션에 저장.  
`kitan_inserter.py`가 `translation['gsovl']`을 읽어 패치 후 `build/kitan/GS.OVL` 출력.  
GS.OVL은 DISK_B_INDEX 0번 — `patch_fdi` 호출 시 system FDI에 자동 삽입.

> **주의 — 고정 오프셋 누락 = 무번역**: gsovl 추출은 `_GSOVL_OFFSETS` 하드코딩 테이블에만
> 의존한다(스캔 아님). 테이블에 없는 오프셋의 문자열은 추출조차 안 되어 게임에 일본어
> 원문이 그대로 노출된다. 인서터는 json 기반이라, 누락 라벨은 파서 재실행 없이
> translation.json `gsovl`에 `{offset, tag, jp, jp_len, kr}` 항목을 직접 추가하면 패치된다
> (단, 다음 파서 재실행 시 보존되도록 `_GSOVL_OFFSETS`에도 같은 오프셋을 추가해 둘 것).
> 실제 사례: 전투 중 상태이상 라벨 `毒`(0x45AF)·`気絶`(0x45BC)과 메뉴 상태목록의
> `毒`(0x582B)이 테이블에서 빠져 무번역으로 남아 있었음 → 3건 추가로 해결.

### 6. 빌드

`editor.py`의 빌드 버튼이 「인서터 → FDI 패치 → `file_packager.py` 번들 교체」를 오케스트레이션 — 풍광전/쾌도전과 동일 구조.

---

## 디버깅 — 패치가 게임 그래픽/로직을 깨뜨릴 때

번역 패치 적용 후 원본에 없던 시각적 깨짐이 보이면, 다음 절차로 원인 파일·entry를 좁힌다.

### 1. 원본 FDI 확보

희담 원본 FDI는 커밋 `9ee4c97` 시점에 추가됨. 임시 디렉토리에 추출:

```bash
mkdir -p /tmp/kitan-orig
git show 9ee4c97:emulator/rom/kitan-system.fdi > /tmp/kitan-orig/kitan-system.fdi
git show 9ee4c97:emulator/rom/kitan-data.fdi   > /tmp/kitan-orig/kitan-data.fdi
```

네이티브 NP2kai에 띄워서 원본에서 정상인지 먼저 확인.

### 2. 파일 단위 이진 탐색

`build/kitan/`에서 한두 파일만 골라 `patch_fdi`로 임시 FDI 생성:

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

### 3. CMD 파일 내 offset 범위 분할

특정 CMD가 범인이면 entry를 offset 절반씩 나눠 적용해 좁힌다.  
`collect_replacements()` 결과(`[(offset, old, new), ...]`)를 offset으로 정렬 후 분할,  
`patch_data()` + `compress()`로 재빌드한 뒤 `patch_fdi`로 슬롯에 삽입.

수십 줄 짜리 1회용 스크립트로 충분. 절반씩 줄여 5~7회 안에 단일 entry까지 좁혀짐.

### 4. 흔한 원인 패턴

- **fill-bar 오용**: 메뉴 텍스트가 엉뚱한 entry에 채워져 폭주한 KR이 비텍스트 영역 침범 — `ignore` 태그 + KR 비우기
- **파서 오탐**: 바이너리 영역을 SJIS로 잘못 해석한 entry (jp가 깨진 한자, jp_len이 비정상적으로 큼)
- **반각 경계**: GS.OVL 등 텍스트 + 반각 혼합 영역에서 반각를 덮어쓰는 경우 — 파서가 `0x85` 경계에서 중단해야 함

---

## 그래픽 포맷 (데모 화면)

### 공통 사항

- 해상도: 640×400, 16색 (bitplane 방식)
- 각 bitplane: 640×400 / 8 = **32000 bytes**
- LZ 압축: `compile_lz.decompress()` 공통 알고리즘 사용
- 픽셀 인덱스 조합: `idx = B | (R<<1) | (G<<2) | (E<<3)`  
  (B=A800, R=B000, G=B800, E=E000)

### 타이틀 화면 (TITLE0-3.DAT)

파일 하나 = bitplane 하나. 4개가 독립적으로 압축.

```
TITLE0.DAT → A800 (B plane), 해제 시 32000 bytes
TITLE1.DAT → B000 (R plane)
TITLE2.DAT → B800 (G plane)
TITLE3.DAT → E000 (E plane)
```

팔레트: SP1.COM @0x0b50  
형식: 4-byte 엔트리 `[idx, R, G, B]`, 값 범위 0-15 (×17 → 0-255)

```
[0]#553300  [1]#000000  [2]#002222  [3]#224444
[4]#446666  [5]#668888  [6]#99aaaa  [7]#551122
[8]#991111  [9]#bb2200  [A]#ee4422  [B]#885500
[C]#bb8833  [D]#ddbb77  [E]#ffffbb  [F]#ffffff
```

### CNS 형식 A — KIRINASI.CNS (확인 완료)

4개의 null-terminated LZ 스트림이 연속으로 이어진 구조.  
각 스트림 해제 시 32000 bytes = 1 bitplane.  
순서: [B, R, G, E].

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

### CNS 형식 B — DATA01C-DATA10C.CNS (미해독)

단일 LZ 스트림. 해제 크기가 파일마다 다르며 32000의 배수가 아님.  
bitplane 배치 방식 미확인 — 역공학 중단, 에뮬 방식으로 전환.

### 참고: SP1.COM 구조 (부분)

```
0x0b50    타이틀 화면 팔레트 (16 × 4-byte)
0x3883    CNS 파일명 테이블
0x7618    CNS 파일명 확장 테이블
0x23B0    LZ 디컴프레서 (ES:DI = VRAM 직접 쓰기)
```
