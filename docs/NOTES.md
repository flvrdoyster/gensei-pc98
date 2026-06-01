# 웹 에뮬레이터 기술 노트

NP2kai를 Emscripten으로 브라우저에 포팅한 구현 노트.  
같은 방식으로 PC-98 에뮬레이터(또는 유사한 네이티브 에뮬레이터)를 웹에 올리려는 경우 참고.

---

## 구조 개요

WASM은 전 게임 공유, JS와 data는 게임별 분리:

| 파일 | 역할 |
|------|------|
| `emnp2kai_sdl2.wasm` | NP2kai 바이너리 (공유) |
| `<title>.js` | 게임별 JS 로더 (메타데이터 포함) |
| `<title>.data` | 게임별 BIOS · ROM 번들 |

예: `hukyou.js` + `hukyou.data`, `kitan.js` + `kitan.data`.  
JS 내부에 `loadPackage({files:[...], remote_package_size:N})`로 번들 메타데이터가 하드코딩됨.  
WASM은 NP2kai 소스 변경 시만 재빌드, JS/data는 ROM이나 BIOS 변경 시 재생성.

공통 페이지 자산(전 페이지가 같은 방식으로 include):

| 파일 | 역할 |
|------|------|
| `style.css` | 공통 스타일 |
| `audio.js` | 뮤트·오디오 resume (`btn-mute` 자동 연결) |
| `gamepad.js` | 가상 게임패드 |
| `version.js` | 사이트 통합 버전 단일 소스. footer.js가 그린 푸터 마지막 줄(`.footer-credits`)에 `· vX.Y.Z` 주입. 배포 버전은 이 파일의 `VERSION` 한 곳만 수정 |

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

### data 번들 (게임별 분리)

게임마다 별도 data 파일 생성. 임시 디렉토리에 해당 게임의 bios + ROM만 모아서 번들링:

```bash
# 예: 풍광전 번들 생성
mkdir -p /tmp/bundle/bios /tmp/bundle/rom
cp emulator/bios/bios.rom emulator/bios/font.bmp /tmp/bundle/bios/
cp emulator/rom/hukyou_kr.fdi /tmp/bundle/rom/

source <emsdk_path>/emsdk_env.sh
cd /tmp/bundle
python3 $(em-config EMSCRIPTEN_ROOT)/tools/file_packager.py \
  <project_root>/emulator/hukyou.data \
  --js-output=/tmp/loader.js \
  --preload bios@/emulator/np2kai \
  --preload rom@/rom
rm /tmp/loader.js
```

생성 후 `loader.js`에서 메타데이터를 추출하여 게임별 JS의 `loadPackage(...)` 부분을 교체:

```bash
# 기존 emnp2kai_sdl2.js를 복사하고 파일명 + 메타데이터를 sed로 교체
cp emnp2kai_sdl2.js hukyou.js
sed -i '' -e 's/emnp2kai_sdl2.data/hukyou.data/g' \
          -e 's/datafile_emnp2kai_sdl2.data/datafile_hukyou.data/g' hukyou.js
# loadPackage({files:[...]}) 부분도 loader.js에서 추출한 메타데이터로 교체
```

**폰트 분기**: 한글화 완료 타이틀은 `font.bmp`(한글), 미완료 타이틀은 `font_jp.bmp`를 `font.bmp`로 복사하여 번들링.

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

DB `gensei-saves` / store `disks`. 키는 **FDI 파일명**(`hukyou_kr.fdi`, `kitan-system.fdi` 등)이라 게임·디스크별로 분리 저장됨.  
다중 디스크 게임(희담: system+data)은 디스크마다 체크섬을 따로 비교해 **변경된 디스크만** 기록한다. (희담 데모/오프닝은 세이브 대상 아님)

---

## 모바일/태블릿 대응

### 오디오 (`audio.js`)

- `Module.SDL2.audioContext`의 `suspend()/resume()`으로 뮤트 구현
- `visibilitychange` · `click` · `keydown`에서 오디오 resume (뮤트 상태면 스킵)
- 뮤트 버튼(`btn-mute`)은 에뮬레이션 시작 전에는 숨김 — AudioContext 생성 감지 시 표시

### 가상 게임패드 (`gamepad.js`)

- 방향키(D-pad) 4개 + ESC/Enter 2개 = 총 6키
- 터치 이벤트 → `KeyboardEvent` 변환, canvas 엘리먼트에 dispatch
- 단일 터치만 처리 (PC-98 게임이라 멀티터치 불필요)
- 3D 키캡 스타일 (CSS `border-bottom` + `translateY` active 효과)
- 키 아이콘은 RasterForge 픽셀 폰트 기반 SVG (`img/key-*.svg`)
- 자동 활성화: `?gamepad` URL 파라미터 또는 모바일(`ontouchstart` + `innerWidth <= 680`)
- 태블릿 등 터치 기기에서는 상단바에 게임패드 활성화 버튼 표시 (`btn-gamepad`). 누르면 `?gamepad` 파라미터를 `history.replaceState`로 URL에 추가 (리로드 없음)
- 활성화 시 `position: fixed; bottom: 0`으로 화면 하단 고정

### 버튼 표시 규칙 (CSS 미디어쿼리)

| 버튼 | PC (hover+fine) | 터치 기기 | 게임패드 활성 시 |
|------|-----------------|-----------|-----------------|
| 게임패드 (`btn-gamepad`) | 숨김 | 표시 | 숨김 |
| 전체화면 (`btn-fullscreen`) | 표시 | 숨김 | — |
| 뮤트 (`btn-mute`) | 에뮬레이션 시작 후 표시 | 동일 | 동일 |

### 세이브 복원 타이밍

`preRun`에서 `FS.stat()`으로 ROM 파일 마운트 여부를 폴링 (10ms 간격, 최대 2초).  
첫 페이지 로드 시 .data 파일 처리가 느릴 수 있어 단순 `setTimeout(0)`으로는 부족.  
타임아웃 시 세이브 없이 원본으로 시작.

### 제한 사항

- 터치 기기에서 전체화면 버튼 숨김 (CSS `@media (hover: none), (pointer: coarse)`)
- 풀스크린 시 게임패드는 canvas-wrap 바깥이므로 표시 안 됨 (의도된 동작)

---

## 새 타이틀 추가

`hukyou.html` 복사 후 수정:

| 항목 | 내용 |
|------|------|
| `DISK` / `DISKS` | ROM 경로 (`/rom/<title>.fdi`) |
| `IDB_KEY` | 타이틀별 세이브 분리 키 |
| `document.title` | 타이틀명 |
| `logo` img src/height | `img/logo-<title>.png`, 높이 기준 (풍광전 42px, 희담 54px) |
| `s.src` | `<title>.js` |

멀티 디스크: `Module.arguments`에 FDI 경로를 순서대로, preRun에서 모두 chmod.  
단, **런타임 디스크 교체는 불가** — NP2kai가 내부 메모리에 디스크를 캐싱하므로 `FS.writeFile()`이 무시됨.

번들 생성: 게임별 bios + ROM으로 `<title>.data` 생성, `emnp2kai_sdl2.js` 복사 후 `<title>.js`로 메타데이터 교체.

`index.html`: 해당 항목 `class="unavailable"` 제거, `<a href>` 추가, badge → `done`.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
| 런타임 디스크 교체 불가 | NP2kai가 디스크를 내부 캐싱. `diskdrv_setfdd()` 등의 export가 필요 |
