# 웹 에뮬레이터 기술 노트

NP2kai를 Emscripten으로 브라우저에 포팅한 구현 기록. 같은 방식으로 PC-98 에뮬레이터나
비슷한 네이티브 에뮬레이터를 웹에 올리려는 경우 참고가 될 만한 내용 위주로 정리했다.

---

## 구조 개요

WASM 바이너리는 전 게임이 공유하고, JS 로더와 데이터 번들만 게임별로 나뉜다.

| 파일 | 역할 |
|------|------|
| `emnp2kai_sdl2.wasm` | NP2kai 바이너리 (공유) |
| `<title>.js` | 게임별 JS 로더 (번들 메타데이터 포함) |
| `<title>.data` | 게임별 BIOS + ROM 번들 |

예를 들면 `hukyou.js`+`hukyou.data`, `kaitou.js`+`kaitou.data` 식이다. JS 안에
`loadPackage({files:[...], remote_package_size:N})` 형태로 번들 메타데이터가 하드코딩되어
있다. WASM은 NP2kai 소스가 바뀔 때만 재빌드하면 되고, JS/data는 ROM이나 BIOS가 바뀔 때마다
재생성한다.

전 페이지가 같은 방식으로 include하는 공통 자산은 다음과 같다.

| 파일 | 역할 |
|------|------|
| `style.css` | 공통 스타일 |
| `icons.js` | 인라인 SVG 아이콘 단일 소스 (`data-icon` 자동 주입) |
| `audio.js` | 뮤트·오디오 resume (`btn-mute` 자동 연결) |
| `gamepad.js` | 가상 게임패드 |
| `version.js` | 사이트 통합 버전 단일 소스. footer.js가 그린 푸터 마지막 줄(`.footer-credits`)에 `· vX.Y.Z`를 주입한다. 배포 버전은 이 파일의 `VERSION` 한 곳만 고치면 된다 |

### 아이콘 (`icons.js`)

전 페이지가 쓰는 인라인 SVG(음소거, 게임패드, 전체화면, 상단바 접기, 가상 D-pad, ESC/Enter,
디스크 선택, 디버그 패널 토글, 피드백 패널 토글)를 `window.ICONS = {key: '<svg>...</svg>'}`
한 곳에 모아 뒀다. 처음엔 게임 페이지 5개에 SVG가 그대로 복붙되어 있었는데, 2026년 8월에
이렇게 정리했다. HTML은 `<button data-icon="mute">`처럼 키만 쓰고, `icons.js`가
`DOMContentLoaded` 시점에 `innerHTML`로 채워 넣는다. `audio.js`(음소거 on/off 토글),
`debug.js`(디버그 버튼 생성), `feedback.js`(피드백 버튼 생성)도 자체 SVG를 안 갖고
`window.ICONS.mute`/`.muteOff`/`.debug`/`.feedback`을 직접 참조한다. 이제 아이콘을
추가하거나 고칠 땐 이 파일 하나만 손보면 5개 게임 페이지 전부에 반영된다.

`<script src="icons.js">`는 5페이지 전부 `audio.js`보다 먼저 온다. 둘 다 동기
`<script src>`라 실행 순서 자체는 `DOMContentLoaded` 시점엔 상관없지만 관례로 먼저 뒀다.
디스크 선택(`disk`) 아이콘은 희담(`kitan.html`·`kitan-opening.html`)만 쓴다 — 다른
타이틀은 인게임 디스크 교체 UI가 없어서다.

---

## 빌드

### CMake 플래그

| 플래그 | 없으면 |
|--------|--------|
| `ASYNCIFY=1` | 메인 루프가 `emscripten_sleep()`을 쓰지 못해 브라우저가 블로킹되어 실행 불가 |
| `EMULATE_FUNCTION_POINTER_CASTS=1` | C 코드베이스의 함수 포인터 타입 불일치로 WASM 런타임이 크래시 |
| `USE_EMULARITY_NP2DIR` | BIOS 경로가 `/np2kai/`가 아닌 다른 경로로 잡혀 BIOS 로드 실패 |
| `EMSCRIPTEN=1` (CMAKE_C_FLAGS) | `np2.c`의 `#ifdef EMSCRIPTEN` 분기가 꺼져 브라우저 비호환 코드가 실행됨 |
| `EXPORTED_RUNTIME_METHODS=[FS]` | JS에서 `Module.FS`에 접근할 수 없어 세이브 지속성을 구현할 수 없음 |

