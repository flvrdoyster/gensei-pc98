# 웹 에뮬레이터 기술 노트

## 빌드 구성 (NP2kai + Emscripten)

### ROM/BIOS 변경 후 데이터 번들 재생성

`emnp2kai_sdl2.data`는 Emscripten `file_packager.py`로 생성된 번들.  
`rom/` 또는 `bios/` 파일 변경 시 반드시 재생성해야 브라우저에 반영됨.

```bash
# emulator/ 디렉토리에서 실행
# 시스템 python3은 3.9라 emsdk 내장 python3.13 사용
/Users/oyster/GitHub/emsdk/python/3.13.3_64bit/bin/python3.13 \
  /Users/oyster/GitHub/emsdk/upstream/emscripten/tools/file_packager.py \
  emnp2kai_sdl2.data \
  --js-output=emnp2kai_sdl2.data.js \
  --preload bios@/emulator/np2kai \
  --preload rom@/rom
rm emnp2kai_sdl2.data.js  # hukyou.html은 이 파일을 사용하지 않음
```

`emnp2kai_sdl2.js` (WASM 로더)는 수정 불필요 — `.data`만 교체하면 됨.

---

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

## 세이브 지속성 — 구현 완료 (2026-05-17)

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

### 구현 내용 (`index.html`)

#### chmod — preRun 타이밍 문제

단순히 `preRun`에서 `Module.FS.chmod()` 호출 시 `ErrnoError` 발생.  
`--preload-file` 파일은 preRun 시작 시점에 아직 MEMFS에 마운트되지 않기 때문.

**해결**: `addRunDependency` + `setTimeout(0)` 패턴으로 마운트 완료까지 대기:

```js
preRun: [function() {
  Module.addRunDependency('disk-setup');
  setTimeout(function() {
    try {
      Module.FS.chmod(DISK, 0o666);
      if (savedDisk) {
        Module.FS.writeFile(DISK, new Uint8Array(savedDisk));
      }
    } catch(e) { ... }
    Module.removeRunDependency('disk-setup');
  }, 0);
}]
```

#### IndexedDB 세이브 지속성

- localStorage는 용량 부족 (FDI base64 시 5MB 초과 가능) → IndexedDB 선택
- 바이너리(`ArrayBuffer`) 그대로 저장 — base64 변환 불필요
- **저장**: 10초마다 FDI 바이트 합 체크섬 비교 → 변경 시에만 IDB 기록
- **복원**: 페이지 로드 시 IDB에서 읽어 `Module.FS.writeFile()` → chmod → 에뮬레이터 시작
- `postRun`에서 기준 체크섬 설정 + 폴링 시작
- **검증 완료**: 인게임 세이브 → 페이지 새로고침 → 세이브 복원 확인

#### 다중 디스크 확장 (향후)

| 타이틀 | 이미지 | 크기 |
|--------|--------|------|
| 환세풍광전 | FDI × 1 | 1.3MB |
| 환세포물장 | HDI × 1 | 3.1MB |
| 환세희담 | FDI × 3 | 1.3MB × 3 |

IDB 키를 타이틀명으로 분리하여 저장.

---

## 모바일 대응 — 구현 완료 (2026-05-17)

### 구조

- **세로(portrait) 전용** — 가로 모드 대응 없음
- 가상 게임패드는 캔버스 **아래** 별도 영역 (오버레이 아님)
- 데스크톱에 영향 없음 — 모든 모바일 코드는 터치 기기 감지 시에만 활성화

### 모바일 감지

`('ontouchstart' in window) && window.innerWidth <= 680` → `body.mobile-active` 클래스 추가.  
`?gamepad` URL 파라미터로 데스크톱에서도 강제 활성화 가능.

### 가상 게임패드 (`gamepad.js`)

- 방향키(D-pad) 4개 + ESC/Enter 2개 = 총 6키
- 터치 이벤트 → `KeyboardEvent` 변환, canvas 엘리먼트에 dispatch
- 단일 터치만 처리 (PC-98 게임이라 멀티터치 불필요)
- 3D 키캡 스타일 (CSS `border-bottom` + `translateY` active 효과)
- 키 아이콘은 RasterForge 픽셀 폰트 기반 SVG (`img/key-*.svg`)
- `Module.SDL2.audioContext` resume 처리 (모바일 오디오 정책 대응)
- `visibilitychange` 감지 → 잠금/탭 전환 복귀 시 다음 터치에서 AudioContext resume

### 세이브 복원 타이밍

`preRun`에서 `FS.stat()`으로 ROM 파일 마운트 여부를 폴링 (10ms 간격, 최대 2초).  
첫 페이지 로드 시 .data 파일 처리가 느릴 수 있어 단순 `setTimeout(0)`으로는 부족.  
타임아웃 시 세이브 없이 원본으로 시작.

### 제한 사항

- iOS는 Fullscreen API 미지원 → 모바일에서 전체화면 버튼 숨김
- 풀스크린 시 게임패드는 canvas-wrap 바깥이므로 표시 안 됨 (의도된 동작)

---

## 새 타이틀 추가 절차

풍광전(`hukyou`)을 기준으로 한 체크리스트. 쾌도전(`kaitou`) 등 추가 시 그대로 따를 것.

### 1. ROM 파일 배치

```
emulator/rom/kaitou_kr.fdi   # 번역 삽입된 FDI
```

멀티 디스크라면 `kaitou_kr_1.fdi`, `kaitou_kr_2.fdi` 등으로 분리.

### 2. `emnp2kai_sdl2.data` 재생성

새 ROM을 번들에 포함시켜야 함. [ROM/BIOS 변경 후 데이터 번들 재생성](#rombioscmd) 섹션 참조.

### 3. 게임 HTML 페이지 작성

`hukyou.html`을 복사해서 `kaitou.html` 생성. 바꿔야 할 부분:

| 항목 | hukyou | kaitou |
|------|--------|--------|
| `DISK` | `/rom/hukyou_kr.fdi` | `/rom/kaitou_kr.fdi` |
| `IDB_KEY` | `hukyou_kr.fdi` | `kaitou_kr.fdi` |
| `document.title` | `환세풍광전 웹 버전 : atah.io` | `환세쾌도전 웹 버전 : atah.io` |
| `<title>` 태그 | 동일 | 동일하게 |
| `logo` img src | `img/logo-hukyou.png` | `img/logo-kaitou.png` |
| `Module.arguments` | `[DISK]` | `[DISK]` (동일) |

`IDB_NAME`(`gensei-saves`)과 `IDB_STORE`(`disks`)는 공유 — 변경 불필요.  
세이브는 `IDB_KEY`(파일명)로 타이틀별 분리됨.

멀티 디스크 시: `DISK2`, `DISK3` 상수 추가 + `Module.arguments`에 순서대로 추가. preRun에서 두 파일 모두 chmod + IDB 복원.

### 4. `index.html` 업데이트

`kaitou` 항목의 `class="unavailable"` 제거, `<a href="kaitou.html">` 추가, badge를 `done`으로 변경.

### 5. 로고 이미지

`img/logo-kaitou.png` — 타이틀 로고 이미지 배치 필요.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
| favicon.ico 404 | 무해, 무시 가능 |
| 세이브 지속성 미구현 | ✅ 완료 (IndexedDB) |
| 모바일 대응 | ✅ 완료 (가상 게임패드) |
