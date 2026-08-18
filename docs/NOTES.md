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

예: `hukyou.js` + `hukyou.data`, `kaitou.js` + `kaitou.data`, `kitan.js` + `kitan.data`.  
JS 내부에 `loadPackage({files:[...], remote_package_size:N})`로 번들 메타데이터가 하드코딩됨.  
WASM은 NP2kai 소스 변경 시만 재빌드, JS/data는 ROM이나 BIOS 변경 시 재생성.

공통 페이지 자산(전 페이지가 같은 방식으로 include):

| 파일 | 역할 |
|------|------|
| `style.css` | 공통 스타일 |
| `icons.js` | 인라인 SVG 아이콘 단일 소스 (`data-icon` 자동 주입) |
| `audio.js` | 뮤트·오디오 resume (`btn-mute` 자동 연결) |
| `gamepad.js` | 가상 게임패드 |
| `version.js` | 사이트 통합 버전 단일 소스. footer.js가 그린 푸터 마지막 줄(`.footer-credits`)에 `· vX.Y.Z` 주입. 배포 버전은 이 파일의 `VERSION` 한 곳만 수정 |

### 아이콘 (`icons.js`)

전 페이지가 쓰는 인라인 SVG(음소거·게임패드·전체화면·상단바 접기·가상 D-pad·ESC/Enter·
디스크 선택·디버그 패널 토글·피드백 패널 토글)를 `window.ICONS = {key: '<svg>...</svg>', ...}`
한 곳에 모아둠. HTML은 `<button data-icon="mute">` 처럼 키만 쓰고, `icons.js`가
`DOMContentLoaded`에 `innerHTML`로 주입한다. `audio.js`(음소거 on/off 토글)·`debug.js`
(디버그 버튼 생성)·`feedback.js`(피드백 버튼 생성)도 자체 SVG 없이 `window.ICONS.mute` /
`.muteOff` / `.debug` / `.feedback`을 직접 참조.

- **로드 순서**: `<script src="icons.js">`를 `audio.js`보다 먼저 include (5페이지 전부 동일).
  두 스크립트 모두 동기 `<script src>`라 실행 순서 자체는 `DOMContentLoaded` 시점엔 상관없지만,
  관례상 먼저 둔다.
- **아이콘 추가/수정은 이 파일만** 고치면 5개 게임 페이지 전부에 반영됨 — 예전처럼 페이지마다
  복붙하지 말 것 (2026-08, 파편화 방지 목적으로 통합).
- 디스크 선택(`disk`) 아이콘은 희담(`kitan.html`·`kitan-opening.html`)만 씀 — 다른 타이틀은
  인게임 디스크 교체 UI가 없어 해당 키를 안 씀. 정의는 다른 아이콘과 마찬가지로 `icons.js`에.

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

**폰트**: `font.bmp`는 도깨비DNR고딕 Regular(도깨비디나루를 복원해 제작, flvrdoyster). 4타이틀 모두 한글화 완료된 뒤로는 전 타이틀이 `font.bmp` 하나만 사용 — `font_jp.bmp`(미완료 타이틀용 일본어 원본 대체)는 더 이상 안 씀, 리포에서도 제거됨.

### BIOS 번들 구성

`bios/` 전체가 4타이틀 공용으로 번들에 들어감 — 하나라도 바꾸면 **4타이틀 전부 재번들** 필요.

| 파일 | 없으면 |
|---|---|
| `bios.rom` | 부팅 불가 |
| `font.bmp` | 한글 안 나옴 (커스텀 폰트 — 덮어쓰지 말 것) |
| `np2kai.cfg` | 아래 오디오 설정 미적용 |
| `sound.rom` | 9바이트 스텁으로 대체(시그니처+`0xcb` RETF). 칩을 직접 제어하는 게임엔 무관하나 넣어두는 게 정확 |
| `2608_bd/sd/top/hh/tom/rim.wav` | **OPNA 리듬(퍼커션) 완전 무음** |

리듬 WAV는 **6개 중 하나라도 없으면 6개 전부 무효**가 된다 — fmgen `LoadRhythmSample()`이 실패 시 `if (i != 6)` 분기에서 전체를 해제하고, `RhythmMix()`는 `rhythm[0].sample == NULL`이면 통째로 건너뛴다(`sound/fmgen/fmgen_opna.cpp`). 크래시 없이 조용히 사라지므로 눈치채기 어려움. 출처는 NP2kai README가 안내하는 `Abdess/retroarch_system`의 `NEC - PC-98`.