### 소스 패치

`embed/menubase/menubase.c`의 `menubase_modalproc()`은 네이티브에서는 blocking while
루프로 모달을 처리하는데, 브라우저에서는 이게 메인 스레드를 그대로 점유해 버려서 즉시
반환하도록 패치했다.

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

게임마다 별도 data 파일을 만든다. 임시 디렉토리에 해당 게임의 bios와 ROM만 모아서
번들링하는 식이다.

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

생성된 `loader.js`에서 메타데이터를 추출해 게임별 JS의 `loadPackage(...)` 부분을 교체한다.

```bash
# 기존 emnp2kai_sdl2.js를 복사하고 파일명 + 메타데이터를 sed로 교체
cp emnp2kai_sdl2.js hukyou.js
sed -i '' -e 's/emnp2kai_sdl2.data/hukyou.data/g' \
          -e 's/datafile_emnp2kai_sdl2.data/datafile_hukyou.data/g' hukyou.js
# loadPackage({files:[...]}) 부분도 loader.js에서 추출한 메타데이터로 교체
```

`font.bmp`는 도깨비디나루를 복원해 flvrdoyster가 만든 도깨비DNR고딕 Regular다. 4타이틀
모두 한글화를 마친 뒤로는 전 타이틀이 이 폰트 하나만 쓴다 — 미완료 타이틀용으로 일본어
원본을 대체하던 `font_jp.bmp`는 이제 안 쓰고 리포에서도 지웠다.

### BIOS 번들 구성

`bios/` 전체가 4타이틀 공용으로 번들에 들어가서, 하나만 바꿔도 4타이틀 전부 재번들해야
한다.

| 파일 | 없으면 |
|---|---|
| `bios.rom` | 부팅 불가 |
| `font.bmp` | 한글이 안 나옴(커스텀 폰트라 덮어쓰면 안 됨) |
| `np2kai.cfg` | 아래 오디오 설정이 적용 안 됨 |
| `sound.rom` | 9바이트 스텁으로 대체(시그니처+`0xcb` RETF). 칩을 직접 제어하는 게임엔 영향 없지만 넣어두는 게 정확하다 |
| `2608_bd/sd/top/hh/tom/rim.wav` | OPNA 리듬(퍼커션)이 완전히 무음이 된다 |

리듬 WAV 6개는 하나라도 빠지면 전부 무효가 된다. fmgen의 `LoadRhythmSample()`이 로드에
실패하면 `if (i != 6)` 분기에서 6개를 통째로 해제해 버리고, `RhythmMix()`는
`rhythm[0].sample == NULL`이면 아예 건너뛰기 때문이다(`sound/fmgen/fmgen_opna.cpp`).
크래시 없이 조용히 사라져서 눈치채기 어렵다. 출처는 NP2kai README가 안내하는
`Abdess/retroarch_system`의 `NEC - PC-98`이다.

### 오디오 튜닝 (`np2kai.cfg`)

웹 빌드 소리가 원작과 다르게 거칠고 째지는 문제가 있었는데, 같은 기기에서 RetroArch(libretro
np2kai)로 돌리면 부드러워서 에뮬레이션이나 원작 문제가 아니라 웹 빌드 설정 문제로 보고
2026년 8월에 원인을 찾았다.

원인은 채널 볼륨을 전부 같은 값으로 맞춰 놓은 것이었다. SSG는 구형파·노이즈 채널이라
본질적으로 거칠고, FM 대비 SSG 비율이 조금만 틀어져도 음색이 바로 망가진다. 정답은 총
볼륨 크기가 아니라 채널 간 비율이었다.

```
volume_F = 64    (FM)
volume_S = 28    (SSG)  ← FM의 44%. 이 비율이 핵심
volume_A = 64    (ADPCM)
volume_P = 92    (PCM)
volume_R = 64    (리듬)
DAVOLUME = 128
```

이 값은 임의로 조정한 게 아니라 NP2kai가 하드코딩해 둔 정규 기본값이다
(`sdl/libretro/libretro_core_options.h`의 각 `np2kai_volume_*` 항목 끝에 default로 박혀
있다). libretro 경로는 이 값을 자동으로 쓰지만, SDL/Emscripten 경로는 cfg에 명시하지
않으면 이 밸런스가 적용되지 않는다. 한 번은 "헤드룸을 확보한다"며 전부 100으로 통일했다가
SSG만 2.3배로 부풀려 증상을 오히려 악화시킨 적이 있다 — 클리핑(총량)과 음색(비율)은
완전히 다른 문제다.

