# 웹 에뮬레이터 기술 노트

NP2kai를 Emscripten으로 브라우저에 포팅한 구현 노트.  
같은 방식으로 PC-98 에뮬레이터(또는 유사한 네이티브 에뮬레이터)를 웹에 올리려는 경우 참고.

---

## 구조 개요

빌드 결과물은 세 파일:

| 파일 | 역할 |
|------|------|
| `emnp2kai_sdl2.js` | Emscripten 런타임 + WASM 로더 |
| `emnp2kai_sdl2.wasm` | NP2kai 바이너리 |
| `emnp2kai_sdl2.data` | BIOS · ROM 번들 (Emscripten preload) |

JS가 WASM과 `.data`를 fetch해서 초기화. `.data`는 ROM/BIOS 변경 시만 재생성, JS/WASM은 NP2kai 소스 변경 시만 재빌드.

---

## 빌드

### CMake 플래그

| 플래그 | 없으면 |
|--------|--------|
| `ASYNCIFY=1` | 메인 루프가 `emscripten_sleep()`을 쓰지 않아 브라우저가 블로킹 → 실행 불가 |
| `EMULATE_FUNCTION_POINTER_CASTS=1` | C 코드베이스의 함수 포인터 타입 불일치 → WASM 런타임 크래시 |
| `USE_EMULARITY_NP2DIR` | BIOS 경로가 `/np2kai/`가 아닌 다른 경로로 잡혀 BIOS 로드 실패 |
| `EMSCRIPTEN=1` (CMAKE_C_FLAGS) | `np2.c`의 `#ifdef EMSCRIPTEN` 분기 비활성화 → 브라우저 비호환 코드 실행 |
| `EXPORTED_RUNTIME_METHODS=[FS]` | JS에서 `Module.FS`에 접근 불가 → 세이브 지속성 구현 불가 |

### 소스 패치

`embed/menubase/menubase.c`의 `menubase_modalproc()`은 네이티브에서 blocking while 루프로 모달을 처리한다. 브라우저에서는 메인 스레드를 점유하므로 즉시 반환으로 패치:

```c
void menubase_modalproc(void) {
#if defined(EMSCRIPTEN) && !defined(__LIBRETRO__)
  (void)menuvram;
#else
  while((taskmng_sleep(5)) && (menuvram != NULL)) {}
#endif
}
```

### data 번들

BIOS · ROM은 `file_packager.py`로 번들. ROM 파일 변경 시 재생성:

```bash
# emulator/ 디렉토리에서 실행
source <emsdk_path>/emsdk_env.sh
python3 $(em-config EMSCRIPTEN_ROOT)/tools/file_packager.py \
  emnp2kai_sdl2.data \
  --js-output=emnp2kai_sdl2.data.js \
  --preload bios@/emulator/np2kai \
  --preload rom@/rom
rm emnp2kai_sdl2.data.js  # 이 프로젝트에서는 미사용 (로더가 JS에 내장됨)
```

---

## 세이브 지속성

### MEMFS read-only 문제

`--preload-file`로 번들된 파일은 MEMFS에 읽기 전용으로 마운트된다.  
NP2kai는 `dosio.c`의 `file_attr()`에서 `S_IWUSR` 비트를 확인하고 read-only로 판단하면 쓰기를 무시한다.  
→ 에뮬레이터 시작 시 `Module.FS.chmod(DISK, 0o666)` 호출로 해결.

### preRun 타이밍 함정

`preRun` 콜백 시점에는 `--preload-file` 파일이 아직 MEMFS에 마운트되지 않아 `chmod`가 실패한다.  
`addRunDependency`로 에뮬레이터 시작을 지연시키고, `FS.stat()` 폴링으로 마운트 완료를 감지한 후 처리:

```js
Module.addRunDependency('disk-setup');
(function trySetup(attempts) {
  try {
    Module.FS.stat(DISK);
    Module.FS.chmod(DISK, 0o666);
    if (savedDisk) Module.FS.writeFile(DISK, new Uint8Array(savedDisk));
    Module.removeRunDependency('disk-setup');
  } catch(e) {
    if (attempts < 200) setTimeout(() => trySetup(attempts + 1), 10);
    else Module.removeRunDependency('disk-setup');
  }
})(0);
```

### IndexedDB 선택 이유

localStorage는 도메인당 5~10MB 제한이 있어 FDI를 base64로 인코딩하면 초과할 수 있다.  
IndexedDB는 `ArrayBuffer`를 그대로 저장할 수 있고 용량 제한도 크다.

저장 전략: 10초마다 FDI 바이트 합 체크섬 비교 → 변경 시에만 IDB 기록.  
복원: 페이지 로드 시 IDB → `writeFile` → `chmod` → 에뮬레이터 시작.

---

## 모바일 대응

터치 기기 감지(`ontouchstart in window && innerWidth <= 680`)로 `body.mobile-active` 클래스 추가.  
`?gamepad` 파라미터로 데스크톱 강제 활성화 가능.

가상 게임패드(`gamepad.js`): D-pad 4키 + ESC/Enter 2키, 터치 이벤트 → `KeyboardEvent` 변환.  
PC-98 게임 특성상 멀티터치 불필요 — 단일 터치만 처리.

모바일 오디오 정책 대응: 첫 터치 이벤트 및 `visibilitychange` 복귀 시 `Module.SDL2.audioContext.resume()`.

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

### 디스크 관리 (내보내기/가져오기)

상단바 ⛁ 버튼 → 확장 패널에서 내보내기/가져오기 선택.
- **내보내기**: IDB의 FDI를 Blob으로 다운로드
- **가져오기**: `<input type="file">`로 FDI 선택 → IDB에 저장 → 새로고침 후 반영
- 번역 패치 적용 시: 내보내기 → inserter 실행 → 가져오기 순서로 세이브 유지 + 새 번역 적용

### 제한 사항

- iOS는 Fullscreen API 미지원 → 모바일에서 전체화면 버튼 숨김
- 풀스크린 시 게임패드는 canvas-wrap 바깥이므로 표시 안 됨 (의도된 동작)

---

## 새 타이틀 추가

`hukyou.html` 복사 후 수정:

| 항목 | 내용 |
|------|------|
| `DISK` | `/rom/<title>_kr.fdi` |
| `IDB_KEY` | `<title>_kr.fdi` (타이틀별 세이브 분리 키) |
| `<title>` · `document.title` | 타이틀명 |
| `logo` img src | `img/logo-<title>.png` |

멀티 디스크: `DISK2`, `DISK3` 상수 추가, `Module.arguments`에 순서대로, preRun에서 모두 chmod + IDB 복원.

`index.html`: 해당 항목 `class="unavailable"` 제거, `<a href>` 추가, badge → `done`.  
`rom/`에 FDI 추가 후 data 번들 재생성 필수.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
