# 웹 에뮬레이터 기술 노트

## 빌드 구성 (NP2kai + Emscripten)

### 핵심 CMake 설정 (`NP2kai/CMakeLists.txt`)

| 플래그 | 이유 |
|--------|------|
| `ASYNCIFY=1` | 메인 루프가 blocking — 없으면 게임 실행 불가 |
| `EMULATE_FUNCTION_POINTER_CASTS=1` | 함수 포인터 타입 불일치 방어 |
| `USE_EMULARITY_NP2DIR` | BIOS 경로를 `/emulator/np2kai/`로 고정 |
| `EMSCRIPTEN=1` (CMAKE_C_FLAGS) | `np2.c`의 `#ifdef EMSCRIPTEN` 분기 활성화 |
| `EXPORTED_RUNTIME_METHODS=[FS]` | JS에서 `Module.FS` 접근 (세이브 지속성용) |
| `--preload-file bios@/emulator/np2kai` | BIOS 번들 |
| `--preload-file rom@/rom` | 게임 디스크 이미지 번들 |

### 소스 패치 (`NP2kai/embed/menubase/menubase.c`)

```c
void menubase_modalproc(void) {
#if defined(EMSCRIPTEN) && !defined(__LIBRETRO__)
  /* 브라우저에서는 blocking modal 루프 불가 — 즉시 반환 */
  (void)menuvram;
#else
  while((taskmng_sleep(5)) && (menuvram != NULL)) {
  }
#endif
}
```

---

## 세이브 지속성 — 조사 결과 (2026-05-17)

### 세이브 데이터 위치

인게임 세이브 → **FDI 파일 자체**에 기록됨 (`/rom/hukyou_kr.fdi`).

`fdd_xdf.c`의 쓰기 경로:
```
fdd_write_xdf() → file_open(fname) → file_write() → file_close()
```
섹터 단위 open/write/close 반복 — MEMFS에 반영됨.

### 문제: MEMFS 파일이 read-only로 마운트됨

`--preload-file`로 번들된 파일은 쓰기 권한 없이 MEMFS에 올라감.  
`dosio.c`의 `file_attr()`가 `S_IWUSR` 비트 확인 → read-only로 판정 → 쓰기 무시.

**확인 방법**: 게임 실행 후 `Module.FS.readFile('/rom/hukyou_kr.fdi').reduce((a,b)=>a+b,0)` 세이브 전후 비교 → 값 다름 (chmod 후).

**픽스**: 에뮬레이터 시작 시 `Module.FS.chmod('/rom/hukyou_kr.fdi', 0o666)` 호출.

### 다음 구현 작업

1. **`index.html` preRun에 chmod 추가**
   ```js
   preRun: [function() {
     Module.FS.chmod('/rom/hukyou_kr.fdi', 0o666);
   }]
   ```

2. **IndexedDB 세이브 지속성 구현**
   - localStorage는 용량 부족 (FDI base64 시 5MB 초과 가능)
   - IndexedDB 직접 사용: 바이너리 그대로 저장, 용량 제한 없음
   - 저장: 인게임 세이브 감지 or 주기적으로 `Module.FS.readFile()` → IDB에 기록
   - 복원: 페이지 로드 시 IDB에서 읽어 `Module.FS.writeFile()` 후 에뮬레이터 시작

3. **다중 디스크 대응**

   | 타이틀 | 이미지 | 크기 |
   |--------|--------|------|
   | 환세풍광전 | FDI × 1 | 1.3MB |
   | 환세포물장 | HDI × 1 | 3.1MB |
   | 환세희담 | FDI × 3 | 1.3MB × 3 |

   각 타이틀별로 IDB 키 분리하여 저장.

### 세이브 감지 방법 (미결정)

- **주기적 폴링**: 5~10초마다 파일 체크섬 비교 → 변경 시 IDB 저장
- **수동 버튼**: "세이브 백업" 버튼 → 즉시 IDB 저장
- 두 방식 병행 추천 (폴링 + 수동 버튼 안전망)

---

## 타이틀 확장 계획

현재 환세풍광전 단일 타이틀. 향후 확장 시:
- URL 파라미터 or 선택 화면으로 타이틀 전환
- 각 타이틀 FDI/HDI를 `rom/` 아래 배치
- IDB 키를 타이틀명으로 분리

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
| favicon.ico 404 | 무해, 무시 가능 |
| 세이브 지속성 미구현 | 다음 작업 |
| 모바일 대응 미구현 | 향후 예정 |