그 밖의 설정으로, `Latencys`는 기본값 0이지만 실제로는 최소 20ms로 클램프된다
(`sdl/soundmng.c`의 `soundmng_create()`). 브라우저 오디오 콜백(ScriptProcessorNode,
deprecated)은 타이밍이 덜 정밀해서 버퍼가 얇으면 언더런 클릭이 날 수 있어, 여유를 두려고
40으로 올렸다 — 음색과는 무관한 예방 조치다. `SampleHz`는 44100을 유지한다. 48000(브라우저
AudioContext 기본값)으로 올리면 SDL 리샘플링 단계가 사라지지만 체감 차이는 없었고, 기기마다
AudioContext 레이트가 다르기 때문에(44100인 기기도 있다) 고정값을 올리면 오히려 그쪽에
리샘플링이 생긴다. 효과음 시작·끝의 클릭음은 PCM86 믹서(`sound/pcm86g.c`)에 샘플 경계
페이드가 없는 것과 관련 있어 보이지만, 위 볼륨 수정으로 체감 문제가 해소되어 더 파고들진
않았다 — 검증되지 않은 추정으로 남겨 둔다.

---

## 세이브 지속성

`--preload-file`로 번들된 파일은 MEMFS에 읽기 전용으로 마운트된다. NP2kai는
`dosio.c`의 `file_attr()`에서 `S_IWUSR` 비트를 보고 read-only면 쓰기를 무시하기 때문에,
에뮬레이터를 시작할 때 `Module.FS.chmod(DISK, 0o666)`을 호출해서 풀어준다.

다만 `preRun` 콜백 시점에는 아직 `--preload-file` 파일이 MEMFS에 마운트되지 않아서
`chmod`가 실패한다. 그래서 `addRunDependency`로 에뮬레이터 시작을 지연시키고
`FS.stat()`을 폴링해 마운트가 끝난 걸 확인한 뒤 처리한다.

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

세이브 저장소로 localStorage 대신 IndexedDB를 골랐다. localStorage는 도메인당 5~10MB
제한이 있어서 FDI를 base64로 인코딩하면 넘칠 수 있는 반면, IndexedDB는 `ArrayBuffer`를
그대로 저장할 수 있고 용량 제한도 훨씬 크다. 저장 전략은 10초마다 FDI 바이트 합 체크섬을
비교해서 바뀌었을 때만 IDB에 기록하는 것이고, 페이지를 로드할 때는 IDB에서 읽어
`writeFile` → `chmod` 순으로 복원한 뒤 에뮬레이터를 시작한다. DB는 `gensei-saves`, store는
`disks`이고 키는 FDI 파일명(`hukyou_kr.fdi`, `kitan-system.fdi` 등)이라 게임과 디스크별로
자연히 분리된다. 다중 디스크 게임(희담: system+data)은 디스크마다 체크섬을 따로 비교해서
바뀐 디스크만 기록한다(희담 데모/오프닝은 세이브 대상이 아니다).

### 디버그 디스크 패널 (`debug.js`)

URL에 `?debug`가 있을 때만 켜지는 디스크 교체·추출용 패널이다. 평소에는 토글 버튼도
패널도 아예 만들지 않고, `audio.js`·`gamepad.js`와 같은 위치에서 전 게임 페이지에
공통으로 로드된다.

상단바 왼쪽의 공유 컨테이너(`#topbar-left`, `feedback.js`와 공유)에 토글 버튼을 두고,
누르면 고정 오버레이 패널이 뜬다(하단 게임패드는 안 가림). `#btn-disk`가 있는 페이지
(희담)는 그 옆에 나란히 배치된다.

IDB(`gensei-saves`/`disks`)는 전 타이틀이 공유하는 store라서, 스코프를 좁히지 않으면
다른 타이틀 캐시까지 같이 나열되고 조작 대상이 된다 — 실제로 쾌도전 페이지에서 조작했는데
포물장 캐시가 같이 나온 적이 있다. 그래서 페이지의 `IDB_KEY`(단일)나 `DISKS`(다중,
희담류에서 파일명만 추출)만 읽어서 현재 페이지가 소유한 키만 대상으로 삼는다. 각 키는
가져오기/내보내기/삭제 버튼이 딸린 개별 행으로 표시돼서, 다중 디스크(희담)도 어느 키에
들어갈지 헷갈리지 않는다. 가져오기는 그 키를 덮어쓰고(파일명 무관) 새로고침하면 반영된다
(`?debug`를 떼도 유지된다 — 게임 로드 경로가 같은 IDB를 읽기 때문). 내보내기를 여러 개
한꺼번에 트리거하면 브라우저가 자동 다운로드 차단으로 뒤쪽 일부를 조용히 누락시키는데,
지금은 키별 버튼이라 한 번에 하나씩만 받아서 문제가 안 된다 — 여러 개를 자동으로 순회하는
코드를 새로 짠다면 순차 처리에 딜레이를 꼭 넣어야 한다. FDI/HDI 모두 처리한다(`.fdi .hdi
.hdm .xdf .d88`).