### 오디오 튜닝 (`np2kai.cfg`)

#### 채널 볼륨 — 총량이 아니라 **비율**이 핵심 (2026-08 해결)

**증상**: 웹 빌드 소리가 원작과 다르게 거칠고 "째지는" 느낌. 같은 기기 RetroArch(libretro np2kai)에서는 부드러움 → 에뮬레이션·원작 문제가 아니라 웹 빌드 설정 문제로 확정.

**원인**: 채널 볼륨을 전부 같은 값으로 맞춰 **SSG가 FM 대비 과다**했음. SSG는 구형파·노이즈 채널이라 본질적으로 거칠어서, 비율이 틀어지면 바로 음색이 망가진다.

```
volume_F = 64    (FM)
volume_S = 28    (SSG)  ← FM의 44%. 이 비율이 핵심
volume_A = 64    (ADPCM)
volume_P = 92    (PCM)
volume_R = 64    (리듬)
DAVOLUME = 128
```

이 값들은 임의 조정이 아니라 **NP2kai가 하드코딩해둔 정규 기본값**이다 — `sdl/libretro/libretro_core_options.h`의 각 `np2kai_volume_*` 항목 끝에 default 문자열로 박혀 있음. libretro 경로는 이 값을 자동으로 쓰지만 **SDL/Emscripten 경로는 cfg에 명시하지 않으면 이 밸런스가 적용되지 않는다.** 임의로 만지지 말 것.

> 교훈: "헤드룸 확보"라며 전부 100으로 통일했다가 SSG를 2.3배로 부풀려 증상을 악화시킨 적 있음. 클리핑(총량) 관점과 음색(비율) 관점은 별개다.

#### 그 밖

- **`Latencys = 40`** (기본 `0`, 실제로는 최소 20ms로 클램프 — `sdl/soundmng.c` `soundmng_create()`): 브라우저 오디오 콜백(ScriptProcessorNode, deprecated)은 타이밍이 덜 정밀해 버퍼가 얇으면 언더런 클릭이 날 수 있어 여유를 둔 **예방 조치**. 음색과는 무관.
- **`SampleHz = 44100`**: 48000(=브라우저 AudioContext 기본값)으로 올리면 SDL 리샘플링 단계가 사라지지만 **체감 차이 없었음**. 기기마다 AudioContext 레이트가 달라(44100인 기기도 있음) 고정값을 올리면 오히려 그쪽에 리샘플링이 생기므로 44100 유지.
- **참고(검증 안 된 것)**: 효과음 시작/끝 클릭음은 PCM86 믹서(`sound/pcm86g.c`)에 샘플 경계 페이드/램프가 없는 것과 관련 있어 보이나, 위 볼륨 수정으로 체감 문제가 해소되어 더 파지 않음.

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

### IDB 디스크 교체/추출 (`debug.js`)

디버그용 디스크 교체 패널. URL에 **`?debug`**가 있을 때만 동작하고, 평소엔 토글 버튼도 패널도 만들지 않는다. 전 게임 페이지 공통(`debug.js`, `audio.js`·`gamepad.js`와 같은 위치에 포함).

