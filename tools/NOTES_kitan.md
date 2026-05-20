# 환세희담 역공학 노트

**대상**: 환세희담 / 幻世喜譚 (Compile, 1995, PC-98)  
**상태**: 에뮬레이터 탑재 완료 (system + data 디스크), demo 분석 부분 완료  
**도구**: `compile_lz.py` (LZ 해제 공통), `pc98disk.py` (FDI 파일 추출)

---

## 디스크 구성

```
original/kitan/
  data/     데이터 디스크에서 추출한 CMD·CNS·DAT 등 게임 파일
  system/   시스템 디스크에서 추출한 파일
  demo/     데모 디스크에서 추출한 파일
```

에뮬레이터(`emulator/kitan.html`)는 system + data 디스크만 사용.  
demo 디스크는 별도로 처리 예정 (에뮬 탑재 + 한글화).

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

`6b 00` 이후 5바이트 이내에 SJIS가 없으면 바이너리 이벤트 블록 → 스킵.

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
BTL_PC.CMD   전투 대사
ENDING.CMD   엔딩
MESSAGE.CMD  아이템 DB
```

---

## 파서

`tools/kitan_parser.py` — 위 포맷을 파싱해 `translation/kitan/translation.json` 생성.

```bash
python3 tools/kitan_parser.py original/kitan/data
```

출력 JSON 구조는 `translation/hukyou/translation.json`과 동일 (ui 섹션 없음).

---

## 한국어판 텍스트 추출 (`kitan_kr_import.py`)

`original/kitan_kr/`의 CMD 파일에서 한국어 텍스트를 추출해 `translation.json`의 `kr` 필드에 채움.
JP 블록 인덱스 + 줄 인덱스 기준으로 1:1 매핑 (참고용).

```bash
python3 tools/kitan_kr_import.py original/kitan_kr translation/kitan/translation.json
```

### KR 인코딩 (역공학)

`MDRSYSF.COM` (폰트 드라이버 TSR) 분석으로 확인.

**리드 바이트 판정**: 0x81–0x9F (SJIS 1바이트 범위 동일)  
**트레일 바이트**: 0x40–0xFC (0x7F 포함, SJIS와 달리 0x7F 건너뛰지 않음 → 189개/행)

**glyph 인덱스 계산 (SJIS 범위 경로)**:
```python
glyph = (lead - 0x81) * 189 + (trail - 0x40)
```

**glyph → EUC-KR 변환 (EUC-KR 경로 역산)**:
```python
euc_lead  = 0xA1 + glyph // 96
euc_trail = 0xA0 + glyph % 96
char = bytes([euc_lead, euc_trail]).decode('euc_kr')
```

두 경로(SJIS 범위 / EUC-KR)가 동일한 glyph index 공간을 공유하므로, SJIS 범위 코드를 EUC-KR로 역산할 수 있음.

`81 41` = glyph 1 = EUC-KR A1A1 = 　(전각 스페이스).  
캐릭터 이름 표시: `82 7E XX XX ... 82 80` = ［이름］ 형태 (전각 대괄호).

### START.CMD 블록 수 불일치

JP: 7블록, KR: 6블록 → 매핑 시 KR 블록 1개 스킵됨 (무시 가능, 나머지는 정상 매핑).

---

## 향후 방향

### 인서터 구현 시 주의

`editor.py`의 빌드 버튼은 인서터에 `original/{TITLE}`을 전달함.  
kitan은 게임 파일이 `original/kitan/data/`에 있으므로, 인서터 구현 시 `editor.py`의 `run_build()`에서 kitan 경우 `/data`를 추가하도록 수정 필요.

### demo 에뮬레이터 탑재

demo를 에뮬레이터로 실행하는 방향:

1. demo FDI에서 텍스트 추출 (SP1.COM + CNS 파일 내 SJIS)
2. 한글 패치 후 demo FDI 재조립
3. `emulator/kitan.html`에 demo 디스크 추가 또는 별도 `kitan-demo.html` 생성

---

## 참고: SP1.COM 구조 (부분)

```
0x0b50    타이틀 화면 팔레트 (16 × 4-byte)
0x3883    CNS 파일명 테이블
0x7618    CNS 파일명 확장 테이블
0x23B0    LZ 디컴프레서 (ES:DI = VRAM 직접 쓰기)
```