콘솔을 쓸 수 없는 환경(아이패드 등)에서 전 타이틀을 한 번에 추출하려면 북마클릿이 더
편하다. 브라우저 북마크 주소를 아래 코드로 바꾸고 아무 게임 페이지에서 실행하면 된다.

```js
javascript:(async()=>{const db=await new Promise(r=>{const q=indexedDB.open('gensei-saves');q.onsuccess=()=>r(q.result)});const ks=await new Promise(r=>{const q=db.transaction('disks').objectStore('disks').getAllKeys();q.onsuccess=()=>r(q.result)});for(const k of ks){const d=await new Promise(r=>{const q=db.transaction('disks').objectStore('disks').get(k);q.onsuccess=()=>r(q.result)});const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([d],{type:'application/octet-stream'}));a.download=k;document.body.appendChild(a);a.click();a.remove();await new Promise(r=>setTimeout(r,800))}alert('추출 완료: '+ks.join(', '))})();
```

전 타이틀이 같은 origin(pc98.atah.io)과 같은 DB(`gensei-saves`/`disks`)를 쓰기 때문에,
아무 게임 페이지에서 한 번만 실행해도 저장된 전 타이틀 FDI가 한꺼번에 추출된다. 추출한
FDI에서 세이브(`PLAY*.INF`)를 다른 FDI로 옮기려면 `pc98disk.py`의 ls/get/add를 쓰면
된다. `PLAY*.INF`는 DISK_B 아카이브 밖의 루트 파일이라 인서터 빌드(`patch_fdi`)가 안
건드리므로, 빌드를 다시 해도 세이브는 보존된다.

### 피드백 패널 (`feedback.js`)

게임 페이지 전용 "의견 보내기" 패널이다(오류 제보/번역 개선/감상 3분류). Google Apps
Script 웹앱(`tools/feedback-appsscript.gs`)으로 POST하면 구글 시트에 기록되고, 스크린샷은
Drive에 저장한 뒤 링크만 시트에 남는다. 문구·분류·엔드포인트는 `feedback.js` 상단의
`CONFIG` 한 곳에만 있고, `CONFIG.endpoint`가 비어 있으면 버튼 자체를 만들지 않는다.

허브(index)는 상단바가 없는 별도 레이아웃이라 패널 대신 `CONFIG.blog.url`로 나가는 단순
링크(`buildBlogLink()`)를 게임 목록 아래에 둔다. `init()`이 `.top-bar` 유무로 이 둘을
가른다. 아이콘은 `window.ICONS.blog`(티스토리 로고)인데, 원형 로고는 사각 실루엣
아이콘들과 같은 22px면 광학적으로 작아 보여서 25px로 살짝 키웠다. 상단바 배치는
`debug.js`와 `#topbar-left` 컨테이너를 공유한다 — 어느 스크립트가 먼저 로드되든 먼저
만든 쪽이 컨테이너를 만들고 나머지가 재사용하는 방식이다. 피드백은 항상 보이는 유일한
버튼이라 맨 왼쪽에 고정하고, 조건부로 나타나는 디스크(희담)·디버그(`?debug`)는 그 오른쪽에
붙는다.

에뮬레이터가 `document`의 keydown을 canvas로 넘기기 때문에, 오버레이 안에서
`stopPropagation()`을 안 걸면 패널에 타이핑한 내용이 게임에도 입력된다. `doGet`은
일부러 안 만들었다 — 시트를 반환하는 `doGet`이 있으면 URL만 알아도 남의 제보를 읽을 수
있어서, 쓰기 전용으로 유지한다.

이 기능을 만들면서 실제로 시간이 든 문제가 몇 개 있었다.