- **노출**: 상단바 왼쪽 공유 컨테이너(`#topbar-left`, `feedback.js`와 공유)에 토글 버튼(`#btn-debug`, `.btn-icon`). 누르면 고정 오버레이 패널 표시(하단 게임패드를 가리지 않음). 기존 `#btn-disk`가 있는 페이지(희담)는 그 옆에 나란히 둔다.
- **스코프**: IDB(`gensei-saves`/`disks`)는 전 타이틀 공유 store라, 스코프를 안 좁히면 다른 타이틀 캐시까지 같이 나열·조작된다(실사고: 쾌도전 페이지에서 조작했는데 포물장 캐시가 같이 나옴). 페이지의 `IDB_KEY`(단일)/`DISKS`(다중, 희담류→파일명 추출)만 읽어 **현재 페이지 소유 키만** 대상으로 삼는다.
- **키별 개별 행**: 각 키마다 `[가져오기] [내보내기] [삭제]`. 다중 디스크(희담)도 어느 키에 들어갈지 애매하지 않음. 가져오기는 해당 키를 덮어씀(파일명 무관), 새로고침하면 반영(`?debug` 떼도 유지 — 게임 로드 경로가 같은 IDB를 읽음).
- **내보내기 동시 다운로드 주의**: 여러 개를 한꺼번에 트리거하면 브라우저가 "자동 다운로드 차단"으로 뒤쪽 일부를 조용히 누락시킨다 — 지금은 키별 버튼이라 한 번에 하나씩이라 문제 없음(북마클릿처럼 여러 개를 자동 순회하는 코드를 새로 짤 땐 순차+딜레이 필수).
- FDI/HDI 모두 처리(`.fdi .hdi .hdm .xdf .d88`).

콘솔 불가 환경(아이패드 등)에서 **전 타이틀을 한 번에** 추출하려면 아래 **북마클릿**이 더 편하다. 웹 브라우저 북마크 주소를 아래 코드로 교체 후, 게임 페이지에서 실행:

```js
javascript:(async()=>{const db=await new Promise(r=>{const q=indexedDB.open('gensei-saves');q.onsuccess=()=>r(q.result)});const ks=await new Promise(r=>{const q=db.transaction('disks').objectStore('disks').getAllKeys();q.onsuccess=()=>r(q.result)});for(const k of ks){const d=await new Promise(r=>{const q=db.transaction('disks').objectStore('disks').get(k);q.onsuccess=()=>r(q.result)});const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([d],{type:'application/octet-stream'}));a.download=k;document.body.appendChild(a);a.click();a.remove();await new Promise(r=>setTimeout(r,800))}alert('추출 완료: '+ks.join(', '))})();
```

전 타이틀이 같은 origin(pc98.atah.io)·같은 DB(`gensei-saves`/`disks`)라, **아무 게임 페이지에서 1회 실행하면 저장된 전 타이틀 FDI가 한꺼번에** 추출된다.

추출한 FDI에서 세이브(`PLAY*.INF`)를 다른 FDI로 이식: `pc98disk.py ls/get/add`. `PLAY*.INF`는 DISK_B 아카이브 *밖*의 루트 파일이라 인서터 빌드(`patch_fdi`)가 안 건드림 → **빌드해도 세이브는 보존**된다.

### 피드백 패널 (`feedback.js`)

게임 페이지 전용 "의견 보내기" 패널(오류 제보/번역 개선/감상 3분류). Google Apps Script 웹앱(`tools/feedback-appsscript.gs`)으로 POST → 구글 시트에 기록, 스크린샷은 Drive에 저장 후 링크만 시트에 남긴다.

