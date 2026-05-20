# 환세희담 역공학 노트

**대상**: 환세희담 / 幻世喜譚 (Compile, 1995, PC-98)  
**상태**: 에뮬레이터 탑재 완료 (system + data 디스크), demo 분석 부분 완료  
**도구**: `compile_lz.py` (LZ 해제 공통), `pc98disk.py` (FDI 파일 추출)

---

## 디스크 구성

```
original/kitan/
  kitan-demo.fdi    데모 디스크 (FAT12 MEGDOS)
  kitan-system.fdi  시스템 디스크 → emulator/ 번들
  kitan-data.fdi    데이터 디스크 → emulator/ 번들
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

## 향후 방향

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