- **Content-Type은 반드시 `text/plain`이어야 한다.** Apps Script는 preflight(OPTIONS)를
  받지 못해서 `application/json`으로 보내면 CORS로 막힌다. `mode:'no-cors'`도 쓰면 안
  된다 — 응답을 못 읽게 되어 실패해도 "전송됨"으로 보인다.
- **응답을 반드시 검사해야 한다**(`res.ok` + 본문이 정확히 `'ok'`). 이걸 빼먹었을 때는
  권한 오류로 로그인 HTML이 오든 스크립트가 `'error'`를 뱉든 전부 "감사합니다"로 떠서
  실패가 전혀 드러나지 않았다 — 시트에 기록이 안 쌓이는 원인을 추적할 때 단서가 하나도
  없어 한참 헤맸다.
- `'ok'` 응답이 실제 기록을 보장하지는 않는다. 수신 스크립트는 허니팟 적중, 빈 메시지,
  본문 없음 세 경우에도 기록 없이 `'ok'`를 돌려주기 때문에, 시트에 안 쌓일 땐 Apps
  Script의 실행(Executions) 로그부터 봐야 한다.
- `appendRow`는 안 쓴다. `appendRow`는 "내용이 있는 마지막 행" 다음에 쓰는데, 시트
  아래쪽(예: 1000행 근처)에 눈에 안 보이는 잔여 서식이 있으면 1001행부터 쌓여서 기록이
  안 되는 것처럼 보인 적이 있다. 지금은 A열(타임스탬프)을 아래에서부터 훑어 진짜 마지막
  데이터 행을 찾고 그 다음 줄에 직접 쓴다(`_append`/`_nextRow`).
- curl로 엔드포인트를 테스트할 땐 `-X POST`나 `--post30x`를 쓰면 안 된다. Apps Script는
  POST를 302로 `googleusercontent/echo`에 넘기는데 그 주소는 GET만 받아서, 메서드를
  강제하면 405가 나 엔드포인트가 죽은 것처럼 보인다. `curl -sS -L -d '...'`처럼 curl이
  알아서 GET으로 바꾸도록 둬야 정상 응답(`ok`)을 본다.
- 스크린샷은 캔버스 `toDataURL()`로 캡처하고 체크박스로 동의를 받은 뒤에만 전송한다.
  시트 셀은 5만 자 제한이 있어서 base64를 시트에 직접 못 넣고, Drive에 파일로 저장한 뒤
  URL만 기록한다(저장 위치는 `feedback-appsscript.gs`의 `FOLDER_ID` — 이름이 아니라
  ID라서 폴더 이름을 바꿔도 안 깨진다).
- 캡처가 새까맣게 나온 적이 있는데, 원인은 SDL이 WebGL 렌더러를 고른 환경에서 WebGL이
  컴포지팅 직후 드로잉 버퍼를 비우기 때문이었다(`preserveDrawingBuffer` 기본값 false).
  화면엔 보이는데 버튼을 누른 시점의 `toDataURL()`은 이미 빈 버퍼를 읽어서 검게 나온
  것. 이 속성은 컨텍스트 생성 시점에만 지정할 수 있어서, 에뮬레이터가 컨텍스트를 만들기
  전에(`init()`, ▶시작 클릭 이전) `canvas.getContext`를 감싸 강제로 주입했다
  (`enableCanvasCapture()`). 글루(`emnp2kai_sdl2.js`)를 직접 패치하는 방법도 있었지만
  NP2kai를 재빌드할 때마다 날아가서, 대신 이 래퍼 방식을 골랐다. 피드백 기능이 켜진
  경우에만 적용해 불필요한 렌더링 비용을 지지 않게 했고, 비용 자체도 640×400 기준
  프레임당 1MB 정도라 CPU 에뮬레이션 부하에 비하면 무시할 수준이었다(실기 체감 차이
  없음 확인). SDL이 2D 렌더러를 고른 환경에선 이 래퍼가 아무 일도 안 한다(2D는 원래도
  캡처가 된다) — 같은 코드인데 어떤 날은 캡처가 되고 어떤 날은 까맣게 나왔던 것도 이
  렌더러 선택 차이로 보인다. 다만 이건 추정이고, 코드 변경 이력을 뒤져 봐도 그 시점에
  렌더링 관련 변경은 없었다.

---

## 모바일/태블릿 대응

오디오(`audio.js`)는 `Module.SDL2.audioContext`의 `suspend()`/`resume()`으로 뮤트를
구현하고, `visibilitychange`·`click`·`keydown`에서 오디오를 재개한다(뮤트 상태면
스킵). 뮤트 버튼은 에뮬레이션이 시작되기 전엔 숨겨 뒀다가 AudioContext가 생성되는 걸
감지하면 보여준다.