- **문구·항목·엔드포인트는 `feedback.js` 상단 `CONFIG` 한 곳에만** — 그 아래 동작 코드는 거의 안 건드릴 일. `CONFIG.endpoint`가 비어 있으면 버튼 자체를 안 만든다.
- **Content-Type은 반드시 `text/plain`** — Apps Script는 preflight(OPTIONS)를 못 받아서 `application/json`이면 CORS로 실패한다. `mode:'no-cors'`도 쓰면 안 됨 — 응답을 못 읽어 실패해도 "전송됨"으로 보인다.
- **응답을 반드시 검사한다** (`res.ok` + 본문이 정확히 `'ok'`). 검사를 빼면 권한 오류로 로그인 HTML이 오든 스크립트가 `'error'`를 뱉든 전부 "감사합니다"로 보여 실패가 드러나지 않는다. 실제로 그 상태로 방치됐다가, 시트에 안 쌓이는 원인을 추적할 때 아무 단서가 없어 애먹은 적 있음.
- **`'ok'` 응답이 기록을 보장하지는 않는다** — 수신 스크립트는 허니팟 적중·빈 메시지·본문 없음 세 갈래에서도 기록 없이 `'ok'`를 반환한다. 시트에 안 쌓일 땐 Apps Script의 **실행(Executions) 로그**를 먼저 볼 것.
- **`appendRow` 안 씀 (함정)** — `appendRow`는 "내용이 있는 마지막 행" 다음에 쓰는데, 시트 아래쪽(예: 1000행 근처)에 눈에 안 보이는 잔여 내용·서식이 있으면 1001행부터 쌓여 기록이 안 되는 것처럼 보인다(실제로 겪음). 지금은 A열(타임스탬프)을 아래에서부터 훑어 진짜 마지막 데이터 행을 찾고 그 다음 줄에 직접 쓴다(`_append`/`_nextRow`).
- **curl로 엔드포인트를 테스트할 땐** `-X POST`나 `--post30x`를 쓰지 말 것. Apps Script는 POST를 302로 `googleusercontent/echo`에 넘기는데 그 주소는 GET만 받는다 — 메서드를 강제하면 405가 나서 엔드포인트가 죽은 것처럼 보인다. `curl -sS -L -d '...'`처럼 curl이 알아서 GET으로 전환하게 둬야 정상 응답(`ok`)을 본다.
- **허니팟**: 숨겨진 입력칸(`fb-hp`)에 값이 있으면 봇으로 간주해 조용히 성공 응답(재시도 유도 안 함).
- **스크린샷**: 캔버스 `toDataURL()`로 캡처, 체크박스로 동의 받은 뒤에만 전송. 시트 셀 5만 자 제한 때문에 base64를 시트에 안 넣고 Drive에 파일로 저장 후 URL만 기록. 저장 위치는 `feedback-appsscript.gs`의 `FOLDER_ID`(폴더 이름이 아니라 ID — 이름을 바꿔도 안 깨진다).
- **캡처가 새까맣게 나오는 함정 → `enableCanvasCapture()`**: SDL이 WebGL 렌더러를 고르면 캔버스가 WebGL 컨텍스트가 되는데, WebGL은 컴포지팅 직후 드로잉 버퍼를 비운다(`preserveDrawingBuffer` 기본 false). 그래서 **화면엔 보이는데** 버튼 클릭 시점의 `toDataURL()`은 전부 검정으로 나온다. 이 속성은 **컨텍스트 생성 시점에만** 지정 가능하므로, 에뮬레이터가 컨텍스트를 만들기 전(=`init()`, ▶시작 클릭 이전)에 `canvas.getContext`를 감싸 강제 주입한다.
  - 글루(`emnp2kai_sdl2.js`)를 직접 패치하지 않은 이유: NP2kai 재빌드 때마다 날아간다. 래퍼 방식은 빌드 산출물과 무관.
  - **피드백 기능이 켜져 있을 때만** 적용된다(`CONFIG.endpoint` 비었거나 허브면 미적용) — 쓰지도 않을 렌더링 비용을 안 지도록.
  - 비용: 프레임마다 버퍼 swap 대신 복사(640×400 ≈ 프레임당 1MB). CPU 에뮬레이션 부하에 비해 무시할 수준이고 실기 체감 차이 없음.
  - SDL이 2D 렌더러를 고른 환경에선 래퍼가 아무 일도 안 한다(2D는 원래 캡처됨). **같은 코드인데 어떤 날은 캡처가 되고 어떤 날은 까맣게 나왔던 것**도 이 렌더러 선택 차이로 추정 — 코드 변경 이력에는 원인이 없었다.
- **키 이벤트 전파 차단**: 에뮬레이터가 `document` keydown을 canvas로 넘기므로, 오버레이 안 끊으면 패널에 타이핑한 게 게임에도 입력된다. `overlay`에서 `keydown/keyup/keypress`를 `stopPropagation()`.
- **상단바 배치**: `#topbar-left`를 `debug.js`와 공유(스크립트 로드 순서 무관하게 먼저 만든 쪽이 컨테이너를 만들고 나머지가 재사용). 피드백은 항상 보이므로 맨 왼쪽 고정, 디스크(희담)/디버그(`?debug`)는 조건부라 그 오른쪽.
- **doGet 없음**: 의도적. doGet으로 시트를 반환하게 두면 URL만 알아도 남의 제보를 읽을 수 있어서, 쓰기 전용으로 유지.
- **허브(index)는 피드백 패널 대신 블로그 링크**: `init()`이 `.top-bar` 유무로 먼저 분기 — 허브는 상단바가 없는 별도 레이아웃이라 패널을 아예 안 만들고, `CONFIG.blog.url`로 나가는 단순 `<a>` 링크(`buildBlogLink()`)만 게임 목록 아래에 둔다. 아이콘은 `window.ICONS.blog`(티스토리 로고). 원형 로고라 사각 실루엣 아이콘들과 같은 22px면 광학적으로 작아 보여서 `height=25`로 살짝 키움(원형 아이콘 관례).

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
- 태블릿 등 터치 기기에서는 상단바에 게임패드 활성화 버튼 표시 (`btn-gamepad`). 누르면 `?gamepad` 파라미터를 `history.replaceState`로 URL에 추가 (리로드 없음). 이때 빈값 파라미터의 `=`는 떼어 `?gamepad&debug`처럼 정리
- 활성화 시 `position: fixed; bottom: 0`으로 화면 하단 고정(캔버스 위에 떠 콘텐츠를 밀지 않음)
- 게임 페이지(`body:has(#canvas-wrap)`)는 `min-height` 강제를 풀어 푸터 아래 빈 공간/스크롤이 생기지 않게 한다(허브는 `min-height:100vh` 유지)

