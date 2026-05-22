# 환세희담 역공학 노트

**대상**: 환세희담 / 幻世喜譚 (Compile, 1995, PC-98)  
**상태**: 에뮬레이터 탑재 완료, JP 텍스트 파싱 완료, KR 참고 텍스트 임포트 완료, 인서터·GS.OVL 패치 구현 완료, 번역 진행 중  
**도구**: `compile_lz.py` (LZ 해제 공통), `pc98disk.py` (FDI 파일 추출)

---

## 디스크 구성

```
original/kitan/
  data/     데이터 디스크에서 추출한 CMD·CNS·DAT 등 게임 파일
  system/   시스템 디스크에서 추출한 파일
  demo/     데모 디스크에서 추출한 파일
```

에뮬레이터:
- `emulator/kitan.html` — 게임 플레이 (system + data 디스크)
- `emulator/kitan-opening.html` — 오프닝 (demo + data 디스크)
- ⛁ 버튼으로 두 페이지 간 전환 가능

---

## demo 디스크 파일 구성

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

---

## 그래픽 포맷

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

---

## DISK_B.DAT 아카이브 포맷 (시스템 디스크)

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

---

## CMD 스크립트 포맷

모든 CMD 파일은 Compile LZ 압축 (`compile_lz.decompress()`).

### 대화 제어코드

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

### 아이템 포맷 (MESSAGE.CMD)

```
62 00 0f 03  SJIS이름  64 XX  SJIS스탯  72 01  SJIS설명줄  72 01  ...
62 00 0f 03  (다음 항목)
```

- `62 00` = 항목 시작 프리픽스
- `0f 03` = 아이템 데이터 시작 마커
- `64 XX (XX≠02)` → 스탯 (소비MP/SP, 공격력 등)
- `64 02` → 설명 줄 시작
- 스탯 이후 첫 `72 01` = 설명 줄로 전환

### 스크립트 파일 목록

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

---

## 파서

`tools/kitan_parser.py` — 위 포맷을 파싱해 `translation/kitan/translation.json` 생성.

```bash
python3 tools/kitan_parser.py original/kitan/data
```

출력 JSON 구조:
```json
{
  "dialogs": [...],   // CMD 파일 대화·메뉴 (파일별 그룹)
  "gsovl":  [...],   // GS.OVL 고정 오프셋 문자열 (배틀 메뉴·UI 라벨·캐릭터 이름)
  "items":  [...]    // MESSAGE.CMD 아이템 DB
}
```

---

## 추출 패턴 (구현 완료)

`kitan_parser.py`가 처리하는 패턴 전체:

| 패턴 | 대상 파일 | 내용 | 함수 |
|------|-----------|------|------|
| `6b 00` 블록 | 모든 CMD | 일반 대화 / 메뉴 항목 | `extract_dialogs` |
| `13 00` 포인터 블록 | 모든 CMD | 분기 메뉴 선택지 | `extract_menus` |
| `64 01 [SJIS] 65 XX` | 모든 CMD (MESSAGE 제외) | 세이브/로드, 타이틀 메뉴 등 | `extract_labeled_text` |
| `63 08 [SJIS] 65 XX` | ENDING.CMD 전용 | 제작진 크레딧 | `extract_labeled_text` |
| `6d 08 [SJIS] 65` | PARTY2~7.CMD 전용 | 적/NPC 이름 | `extract_labeled_text` |
| bare SJIS + `65` | SC6A.CMD 전용 | 층수 이름 (`　４階　` 등) | `extract_bare_sjis65` |
| `[SJIS] 72 01 ... 65` | MESSAGE.CMD 전용 | 스토리 대화; 0x1290~EOF 연속 배치 | `extract_message_dialog` |
| `0f 03` 블록 | MESSAGE.CMD 전용 | 아이템 DB (이름/스탯/설명) | `extract_items` |

### 6d 08 연속 항목 주의사항

`6d 08 [SJIS] 65` 패턴에서 `65`는 1바이트 종결자 (2바이트 오피코드 아님).  
다음 항목의 `6d 08`이 `65` 직후에 바로 이어지므로 `j += 1`로 처리해야 연속 항목 누락 없음.  
(`j += 2`로 처리하면 홀수 번째 항목만 추출됨 — 수정 완료)