가상 게임패드(`gamepad.js`)는 방향키 4개와 ESC/Enter 2개, 총 6키를 지원한다. 터치
이벤트를 `KeyboardEvent`로 변환해 canvas에 dispatch하고, PC-98 게임이라 멀티터치는
필요 없어서 단일 터치만 처리한다. 키 캡은 CSS `border-bottom`과 `translateY`로 3D
느낌을 냈고, 키 아이콘은 RasterForge 픽셀 폰트 기반 SVG(`img/key-*.svg`)를 쓴다.
`?gamepad` URL 파라미터를 주거나 모바일(`ontouchstart` + `innerWidth <= 680`)이면
자동으로 켜지고, 태블릿처럼 터치는 되지만 이 조건에 안 걸리는 기기를 위해 상단바에
수동 활성화 버튼(`btn-gamepad`)도 뒀다 — 누르면 `history.replaceState`로 `?gamepad`를
URL에 추가한다(리로드 없이, 빈 파라미터는 `=`를 떼고 `?gamepad&debug`처럼 정리). 활성화된
게임패드는 `position: fixed; bottom: 0`으로 화면 하단에 고정되어 캔버스 위에 뜨는
형태고, 게임 페이지(`body:has(#canvas-wrap)`)는 `min-height` 강제를 풀어서 푸터 아래
빈 공간이나 스크롤이 안 생기게 한다(허브는 `min-height:100vh`를 유지한다).

상단바 접기(`btn-collapse`)는 모바일 전용 토글로, 상단바 우측(전체화면 버튼 자리)에
있고 클릭하면 `body.chrome-hidden`을 토글한다. 게임 화면 클릭과 안 겹치게 전용 버튼으로
만들었다. 접히면 `.top-bar`를 `height: 0; overflow: hidden`으로 클립해 자식 버튼째
숨기고, body 위 패딩과 캔버스 위 마진도 없애 캔버스를 화면 상단에 붙인다. 접기 버튼만
`position: fixed`로 클립을 벗어나 화면 상단 중앙에 남는다(chevron이 180도 회전). 원래
`#footer`·`.hint`는 미디어쿼리(`max-width:680px`)에서만 숨겨졌는데 `chrome-hidden` 자체엔
규칙이 없어서 접어도 안 사라지는 버그가 있었다 — suiko-web-v2에서 먼저 발견해 고친 걸
역이식했다.

전체화면(`btn-fullscreen`)은 `canvas-wrap`을 `requestFullscreen`하고, 진입 직후
`navigator.keyboard.lock(['Escape'])`로 ESC를 잠근다. 이 잠금이 걸리는 환경(Chrome/Edge +
보안 컨텍스트, 즉 localhost/HTTPS)에서는 짧게 누른 ESC가 게임으로 전달되어 게임 키가
유지되고, 전체화면 자체는 길게 눌러야 풀린다. 전체화면 중 ESC를 누를 때마다 안내
토스트를 띄운다(진입 시 1회만 보여주면 놓치기 쉬워서 매번 뜨도록 바꿨다). Safari·
Firefox처럼 미지원이거나 LAN IP처럼 비보안 컨텍스트에서는 `lock` 자체가 없거나
거부되므로 catch로 넘겨 원래 동작(짧은 ESC로 종료)을 그대로 둔다. 전체화면이 풀리면
`fullscreenchange`에서 `keyboard.unlock()`을 부른다. 전체화면 중 토스트는 캔버스가
`min(100vw,160vh)` 식으로 뷰포트에 비례해 커지는 것과 같은 축을 타야 해서 `em`이 아니라
`vmin`으로 스케일한다(`em`은 캔버스 확대량과 무관해서 커진 게 체감이 안 된다).

버튼 표시는 미디어쿼리로 나눈다.

| 버튼 | PC (hover+fine) | 터치 기기 | 비고 |
|------|-----------------|-----------|------|
| 게임패드 (`btn-gamepad`) | 숨김 | 표시 | 게임패드 활성 시 숨김 |
| 상단바 접기 (`btn-collapse`) | 숨김 | 표시 | 접힘 시 상단 중앙 고정 |
| 전체화면 (`btn-fullscreen`) | 표시 | 숨김 | — |
| 뮤트 (`btn-mute`) | 에뮬레이션 시작 후 표시 | 동일 | 접힘 시 같이 숨김 |