### 상단바 접기 (`btn-collapse`)

- 모바일 전용 토글 버튼(상단바 우측, 전체화면 자리). 클릭 시 `body.chrome-hidden` 토글
- 게임 내 마우스 클릭과 겹치지 않도록 캔버스 탭이 아닌 전용 버튼 방식
- 접힘 상태: `.top-bar`를 `height: 0; overflow: hidden`으로 클립(자식 버튼들 같이 숨김), body 위 패딩·캔버스 위 마진 제거로 캔버스를 화면 상단에 밀착
- `#footer`·`.hint`도 `body.chrome-hidden`에서 숨김. 원래 미디어쿼리(`max-width:680px`)에서만 숨겨지던 게 아니라 `chrome-hidden` 자체에 규칙이 없어서, 접어도 안 사라지던 버그(suiko-web-v2에서 먼저 발견·수정 후 역이식)
- 접기 버튼만 `position: fixed`로 클립을 벗어나 화면 상단 중앙에 잔류 (chevron 180° 회전)

### 전체화면 ESC (`btn-fullscreen`)

- `canvas-wrap`을 `requestFullscreen`. 진입 직후 `navigator.keyboard.lock(['Escape'])`로 ESC를 잠근다.
- 잠금 성공 시(**Chrome/Edge + 보안 컨텍스트=localhost/HTTPS 한정**): 짧은 ESC는 **에뮬레이터로 전달**(게임 키 유지), 전체화면은 **길게 눌러야** 해제. 전체화면 중 ESC(`keydown`)를 누를 때마다 `MSG.FULLSCREEN_ESC` 토스트로 안내(진입 시 1회 노출은 놓치기 쉬워 매회 노출로 변경).
- 미지원(Safari·Firefox)·비보안 컨텍스트(LAN IP 등)에선 `lock`이 없거나 거부됨 → `catch`로 넘겨 기존 네이티브 동작(짧은 ESC로 종료) 유지.
- `fullscreenchange`에서 전체화면이 풀리면 `keyboard.unlock()`.
- 데스크톱 힌트(`.hint`, 모바일 숨김): `이동: 방향키, 결정: Enter/Space, 취소: ESC/Shift`.
- 토스트(`#toast`)는 전체화면 중 `#canvas-wrap:fullscreen #toast`로 크기를 키움. 캔버스가 `min(100vw,160vh)` 등 뷰포트 비례로 커지는 것과 같은 축이라 `em`이 아닌 `vmin`으로 스케일(`font-size: 2.4vmin` 등) — `em`은 캔버스 확대량과 무관해 체감이 안 됨. 노출 시간은 전 페이지 공통 `showToast(msg, duration=2000)` 기본값(로드 실패만 5000ms 예외).

### 버튼 표시 규칙 (CSS 미디어쿼리)

| 버튼 | PC (hover+fine) | 터치 기기 | 비고 |
|------|-----------------|-----------|------|
| 게임패드 (`btn-gamepad`) | 숨김 | 표시 | 게임패드 활성 시 숨김 |
| 상단바 접기 (`btn-collapse`) | 숨김 | 표시 | 접힘 시 상단 중앙 고정 |
| 전체화면 (`btn-fullscreen`) | 표시 | 숨김 | — |
| 뮤트 (`btn-mute`) | 에뮬레이션 시작 후 표시 | 동일 | 접힘 시 같이 숨김 |