### extract_dialogs 제어코드 처리 메모

- `64 00` = portrait/캐릭터 코드 + 2바이트 인수 = **총 4바이트 오피코드**  
  인수 바이트가 우연히 SJIS를 형성해 텍스트에 붙는 것 방지 → 4바이트 스킵 + 텍스트 리셋
- 비-SJIS 바이트 = 텍스트 **리셋** (이벤트 데이터 내 우연한 SJIS 쌍 누적 방지)
- `6d 04 [SJIS] 6d 00 65` 형식: `6d 00` 이 flush 트리거 → 텍스트 정상 추출됨

### extract_message_dialog 포맷 메모

`00 02` 프리픽스는 섹션 최초(0x128E)에만 붙고, 이후 블록은 `65` 종료 직후 바로 다음 블록  
시작. 비-SJIS 바이트(반각가나 등)는 리셋 없이 스킵.

---

## 인서터

`tools/kitan_inserter.py` — CMD 파일 패치 후 FDI에 직접 삽입.

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

### 구조

- **한글 인코딩**: 풍광전과 동일하게 `charmap.json` 기반 (`encode_korean_kitan`)
- **텍스트 길이**: 원본 바이트 크기 고정 — 초과 시 잘림 경고 후 truncate
- **FDI 삽입**: DISK_B.DAT 오프셋 테이블로 슬롯 위치·크기 계산 → 범위 내 overwrite
  - 파일 크기 불변 → 오프셋 테이블 갱신 불필요
  - 슬롯보다 크면 skipping (초과 텍스트 잘려야 함)
- **DISK_B_INDEX**: 대부분의 CMD는 `kitan-system.fdi` 내 DISK_B.DAT (base `0x14400`)
- **DISK_C_INDEX**: `PARTY7.CMD`만 `kitan-data.fdi` (base `0x3C00`)

### GS.OVL 패치

`GS.OVL`은 배틀 메뉴·UI 라벨·캐릭터 이름 등 게임 전반의 UI 문자열을 담음.  
`kitan_parser.py`가 고정 오프셋에서 문자열을 추출해 `translation.json`의 `gsovl` 섹션에 저장.  
`kitan_inserter.py`가 `translation['gsovl']`을 읽어 패치 후 `build/kitan/GS.OVL` 출력.  
GS.OVL은 DISK_B_INDEX 0번 — `patch_fdi` 호출 시 system FDI에 자동 삽입.

**패치 대상 분류 (tag)**:

| tag | 내용 |
|-----|------|
| `battle` | 배틀 메뉴 (공격·마법·특기·도망·아이템, 스킬명) |
| `status` | 상태 표시 라벨 (精神力·魔力·特技·魔法·正常·気絶) |
| `name` | 캐릭터 이름 — 스테이터스 창(0x5638) + HUD 상시 표시(0x58A8) 두 곳에 각각 |
| `stat` | 스탯 창 라벨 (レベル·生命力·経験値·攻撃力·素早さ·防御力·武器·防具·道具·所持金) |
| `misc` | 기타 (残金·誰が持つ？) |

**패치 방식** (압축 해제 후):  
KR 바이트로 교체 후 남은 슬롯은 `00 F4`로 채움. 슬롯 크기 = 원본 SJIS 바이트 수.  
초과 시 경고 출력 후 건너뜀.

---

## 향후 방향

### demo 에뮬레이터 탑재 (미완료)

demo를 에뮬레이터로 실행하는 방향:

1. demo FDI에서 텍스트 추출 (SP1.COM + CNS 파일 내 SJIS)
2. 한글 패치 후 demo FDI 재조립
3. `emulator/kitan-opening.html` — 오프닝 전용 페이지 (⛁로 kitan.html과 연결)

---

## 참고: SP1.COM 구조 (부분)

```
0x0b50    타이틀 화면 팔레트 (16 × 4-byte)
0x3883    CNS 파일명 테이블
0x7618    CNS 파일명 확장 테이블
0x23B0    LZ 디컴프레서 (ES:DI = VRAM 직접 쓰기)
```