아이콘 버튼(`.btn-icon`)은 회색 채움 호버 없이 색만 바뀐다. 회색 채움 호버는
디스크 패널 메뉴 버튼에만 쓴다.

가로 모드 대응도 손이 좀 갔다. `@media (max-width: 680px)`만으로는 부족한 게, 폰을
가로로 눕히는 순간 폭이 680px를 쉽게 넘어서 이 규칙이 안 걸리고 고정 640×400 캔버스가
짧은 뷰포트에서 위아래로 잘린다. 그래서 `@media (orientation: landscape) and
(pointer: coarse)`를 따로 두고, 이 경우만 뷰포트 전체 높이를 기준으로 폭을 8:5 비율로
계산해 화면 전체가 보이게 했다(세로 모드는 기존 폭 기준 규칙을 그대로 쓴다). 이건
suiko-web-v2(640×480, 4:3)에서 비율만 8:5로 바꿔 역이식한 것이다. 갤럭시 폴드처럼
펼쳤을 때 화면비가 1:1에 가까운 기기는 이 높이 기준 폭(`100vh*8/5`)이 실제 뷰포트
폭을 넘어서 캔버스가 화면 밖으로 나가 버렸다("화면이 엄청 커짐"이라는 제보로 발견).
`width: min(100vw, calc(100vh*8/5))`, `height: min(100vh, calc(100vw*5/8))`로 양쪽을
다 clamp해서(전체화면 규칙과 같은 패턴) 해결했는데, 일반 폰(가로로 긴 화면)은 이
clamp가 안 걸려 기존과 동일하게 동작한다. 다만 이건 실기가 없어 로직 검증만 했고
실측 확인은 못 했다 — 문제가 다시 보고되면 먼저 의심할 지점이다.

세이브 관련해서는, `preRun`에서 `FS.stat()`으로 ROM 파일이 마운트됐는지 10ms 간격,
최대 2초까지 폴링한다. 첫 로드 시 `.data` 처리가 느릴 수 있어 단순
`setTimeout(0)`으로는 부족했다. 타임아웃되면 세이브 없이 원본으로 시작한다. 저장 토스트는
`saveDisk(s)`가 폴링 중 체크섬이 실제로 바뀐 걸 감지해 IDB에 쓴 직후 뜨는데,
`lastChecksum`을 부팅 직후(`postRun`)에 현재 디스크로 초기화해 둬서 첫 폴링에서
헛김이 뜨는 일은 없다. 다중 디스크(희담)는 디스크 여러 개 중 하나라도 바뀌면 호출당
토스트 1회만 뜨도록 `saved` 플래그로 취합한다(디스크마다 따로 뜨지 않게). 세이브
대상이 아닌 페이지(희담 오프닝)에는 이 로직 자체가 없다. 이 부분도 suiko-web-v2에서
역이식했다.

터치 기기에서는 CSS(`@media (hover: none), (pointer: coarse)`)로 전체화면 버튼을
숨기고, 풀스크린 상태에서는 게임패드가 `canvas-wrap` 바깥에 있어 안 보이는 게 의도된
동작이다.

---

## 태블릿 블루투스 키보드 문제 (미해결)

iPad에 블루투스 키보드를 물려 플레이하다가 앱을 백그라운드로 보내거나 다른 탭에 갔다
돌아오면 키보드 입력이 게임에 전달되지 않는 현상이 2026년 8월에 제보됐다. `document`에
`keydown` capture 리스너를 걸어 실기로 확인한 결과는 이렇다.

- 증상이 나타난 상태에서 `document`에 `keydown` 이벤트 자체가 전혀 도착하지 않는다
  (캡처 단계에서도 안 잡힌다).
- 같은 상태에서 브라우저 주소창엔 정상적으로 타이핑되고, 다른 웹페이지로 이동하면
  거기선 정상 동작한다 — 키보드도 OS도 블루투스 연결도 다 살아있고, 이 페이지의 콘텐츠
  영역만 입력 대상으로 인정을 못 받는 상태로 보인다.
- 화면을 터치하면(가상 게임패드 버튼 등, 위치는 무관해 보임) 풀리는 경우가 있었지만
  재현이 불안정했다 — 같은 방법이 다음번엔 안 먹히기도 했다.