아이콘 버튼(`.btn-icon`)은 회색 채움 호버 없이 색만 변함. 회색 채움 호버는 disk-panel 메뉴 버튼에만 적용.

### 가로 모드 캔버스 (터치 기기)

`@media (max-width: 680px)`(폭 기준)만으로는 부족 — 폰이 가로로 눕는 순간 폭이 680px를 쉽게 넘어가 규칙이 안 걸리고 고정 640×400 캔버스가 짧은 뷰포트에서 위아래로 잘린다.  
`@media (orientation: landscape) and (pointer: coarse)`를 추가해 이 경우만 **높이 기준**(뷰포트 전체 높이, 폭은 8:5 비율로 계산)으로 몰아 화면 전체가 보이게 한다. 세로 모드는 기존 폭 기준 규칙 그대로 유지.  
(suiko-web-v2에서 역이식. 그쪽은 640×480(4:3)이라 비율만 8:5로 환산)

**갤럭시 폴드 등 정사각형에 가까운 화면비 대응**: 펼쳤을 때 화면비가 1:1대인 기기는 높이 기준 폭(`100vh*8/5`)이 실제 뷰포트 폭을 초과해 캔버스가 화면 밖으로 넘친다(제보: "화면이 엄청 커짐"). `width: min(100vw, calc(100vh*8/5))`, `height: min(100vh, calc(100vw*5/8))`로 양쪽 다 clamp — 전체화면 규칙(`#canvas-wrap:fullscreen canvas`)과 동일 패턴. 일반 폰(가로로 긴 화면)은 폭 clamp가 안 걸려 기존과 동일하게 동작. **실기 미보유로 로직 검증만 했고 실측 확인은 못함** — 문제 재발 시 우선 의심할 지점.

### 세이브 복원 타이밍

`preRun`에서 `FS.stat()`으로 ROM 파일 마운트 여부를 폴링 (10ms 간격, 최대 2초).  
첫 페이지 로드 시 .data 파일 처리가 느릴 수 있어 단순 `setTimeout(0)`으로는 부족.  
타임아웃 시 세이브 없이 원본으로 시작.

### 세이브 저장 토스트

`saveDisk(s)`가 폴링 중 체크섬이 실제로 바뀐 걸 감지해 IDB에 쓴 직후 `MSG.SAVE_SAVED` 토스트. `lastChecksum`은 부팅 직후(`postRun`)에 현재 디스크로 초기화되므로 헛김(부팅 직후 첫 폴링에서 오탐) 없음.  
다중 디스크(희담: system+data)는 디스크별 반복 중 **하나라도** 바뀌면 호출당 토스트 1회만(디스크마다 따로 뜨지 않게 `saved` 플래그로 취합).  
세이브 대상이 아닌 페이지(희담 오프닝)는 미적용. (suiko-web-v2에서 역이식)

### 제한 사항

- 터치 기기에서 전체화면 버튼 숨김 (CSS `@media (hover: none), (pointer: coarse)`)
- 풀스크린 시 게임패드는 canvas-wrap 바깥이므로 표시 안 됨 (의도된 동작)

---

## 새 타이틀 추가

단일 디스크 FDI(풍광전·쾌도전)는 `hukyou.html`, 멀티 디스크 FDI(희담)는 `kitan.html`, HDI(포물장)는 `torimono.html`을 복사 후 수정:

| 항목 | 내용 |
|------|------|
| `DISK` / `DISKS` | ROM 경로 (`/rom/<title>.fdi`) |
| `IDB_KEY` | 타이틀별 세이브 분리 키 |
| `document.title` | 타이틀명 |
| `logo` img src/height | `img/logo-<title>.png`, 높이 기준 (풍광전 42px, 희담 54px) |
| `s.src` | `<title>.js` |

멀티 디스크: `Module.arguments`에 FDI 경로를 순서대로, preRun에서 모두 chmod.  
단, **런타임 디스크 교체는 불가** — NP2kai가 내부 메모리에 디스크를 캐싱하므로 `FS.writeFile()`이 무시됨.

