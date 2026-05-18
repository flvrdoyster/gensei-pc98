# 웹 에뮬레이터 기술 노트

NP2kai + Emscripten SDL2 빌드. `emnp2kai_sdl2.js` / `.wasm` / `.data` 세 파일로 구성.

---

## 빌드

### NP2kai 초기 빌드

```bash
source <emsdk_path>/emsdk_env.sh
make -C <NP2kai_path>/build_em emnp2kai_sdl2
cp <NP2kai_path>/build_em/emnp2kai_sdl2.{js,wasm} emulator/
```

핵심 CMake 플래그:

| 플래그 | 이유 |
|--------|------|
| `ASYNCIFY=1` | 메인 루프가 blocking |
| `EMULATE_FUNCTION_POINTER_CASTS=1` | 함수 포인터 타입 불일치 방어 |
| `USE_EMULARITY_NP2DIR` | BIOS 경로를 `/emulator/np2kai/`로 고정 |
| `EMSCRIPTEN=1` (CMAKE_C_FLAGS) | `np2.c`의 `#ifdef EMSCRIPTEN` 분기 활성화 |
| `EXPORTED_RUNTIME_METHODS=[FS]` | JS에서 `Module.FS` 접근 (세이브 지속성용) |

NP2kai 소스 패치 (`embed/menubase/menubase.c`) — blocking modal 루프 제거:

```c
void menubase_modalproc(void) {
#if defined(EMSCRIPTEN) && !defined(__LIBRETRO__)
  (void)menuvram;
#else
  while((taskmng_sleep(5)) && (menuvram != NULL)) {}
#endif
}
```

### ROM/BIOS 변경 후 data 번들 재생성

`rom/` 또는 `bios/` 파일 변경 시 `.data`만 재생성 (JS/WASM 수정 불필요):

```bash
# emulator/ 디렉토리에서 실행
source <emsdk_path>/emsdk_env.sh
python3 $(em-config EMSCRIPTEN_ROOT)/tools/file_packager.py \
  emnp2kai_sdl2.data \
  --js-output=emnp2kai_sdl2.data.js \
  --preload bios@/emulator/np2kai \
  --preload rom@/rom
rm emnp2kai_sdl2.data.js
```

---

## 세이브 지속성

인게임 세이브는 FDI 파일 자체에 기록됨 (`fdd_xdf.c` → MEMFS).  
`--preload-file`로 번들된 파일은 read-only로 마운트되므로, 시작 시 `chmod(0o666)` 필요.

`preRun` 시점엔 파일이 아직 MEMFS에 없으므로 `addRunDependency` + `FS.stat()` 폴링으로 마운트 완료 후 처리:

```js
preRun: [function() {
  Module.addRunDependency('disk-setup');
  var attempts = 0;
  function trySetup() {
    try {
      Module.FS.stat(DISK);
      Module.FS.chmod(DISK, 0o666);
      if (savedDisk) Module.FS.writeFile(DISK, new Uint8Array(savedDisk));
      Module.removeRunDependency('disk-setup');
    } catch(e) {
      if (++attempts < 200) setTimeout(trySetup, 10);
      else Module.removeRunDependency('disk-setup');
    }
  }
  setTimeout(trySetup, 0);
}]
```

IDB 저장: 10초마다 체크섬 비교 → 변경 시에만 기록. 복원: 페이지 로드 시 IDB → `writeFile` → `chmod` → 에뮬레이터 시작.

---

## 모바일 대응

- 세로(portrait) 전용, 가상 게임패드는 캔버스 아래 별도 영역
- 감지: `('ontouchstart' in window) && window.innerWidth <= 680` → `body.mobile-active`
- `?gamepad` 파라미터로 데스크톱 강제 활성화 가능
- D-pad 4키 + ESC/Enter 2키, 터치 이벤트 → `KeyboardEvent` 변환
- iOS Fullscreen API 미지원 → 모바일에서 전체화면 버튼 숨김

---

## 새 타이틀 추가

`hukyou.html` 복사 후 아래 항목 수정:

| 항목 | 변경 내용 |
|------|----------|
| `DISK` | `/rom/<title>_kr.fdi` |
| `IDB_KEY` | `<title>_kr.fdi` |
| `<title>` · `document.title` | 타이틀명 |
| `logo` img src | `img/logo-<title>.png` |

`IDB_NAME` / `IDB_STORE`는 공유 — 세이브는 `IDB_KEY`로 타이틀별 분리됨.  
멀티 디스크: `DISK2`, `DISK3` 상수 추가, `Module.arguments`에 순서대로, preRun에서 모두 chmod + IDB 복원.

`index.html`: 해당 항목 `class="unavailable"` 제거, `<a href>` 추가, badge → `done`.  
`rom/`에 FDI 추가 후 data 번들 재생성 필수.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
| favicon.ico 404 | 무해 |