`<canvas>`에 `tabindex="-1"`을 주고 `visibilitychange` 시점에
`canvas.focus({preventScroll:true})`를 호출해 봤지만 효과가 없었다. 스크립트로 만든
focus는 이 문제에 영향을 주지 못한다는 뜻이다.

iOS/iPadOS Safari가 탭에 복귀할 때 콘텐츠 프레임으로 실제 입력 포커스를 넘기지 못하는
것으로 추정되지만, 신뢰할 수 있는(trusted) 터치 제스처로도 재현이 불안정해서 페이지
스크립트로 확실히 재현하거나 고칠 방법을 못 찾았다. 탭 전환/홈 버튼/Split View 중
어느 쪽에서 더 자주 나는지 같은 단서가 더 없으면 이 상태로 보류한다.

---

## 새 타이틀 추가

단일 디스크 FDI(풍광전·쾌도전)는 `hukyou.html`을, 멀티 디스크 FDI(희담)는 `kitan.html`을,
HDI(포물장)는 `torimono.html`을 복사해서 시작하면 된다. 고칠 항목은 다음과 같다.

| 항목 | 내용 |
|------|------|
| `DISK` / `DISKS` | ROM 경로 (`/rom/<title>.fdi`) |
| `IDB_KEY` | 타이틀별 세이브 분리 키 |
| `document.title` | 타이틀명 |
| `logo` img src/height | `img/logo-<title>.png`, 높이 기준 (풍광전 42px, 희담 54px) |
| `s.src` | `<title>.js` |

멀티 디스크는 `Module.arguments`에 FDI 경로를 순서대로 넣고 preRun에서 전부 chmod한다.
다만 런타임 중 디스크를 바꿔 끼우는 건 안 된다 — NP2kai가 디스크를 내부 메모리에
캐싱해서 `FS.writeFile()`을 해도 무시되기 때문이다.

포물장처럼 HDI를 쓰는 게임은 FDI가 아니라 부팅 가능한 PC-98 HDD 이미지를 쓴다. np2kai
웹빌드의 커맨드라인 확장자 분기에 `.hdi`가 없어서 `Module.arguments`는 비워 두고,
preRun에서 번들 안 `np2kai.cfg`에 `HDD1FILE`을 주입해 SASI HDD로 마운트한다(이건 페이지
번들의 파일시스템 안에서만 벌어지는 일이라 공유 cfg 원본에는 영향이 없다). 인서트나
파티션 처리 상세는 `tools/TORIMONO.md`를 참고.

번들은 게임별 bios + ROM으로 `<title>.data`를 만들고, `emnp2kai_sdl2.js`를 복사해
`<title>.js`로 메타데이터를 교체하면 된다. 마지막으로 `index.html`에서 해당 항목의
`class="unavailable"`을 지우고 `<a href>`를 추가하고 badge를 `done`으로 바꾸면 끝.

---

## 알려진 이슈

| 이슈 | 상태 |
|------|------|
| ScriptProcessorNode deprecated (오디오) | 경고만 뜨고 기능은 정상 |
| 런타임 디스크 교체 불가 | NP2kai가 디스크를 내부 캐싱. `diskdrv_setfdd()` 등의 export가 필요 |
| 태블릿 블루투스 키보드, 백그라운드 복귀 후 입력 안 됨 | 위 절 참조. 미해결 |

---

## 자매 프로젝트 (suiko-web-v2)

`suiko-web-v2`(환세취호전, doswasmx 기반 Windows 95 에뮬레이터)는 이 프로젝트의 웹
에뮬레이터 UI를 바탕으로 만든 별도 리포다. 같은 사이트 계열(atah.io)에서 서빙되지만
공유 패키지나 서브모듈은 안 쓴다 — 둘 다 정적 사이트라 빌드 파이프라인을 만드는 비용이
그때그때 수동으로 이식하는 비용보다 크다고 판단했다(2026-07).

`style.css`와 `suiko-web-v2`의 `suiko-overrides.css`는 구조를 맞춰서 관리한다. 가로 모드
대응, 세이브 토스트, `chrome-hidden` 접기, 전체화면처럼 공용 UI/로직을 고칠 땐 다른 쪽에도
해당 사항이 있는지 확인해야 한다. 그대로 복사는 안 되고 그때마다 다음을 맞춰 조정해야
한다: 종횡비(이쪽 640×400=8:5, suiko는 640×480=4:3), DOM id(`#canvas-wrap` vs
`#canvasDiv`), 그리고 다중 디스크 여부·버튼 유무 같은 리포별 기능 적용 범위.