**HDI 게임(포물장)**: FDI가 아니라 부팅 가능한 PC-98 HDD 이미지. np2kai 웹빌드의 커맨드라인 확장자 분기에 `.hdi`가 없어 `Module.arguments`는 비우고, preRun에서 번들 내 `np2kai.cfg`에 `HDD1FILE`을 주입해 SASI HDD로 마운트한다(페이지 번들 FS 안에서만 — 공유 cfg 원본 무영향). 인서트·파티션 처리 상세는 `tools/TORIMONO.md` 참조.

번들 생성: 게임별 bios + ROM으로 `<title>.data` 생성, `emnp2kai_sdl2.js` 복사 후 `<title>.js`로 메타데이터 교체.

`index.html`: 해당 항목 `class="unavailable"` 제거, `<a href>` 추가, badge → `done`.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 — 기능 정상 |
| 런타임 디스크 교체 불가 | NP2kai가 디스크를 내부 캐싱. `diskdrv_setfdd()` 등의 export가 필요 |
| 태블릿 블루투스 키보드, 백그라운드 복귀 후 입력 안 됨 | 원인 미상 — 아래 참조. 미해결 |

### 태블릿 블루투스 키보드 — 백그라운드 복귀 후 입력 끊김 (미해결)

iPad + 블루투스 키보드로 플레이 중, 앱을 백그라운드로 보내거나 다른 탭에 갔다 돌아오면
키보드 입력이 게임에 전달되지 않는 현상 (2026-08 제보).

**확인된 사실** (실기 테스트, `document`에 `keydown` capture 리스너를 걸어 직접 관찰):
- 증상 발생 시 `document`에 `keydown` 이벤트 자체가 전혀 도착하지 않는다(캡처 단계에서도 안 잡힘).
- 같은 상태에서 **브라우저 주소창엔 정상 타이핑됨**, **다른 웹페이지로 이동하면 정상 동작** — 키보드·OS·블루투스 연결 자체는 살아있다. 이 페이지의 콘텐츠 영역만 입력 대상으로 인정을 못 받는 상태로 보임.
- 화면을 터치하면(가상 게임패드 버튼 등, 특정 위치 무관) 풀리는 경우가 있었으나 **재현이 불안정** — 같은 방법이 다음 발생 시엔 안 먹히기도 함.

**시도했다가 효과 없었던 것**:
- `<canvas>`에 `tabindex="-1"` 부여 + `visibilitychange` 시점에 `canvas.focus({preventScroll:true})` 호출 — 스크립트로 만든 focus는 이 문제에 영향 없음.

**현재 결론**: iOS/iPadOS Safari가 탭 복귀 시 콘텐츠 프레임으로 실제 입력 포커스를 넘기지 못하는 것으로 추정되나, 신뢰 가능한(trusted) 터치 제스처로도 재현이 불안정해 페이지 스크립트로 확실히 재현·해결할 방법을 못 찾음. 추가 단서(재현 조건 — 탭 전환/홈 버튼/Split View 중 어느 쪽에서 더 잦은지 등) 없이는 보류.

---

## 자매 프로젝트 (suiko-web-v2)

`suiko-web-v2`(환세취호전, doswasmx 기반 Windows 95 에뮬레이터)는 이 프로젝트의 웹 에뮬레이터 UI를 바탕으로 만들어진 별도 리포. 같은 사이트 계열(atah.io)에서 서빙되지만 공유 패키지/서브모듈은 안 씀 — 정적 사이트라 빌드 파이프라인 도입 비용이 수동 이식 비용보다 크다고 판단(2026-07).

`style.css`와 `suiko-web-v2`의 `suiko-overrides.css`는 구조를 맞춰 관리한다. 가로 모드 대응·세이브 토스트·`chrome-hidden` 접기·전체화면 등 **공용 UI/로직을 고칠 때는 다른 쪽에도 해당 사항이 있는지 확인**할 것. 그대로 복사는 안 되고 매번 다음을 맞춰 조정해야 한다:

- 종횡비: 이쪽 640×400(8:5) vs suiko 640×480(4:3)
- DOM id: `#canvas-wrap` vs `#canvasDiv`
- 기능 적용 범위: 다중 디스크 여부, 버튼 유무 등 리포별 차이
