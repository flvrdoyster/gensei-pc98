# 공통 도구 노트

---

## 로컬 서버 포트 규칙

| 용도 | 포트 | 연상 |
|------|------|------|
| 번역 에디터 (`editor.py`) | **8182** | JP(81) → KR(82) |
| 에뮬레이터 (`python3 -m http.server`) | **9801** | PC-9801 |

```bash
# 인자 없이 실행하면 터미널에서 대상 선택 (기본 타이틀로 열지 않는다)
python3 tools/editor.py

# 바로 지정 — <title> 또는 dashboard
python3 tools/editor.py <title>
python3 tools/editor.py dashboard    # 같은 포트, 편집 서버와 동시 실행 불가
# → http://localhost:8182

# 에뮬레이터 (프로젝트 루트에서 실행)
python3 -m http.server 9801 --directory emulator
# → http://localhost:9801
```

---

## 반각 한글 (halfwidth Korean)

좁은 슬롯(예: 풍광전 적 이름, 희담 아이템명 일부)에 들어가는 한글을  
PC-98 폰트의 반각 카나 영역(`0x85A4`부터)에 글리프 추가해서 처리.

### 인코딩 마커 `/X`

KR 텍스트에서 슬래시 1개 + **바로 다음 한 글자만** 반각으로 처리.  
여러 글자를 반각으로 하려면 각 글자 앞에 `/`를 붙여야 함.

```
'/리프레시워터'    → 리만 반각, '프레시워터'는 전각
'/리/프/레/시워터' → 리프레시 4자 반각, '워터' 2자 전각
'/Gold'           → G만 반각, 'old'는 전각으로 자동 변환
'/G/o/l/d'        → 전체 반각
```

charmap.json에 `/리: 85a4`, `/G: 8566` 형식으로 매핑.  
인서터(`hukyou_inserter.encode_korean`, `kitan_inserter.encode_korean_kitan`)가  
`/X` 시퀀스를 만나면 charmap에서 키 검색 → 있으면 반각 코드 출력, 없으면 일반 처리.

### 폰트 슬롯

`emulator/bios/font.bmp`의 `0x85XX` 영역은 PC-98 반각 카나 글리프 자리.  
JIS row 42 (s2 ≥ 0x9F, 94 슬롯)를 한글로 덮어써서 사용:

**한글 반각 영역**: `0x85A4~0x85FC` 와 `0x8645~0x867E` 범위. 실제 등록 글리프는 `charmap.json`(단일 소스)을 따르며, 중간에 게임이 출력하는 코드(`0x8640~0x8644` 등)는 비워 둔다.  
초성별 가나다순 영역으로 분할 (쌍자음은 자음과 통합):

| 초성 | 범위 | 슬롯 | 예시 |
|------|------|------|------|
| ㄱ(+ㄲ) | 0x85A4~0x85AD | 10 | 가, 거, 게, 그, 기 |
| ㄴ | 0x85AE~0x85B5 | 8 | 나, 노, 니, 닌 |
| ㄷ(+ㄸ) | 0x85B6~0x85C1 | 12 | 다, 데, 드, 디, ... |
| ㄹ | 0x85C2~0x85CD | 12 | 라, 레, 리, ... |
| ㅁ | 0x85CE~0x85D7 | 10 | 마, 머, 미, ... |
| ㅂ(+ㅃ) | 0x85D8~0x85E7 | 16 | 바, 베, 보, ... |
| ㅅ(+ㅆ) | 0x85E8~0x85F5 | 14 | 사, 서, 소, 시, ... |
| ㅇ | 0x85F6~0x8651 | 20 | 아, 어, 오, 우, 이, ... |
| ㅈ(+ㅉ) | 0x8652~0x8659 | 8 | 진, 즈, 져 |
| ㅊ | 0x865A~0x865D | 4 | 츠, 치 |
| ㅋ | 0x865E~0x8666 | 9 | 카, 케, 키, ... |
| ㅌ | 0x8667~0x866E | 8 | 타, 테, 토, ... |
| ㅍ | 0x866F~0x8678 | 10 | 파, 포, 푸, ... |
| ㅎ | 0x8679~0x867E | 6 | 헌, 헤, 후 |

- 영역 내는 가나다순 정렬, 영역 사이엔 여유 슬롯 있음 → 새 글자 추가 시 해당 초성 영역 빈 슬롯에 넣기
- 0x85 영역은 원본 반각 카나(`ヲ`, `ァ` 등)를 덮어씀
- 0x86 영역(low half)은 원래 일본어 폰트의 반각 글리프(잘 안 쓰는 한자/기호류)가 있던 곳. 게임이 텍스트로 안 쓰는 게 확인된 영역

ASCII 반각(`0x8540~0x859E`)은 게임 원본 폰트의 ANK 글리프를 그대로 사용 가능 →  
charmap에 `/0`, `/A`, `/G`, ... `/z` 형태로 ASCII printable 94자 전체 등록됨.

### 폰트 BMP 좌표 — SJIS → 셀 위치 (글리프 찾기·넣기)

`emulator/bios/font.bmp`는 2048×2048, 1bpp, **팔레트 0=잉크(검정) / 1=배경(흰색)**.  
전각·반각 **모두 16px 그리드**로 정렬되며, 반각은 셀의 **왼쪽 8px**만 사용.

**SJIS 코드 → 셀 위치 (이게 1차 방법. 픽셀 역산은 차선책):**

1. SJIS → JIS 구점 `(ku, ten)`:
   ```
   c1, c2 = sjis >> 8, sjis & 0xFF
   if c1 >= 0xE0: c1 -= 0x40
   c1 -= 0x81
   if c2 >= 0x80: c2 -= 1
   c2 -= 0x40
   ku  = c1 * 2 + c2 // 94 + 1
   ten = c2 % 94 + 1
   ```
2. 16px 셀: **`col = ku`,  `row = ten + 32`**
3. 픽셀 좌상단: `x = col * 16`,  `y = row * 16`  (반각 글리프는 x..x+7)

검증: charmap의 반각 글리프 전부 적중.  
예) `0x864f`(오) → ku 11 / ten 16 → (col 11, row 48) → 픽셀 **(176, 768)**.  
전각 한글이 cols 16~40(=ku 16~40) · rows 33~126(=ten 1~94)에 packed된 것과 같은 규칙이고,  
반각 한글은 ku 9~12 영역이라 col<16(전각 블록 왼쪽)에 위치.

> **⚠ 빈칸 ≠ 안전 슬롯.** 폰트 셀이 비어 있어도(잉크 0) 게임이 그 *SJIS 코드*를
> 출력하면(예: 스페이스로) 거기 글리프를 그리는 순간 인게임에 깨져 보인다.
> 실제 사고: `0x8640`은 폰트는 빈칸이지만 게임이 쓰는 코드라 `오`를 그렸다가
> 인게임 깨짐 → `0x864f`로 이동. **안전한 반각 한글 슬롯은 확정 블록
> `0x85A4~0x85FC` / `0x8645~0x867B` 안에서만** 잡을 것. 그 밖(예: `0x8640~0x8644`,
> 0x86 블록 시작부)은 게임이 출력하는 코드. 새 글리프 추가 후엔 **반드시 인게임 확인.**

**역방향(차선책)**: 폰트를 막 그린 직후 어느 셀인지 모를 때만,  
`git show HEAD:emulator/bios/font.bmp` vs 작업트리를 바이트 비교 → 바뀐 픽셀 좌표 → `//16`로 셀 역산.  
공식이 우선, diff는 사후 확인용.

### 글리프 작업

8×16 픽셀, **왼쪽 8픽셀에 한글 그리고 오른쪽 8픽셀은 비움**. 둥근모꼴 느낌으로 도트 직접 작업.

### 적용 절차

1. 적 이름/짧은 슬롯 entry에 `enemy` 태그 (풍광전 한정)
2. KR을 `/리/프/레/시` 형태로 변환 (스크립트)
3. 폰트 글리프 + charmap.json 업데이트
4. 인서터 빌드 → FDI 패치 → 번들 재생성

### 시각적 한계

NP2kai는 텍스트 plane을 dot-by-dot 출력 (글자 굵게 처리 옵션 없음).  
글자가 두꺼워 보이는 인상은 SDL2 픽셀 보간(`SDL_HINT_RENDER_SCALE_QUALITY=2`)  
영향. 텍스트만 sharp하게 만들 방법은 없고, 폰트 자체를 더 얇게 디자인하는 게 유일.

---

## editor.py — 번역 에디터

웹 기반 번역 GUI. 800px 고정 폭, 다크 테마. 포트 8182는 고정이라 **한 번에 하나만** 뜬다
(편집·대시보드 전환은 재기동).

```bash
python3 tools/editor.py             # 터미널 선택 UI (번호 또는 이름 입력, q=종료)
python3 tools/editor.py <title>     # 번역 편집 (hukyou|kaitou|torimono|kitan)
python3 tools/editor.py dashboard   # 4개 타이틀 빌드/번들/배포 대시보드
python3 tools/editor.py <title> --no-open   # 브라우저 자동 실행 끄기
```

인자 없이 실행하면 **임의의 기본 타이틀을 열지 않고** 선택지를 띄운다. 비-tty(파이프·CI)면
선택 UI 대신 사용법을 출력하고 종료코드 1 — 입력을 기다리며 멈추지 않는다.

기동하면 **브라우저가 자동으로 열린다**(`--no-open` 으로 끔). 이때 `serve_forever()` 를
메인 스레드에서 돌리면 브라우저가 연결 거부를 맞으므로, **서버를 데몬 스레드로 먼저 띄우고
브라우저를 연 뒤 `join()`** 한다 (font 리포 `scripts/editor_server.py` 와 같은 패턴).
포트가 이미 물려 있으면 트레이스백 대신 "이미 에디터가 떠 있는지 확인" 안내 후 종료코드 1.

빌드/번들/배포 실행 로직은 `tools/pipeline.py`(title 인자 받는 공용 함수)에 있고,
`editor.py`는 이걸 불러써 HTTP 라우팅만 담당한다. 편집 화면의 3버튼(빌드/번들/배포)과
대시보드는 같은 `pipeline.py` 함수를 공유하므로 동작이 갈릴 일이 없다.

### 단축키

| 키 | 동작 |
|----|------|
| `Ctrl+S` | 저장 |
| `Ctrl+D` | 마지막 편집 행으로 점프 |
| `[` / `]` | 초과(over) 행 이전/다음 |

모두 `Ctrl`만 인식 (Mac의 `Cmd`는 브라우저 기본 동작에 양보).  
한글 IME 켜진 상태에서도 동작 (키 매칭에 `e.code` 사용).

### 멀티 선택

행 클릭으로 시작점 지정, 다른 행 클릭으로 범위 선택.  
하단 bulk-bar에 카운트 + 액션 버튼 표시.

- `JP 복사` / `KR 복사` — 선택된 행 텍스트를 개행으로 join해서 클립보드 복사
- 모드 토글(태그/화자) + 적용/취소 — 한 번에 하나만 적용(아래 화자별 검수)

### 화자별 검수 (entries 포맷 — 쾌도전·포물장)

화자별로 대사를 모아 보이스톤 일관성을 본다. `translation.json` 은 건드리지 않고 화면에서
화자를 파생 계산(`computeSpeakers`)하며, **수동 지정만** `line.speaker` 로 저장된다.
dialogs/items/ui 포맷(풍광전·희담)에선 비활성(드롭다운·모드 토글 숨김).

**자동 귀속 우선순위**: 수동 지정 > `char` 태그 > speaker 엔트리 첫 줄 >
휴리스틱(짧은 비-「 줄 + 다음 줄이 「 → 이름줄). 비-대사 태그(아이템·메뉴·적·시스템·전투·장소·컷씬)는
그룹핑에서 제외(미상에도 안 잡힘).

- **화자 없는 「는 미상**: 새 엔트리가 이어지는 줄(선행 전각공백)이 아니면 현재화자를 만료시켜,
  이름표 없이 「로 시작하는 블록을 이전 화자에 오귀속하지 않는다. 진짜 이름줄은 자기 「와 같은
  엔트리에 있어(`手下`+`「お頭`) 이 리셋에 안 깨진다.
- 툴바 `화자` 드롭다운으로 한 화자만 필터(`(미상)` 은 맨 끝).
- bulk-bar 모드 토글로 **태그 지정과 화자 지정을 분리**. 화자 입력칸: 이름 입력/선택 = 귀속,
  `(미상)` = 강제 미상, 빈칸 = 지정 해제(자동 복귀).
- 수동 지정은 `<title>_parser.py` 재실행 시 kr·tag 와 함께 보존된다(merge 이식).

### 검색

상단 검색바에서 JP/KR 부분 일치, 완전 일치 토글 가능.  
완전 일치 모드에서는 매칭된 모든 행에 같은 KR을 한 번에 채우는 "전체 적용" 표시.

### 빌드 / 번들

파이프라인 3단계 버튼(역할별, 상세는 hover tooltip):
- `빌드` — 인서터 실행, 번역을 디스크 이미지에 삽입 (`build/`).
- `번들` — `emulator/<title>.data` 재생성 (emsdk 환경 필요).
- `배포` — `deploy-docs.sh` 실행(emulator→docs 동기화 + 정합 검사). 결과 토스트, 커밋·버전 미변경.

보통 `빌드 → 번들 → 배포` 순. 타이틀 하나만 왕복할 땐 이 3버튼으로 충분 — 여러 타이틀을
한꺼번에 처리하려면 아래 대시보드 참조.

빌드 시 `lint.py` 빠른 검사(깨진문자·일관성)가 자동 실행돼 토스트에 합산 표시.
깨진문자·잘림이 있으면 토스트가 경고색으로 바뀜.

### 입력 보조 — 시리즈 용어집 placeholder

빈 KR 칸의 placeholder 에 **시리즈 전 타이틀에서 같은 원문의 기존 번역**을
`번역 (풍/희/쾌)` 형식으로 제시 (`/api/series-glossary`).

- 매칭은 **정규화 일치**: 공백·약물·괄호 등 특수문자를 제거하고 글자(가나·한자·영숫자)만
  비교. 정규화 문자 범위는 `lint.py _norm_jp` ↔ editor `normJp()` 가 반드시 일치해야 함.
- 현재 타이틀 번역 우선, 없으면 타 타이틀 번역 제안 (`series_glossary` 가 현재 타이틀을
  마지막에 덮어써 우선권 부여 — `SERIES_TITLES` 에 모든 타이틀이 들어 있어야 자기 번역도 잡힘).
- 신규 타이틀 착수 시 시스템 정형구(전투 메뉴·주문·아이템 획득문 등)가 자동 제안되는 효과.
- **빈 KR 칸의 Byte(길이) 칸을 클릭하면** 그 제안이 KR 에 바로 채워진다 (출처 표기 `(풍)` 등은
  빼고 번역 텍스트만). 주입 후 일반 입력과 동일 경로를 타 변경 추적·길이 갱신됨.

### 대용량 대응

전 행을 DOM 에 렌더하고 가상화는 없다. 행 수가 만 단위(포물장 ~1.4만 행)면
`rowKey(type:file:offset)→row` 조회가 병목이 된다. **`rowIndex` Map 을 적재 후 1회 구축**해
입력·클릭·저장의 행 조회를 O(1) 로, 저장 후처리도 변경된 행만 `tr[data-key]` 로 콕 집어
갱신한다(전체 행 순회 금지). 이 Map 없이 선형 탐색하면 저장이 O(N²) 로 수 초씩 멈춘다.

### 대시보드 (`dashboard` 모드)

`python3 tools/editor.py dashboard` — 4개 타이틀의 빌드/번들/배포 상태를 한 화면에서.

- **4단계 상태**: `translation.json → build/ → emulator/*.data → docs/` 각 단계를
  mtime(빌드·번들) / 파일 비교(배포)로 판정해 `미빌드`·`빌드 필요`·`빌드됨` 식 배지로 표시.
  희담은 데모 디스크(`kitan-demo.fdi`) 존재 여부를 별도 표시(없어도 빌드 실패로 안 봄 —
  오프닝 미번역이면 정상).
- **번들 신선도엔 공용 입력(폰트 등)도 들어간다**: `번들` 단계는 타이틀별 `build/<t>/` 디스크
  뿐 아니라 `emulator/bios/*`(`_bundle_shared_input_paths()`)도 같이 비교한다.
  `_repackage_bundle` 이 실제로 매번 `bios/` 전체를 통째로 챙겨 패키징하기 때문 — 이걸
  안 보면 **어느 타이틀의 build/ 도 안 바뀌었지만 폰트만 바뀐 경우**, 4개 타이틀 `.data`
  전부 구식 폰트를 담은 채인데도 `번들됨`으로 잘못 표시된다(실사고로 발견).
- **공용 파일 행**: `version.js`·`audio.js`·`bios/` 등은 어느 타이틀에도 안 묶이는데
  `deploy-docs.sh` 는 `cp -r emulator/*` 로 통째 복사한다. 타이틀 배지만 보면 **버전만 올린
  배포를 통째로 놓치므로**, 타이틀별 `<t>.data`/`<t>.js` 를 뺀 나머지 전체를 따로 비교해
  어긋난 파일명을 나열한다 (`pipeline.shared_status()`).
- **타이틀별 빌드/번들 버튼** + **전체 빌드+번들**(변경된 타이틀만 클라이언트가 순차 호출,
  실패하면 그 자리에서 중단). 서버에 배치 엔드포인트는 없음 —
  `HTTPServer` 가 단일 스레드라 서버측 배치는 진행 중 서버 전체를 블록시킨다.
- **배포**는 페이지에 하나(= `deploy-docs.sh` 가 원래 전 타이틀을 한 번에 처리). 빌드 신선도
  경고로 막힐 타이틀이 있으면 미리 배지에 표시하고, `-f` 강제 배포 버튼을 노출한다.
- **실행 로그** 패널(접이식) — 인서터·file_packager·deploy 원문 출력을 그대로 보존.
- **커밋**: `translation/`·`emulator/`·`docs/` 안의 git 변경 파일 목록 + 자동 작성된 커밋
  메시지 초안을 보여준다(수정 가능한 textarea). 변경이 있을 때만 바(bar)가 뜬다.
  **스코프는 이 세 디렉토리로 고정** — `tools/` 등 다른 작업 중인 코드 변경은 절대 같이
  안 실린다(`pipeline.COMMIT_SCOPE`). 메시지 초안은 타이틀별로 어느 단계까지 갔는지
  (`번역 작업` < `빌드 갱신` < `번역 반영 및 배포`) 보고 조합한다 — 완벽할 필요는 없고
  출발점만 되면 됨. 스테이징된 게 없으면(빈 커밋 방지) 실패로 응답.
  - 타이틀 이름에서 `환세` 접두어는 뗀다(`_short_title`) — 시리즈 전체가 공유하는
    접두어라 나열하면 반복일 뿐. 배지 등 다른 표시는 `TITLES` 원본(`환세풍광전` 등) 그대로.
  - `translation.json` 이 바뀐 타이틀은 `git diff HEAD` 에서 실제로 바뀐 `kr` 줄 수를
    세어 `"{타이틀} {N}줄 ..."` 로 붙인다(`_count_changed_kr`). 포맷이 한 줄에 `"kr"`
    하나(pretty-printed)라 `+`로 시작하는 `"kr":` 줄 개수 = 교체·신규 채움 건수와 일치.
- API: `GET /api/pipeline/status`(`{titles, shared}`), `GET /api/pipeline/commit-status`,
  `POST /api/pipeline/{build,bundle,deploy}?title=<t>`, `POST /api/pipeline/commit`(body
  `{message}`) — 전부 dashboard 모드 전용 라우트, 편집 모드의 `/api/build` 등과는 별개.
- 실행 중 잠금은 `busy` 플래그 + `syncButtons()` 로 관리한다. **`render()` 가 행을 다시
  그리므로 버튼의 `disabled` 를 직접 켜면 배치 도중 되살아난다** — 고유 비활성은
  `data-off` 속성으로만 표시하고 최종 `disabled` 는 `syncButtons()` 가 `busy` 와 합쳐 계산.

---

## pipeline.py — 빌드/번들/배포 공용 모듈

`editor.py`(편집 모드 3버튼)와 `dashboard` 모드가 공유하는 순수 함수. 전부 `title` 인자를
받고 `{ok, message, output, warnings, ...}` dict 를 반환 — HTTP 응답은 호출자가 쓴다.

| 함수 | 역할 |
|------|------|
| `build(title)` | 인서터 실행 (`<title>_inserter.py`) + `lint.analyze` 빠른 검사 |
| `bundle(title)` | `build/` 디스크 → `emulator/rom/` 복사 → `file_packager` 로 `emulator/<title>.data` 재생성. 희담은 데모 인서터 선행(실패해도 `warnings`로만 보고, 계속 진행) |
| `deploy(force=False)` | `deploy-docs.sh` 실행 (`force`→`-f`) |
| `status()` | `{titles: {t: 4단계+deploy_blocked}, shared: 공용 파일 동기 여부}` |
| `shared_status()` | 타이틀별 `<t>.data`/`<t>.js` 를 뺀 나머지 `emulator/` 전체의 docs 동기 여부 |
| `_bundle_shared_input_paths()` | `emulator/bios/*`(폰트 등, `font_jp.bmp` 제외) — 모든 타이틀 번들에 공통으로 들어가는 입력. `_repackage_bundle` 의 복사 필터와 반드시 동일해야 함 |
| `predict_deploy_block(title)` | `deploy-docs.sh` 0단계(git-clean 스킵 + mtime)를 파이썬으로 재현 — 배포 전에 막힐 타이틀을 미리 예측 |
| `_count_changed_kr(rel_path)` | `translation/<t>/translation.json` 의 `git diff HEAD`에서 실제로 바뀐 `kr` 줄 수 (커밋 메시지 초안용) |
| `commit_status()` | `COMMIT_SCOPE`(`translation/`·`emulator/`·`docs/`) 안의 git 변경 파일 + 자동 메시지 초안 |
| `commit(message)` | 위 스코프만 `git add` 후 커밋. 스코프 밖은 절대 add 하지 않음. 스테이징 없으면 실패 응답(빈 커밋 방지) |

타이틀별 함수 하나씩 있던 걸 통합한 게 아니라, 애초에 `_repackage_bundle` 은 이미 title
인자를 받고 있었다 — editor.py 가 응답 작성(`_send_json`)과 로직을 한 메서드에 섞어뒀던
걸 분리한 것에 가깝다.

**실패 응답 규약**: `bundle()` 은 실패 시 `code`(400=빌드 결과 없음 / 500=복사·번들 실패)를
같이 반환한다. 편집 모드 `/api/emulator-update` 는 이걸 `_send_json_error(msg, code)` 로
바꿔 **기존 규약(실패 400·500 + `{message}`, 성공 200 + `{ok, message}`)을 그대로 유지**하고,
대시보드 라우트는 `output`·`warnings` 까지 담은 dict 를 200 으로 그대로 넘긴다.

파일 동기 판정(`_synced`)은 `cp -r` 특성상 동기 상태면 dst mtime ≥ src mtime 이라는 점을 이용해
**크기+mtime 으로 먼저 거르고**, 어긋날 때만 내용을 전수 비교한다 (수 MB `.data` 4개를 매번
읽지 않으려고).

---

## lint.py — 번역 검수 lint

translation.json 의 품질 문제를 한 번에 점검. 검사 항목은 파일 docstring 참조.

```bash
python3 tools/lint.py <title>      # 요약 (-v 상세)
```

- **버그류**(잘림·깨진문자·offset 어긋남·선행 글자 누락)가 있으면 종료코드 1
  → 빌드/배포 게이트로 사용 가능.
- 미번역·일관성(같은 jp 에 다른 kr)은 검수 정보로만 리포트.
- offset 정합 검사는 원본 디컴프가 필요해 무겁다 — editor 빌드 통합 호출은
  `analyze(title, check_offset=False)` 빠른 모드.
- `iter_lines()` 가 타이틀별 json 포맷 차이(entries / dialogs·items·ui)를 흡수.
  단 잘림·offset 등 본검사는 현재 entries 포맷(쾌도전·포물장)만 지원.

---

## deploy-docs.sh — docs 배포 동기화·검사

`emulator/` → `docs/` 복사 + 배포 정합 검사. **커밋·버전은 건드리지 않는다** (검사만).

```bash
./tools/deploy-docs.sh        # 신선도 → 복사 → 정합 검사
./tools/deploy-docs.sh -f     # 빌드 신선도 경고 무시하고 진행
```

- **0) 빌드 신선도**: `translation/<title>/translation.json` 과 `emulator/<title>.data` 가 둘 다
  커밋된(clean) 타이틀은 일관 가정해 스킵, 작업 중인 타이틀만 mtime 비교 — json 이 번들보다
  최신이면 "편집 후 빌드 안 함"으로 보고 복사 전에 중단(`-f` 로 우회). git+mtime 혼합이라
  단순 touch(내용 동일)나 커밋 완료분은 오탐하지 않는다.
- **1) 복사** → **2) docs↔emulator 동일성** → **3) `<title>.js` remote_package_size ↔ `<title>.data` 크기**.
- 하나라도 어긋나면 종료코드 1. CLAUDE.md docs 배포 체크리스트를 코드로 박은 것.
- 대시보드의 `배포` 버튼(`pipeline.deploy()`)이 이 스크립트를 그대로 호출한다. `-f`도
  대시보드에서 (배포 차단이 예측된 경우에만) 버튼으로 노출됨 — 터미널 없이도 가능.

---

## compile_lz.py — Compile LZ 압축 / 해제

희담·풍광전의 CMD·OVL·실행 파일에 쓰이는 Compile 자체 LZ 알고리즘.

### 포맷

```
literal run : header (1B, 1~127) + N bytes
back-ref    : header (0x80 | (length-3)) + (dist-1)
              → length 3~130, dist 1~256
terminator  : 0x00
```

### 압축 알고리즘

`compress()` 는 **optimal parsing (DP)** 사용.

- `dp[i]` = `data[i:]` 압축 최소 출력 byte 수
- 각 위치에서 literal run (길이 1~127) vs match (길이 3~130) 중 minimum cost 결정
- Literal run 헤더 오버헤드(1B per run)까지 cost 에 정확히 반영
- 매치 비용은 dist 와 무관(2B 고정)이라, 각 위치에서 **최장 매치 하나 + 그 dist** 만 구하면 길이 k=3..best 를 전부 커버. dist 별 전수 기록 불필요
- 매치 탐색은 ml 이 max_len 에 도달하면 조기 종료(`break`) — 반복 패턴이 많은 데이터(코드·0x00 패딩이 섞인 OVL 등)에서 dist 전수 탐색의 데이터 의존 폭발을 막는다

Greedy 대비 더 압축하면서, 위 최적화로 압축 결과는 그대로 두고 속도만 크게 단축. 무손실은 전 타이틀 압축 파일 round-trip + 바이트 동일성으로 검증됨.

### 반각 디코드 — `read_sjis_char` 와 탁점 카나

`0x85 XX` 는 PC-98 반각 폰트 영역.
- `XX < 0x9F`: 반각 영숫자/기호 → `chr` 직변환
- `0x9F ≤ XX ≤ 0xDE`: 표준 반각 카나(`_HW_KANA`, 64자)
- **`0x85E3~0x85FC`: 탁점/반탁점 합성 카나(`ヴ ガ~ポ`)** — JIS X 0201 에 없어 cp932 로는 U+FFFD. `_HW_DAKUTEN` 매핑으로 디코드. 폰트 BMP 셀 판독으로 확정한 PC-98 공통 배열이며 게임 고유 아님.

> 누락 사례: 희담 적 이름 `カルニヴェアン`(카르니베안) 등이 `ヴ` 때문에 U+FFFD → 파서 노이즈 필터(U+FFFD 제거)가 엔트리째 버려 미파싱. 테이블 확장으로 해소.

미지 반각 코드 판독: 원본 일본어 폰트 `emulator/bios/font_jp.bmp` 에서 해당 셀(SJIS→셀 좌표 공식)을 잘라 글리프를 눈으로 확인. (작업본 `font.bmp` 는 한글이 덮여 원본 글리프 확인 불가)

### 슬롯 초과 처리 (희담)

희담의 SC*.CMD 는 FDI 안 DISK_B 아카이브의 **고정 크기 슬롯**에 들어가며, 압축 결과가 슬롯 초과 시 `patch_fdi` 가 해당 파일을 스킵하고 경고 출력. 초과 byte 가 크지 않으면 (수십 byte) 보통 검수가 진행될수록 KR 이 짧아져 자연스럽게 해소됨. 그래도 안 들어가면 해당 파일의 KR 을 직접 줄여야 함.

---

## compile_script.py — 공유 스크립트 워커

환세 시리즈 공통 **오피코드 스트림 파서**. 디컴프레스된 청크/CMD를 바이트 스트림으로
워킹해 텍스트를 추출한다. 희담 `kitan_parser.extract_dialogs`에서 검증된 모델을 일반화한
것으로, **쾌도전·포물장이 사용**한다 (포물장은 BASE_SPEC 무수정으로 동작 확인).

### 핵심 원칙

- **오피코드를 인자 길이만큼 정확히 소비** → 어디가 텍스트고 어디가 제어/인자/그래픽인지
  애초에 헷갈리지 않는다. 인자 바이트가 우연히 SJIS 쌍을 이뤄도 텍스트로 오인하지 않음.
- 따라서 **사후 노이즈 필터가 필요 없다.** 찌꺼기가 나오면 그건 *오피코드 모델이 불완전하다는
  신호* → 필터가 아니라 이 파일(모델)을 고친다. (쾌도전 구파서의 노이즈 필터가 진짜 대사
  534개를 학살한 게 교훈.)

### 사용

```python
from compile_script import walk, BASE_SPEC
blocks = walk(decompressed_bytes)            # 기본 스펙
# blocks: [{'type', 'offset', 'lines': [{'offset', 'jp'}]}]
```

### ScriptSpec (타이틀별 설정)

블록 내부 오피코드 처리는 공통 베이스, **타이틀마다 다를 수 있는 부분만 설정**으로 둔다:

| 필드 | 의미 |
|------|------|
| `openers` | 블록을 새로 여는 오피코드 시퀀스 → 종류 (`6b 00`·`6e 00 67 01`·`62 00`·`6d 08`) |
| `markers` | 블록 밖에서 SJIS 직전에 와 본문 시작을 알리는 시퀀스 (`01 02`·`76 1a`·`02 65`) |
| `skip_opcodes` | `[opcode]→길이`. 인자 통째로 건너뜀 (`6a 01`=4·`64 00`=4·`81 65`=2) |
| `break_lead` | 줄 구분자 lead (`72`·`73`·`76`) |
| `min_chars` | 줄 최소 글자수. **1이면 `「`·단일글자까지 전부 캡처(완전 파싱)** |
| `implicit_text` | 오프너 없는 2자+ SJIS 런을 텍스트로 암묵 재진입 (포인터 테이블 참조 맵 대화) |

### 새 타이틀 추가 절차

1. `BASE_SPEC` 그대로 `walk()` 시도.
2. 안 잡히는 블록이 있으면 그 타이틀의 오프너/마커를 Spec에 추가(override).
3. 새 오피코드(인자 길이)가 보이면 `skip_opcodes`에 추가.
4. **타이틀별 차이 주의**: 같은 회사 게임이라 대체로 공유되지만, 인자 길이가 다를 수
   있음(예: 쾌도전 `65`는 1바이트 종료자). 데이터로 검증하며 reconcile.

### 비-스크립트 데이터

gsovl 고정 오프셋 테이블, 아이템 정의 등 **오피코드 스트림이 아닌 구조**는 워커 대상이
아니다. 타이틀별 파서에서 따로 처리한다(희담 gsovl·items 등).

---

## pc98disk.py — PC-98 디스크 이미지 도구

Editdisk 대체. FDI/HDI/IMG 생성·편집을 CLI에서 수행.

### 지원 포맷

| 타입 | 설명 | FAT |
|------|------|-----|
| `fdi-2hd` | 2HD 플로피 (77C/2H/8S, 1024B/sec) | FAT12 |
| `hdi-20mb` | HDD 20MB (615C/4H/17S, 512B/sec) | FAT16 |
| `hdi-40mb` | HDD 40MB (615C/8H/17S, 512B/sec) | FAT16 |
| `hdi-80mb` | HDD 80MB (1024C/8H/17S, 512B/sec) | FAT16 |

기존 이미지 열기 시 Anex86 FDI 헤더 유무를 자동 감지. 헤더 없는 raw FDI도 지원.

### 사용법

```bash
# 빈 디스크 생성
python3 tools/pc98disk.py create output.fdi -t fdi-2hd
python3 tools/pc98disk.py create output.hdi -t hdi-40mb

# 파일 목록
python3 tools/pc98disk.py ls image.fdi

# 파일 추가 (동명 파일 존재 시 자동 교체)
python3 tools/pc98disk.py add image.fdi ./local_file.dat DEST.DAT

# 파일명 생략 시 로컬 파일명 그대로 사용
python3 tools/pc98disk.py add image.fdi ./MSG.DAT

# 파일 추출
python3 tools/pc98disk.py get image.fdi STAGE1.CMD ./out/STAGE1.CMD

# 파일 삭제
python3 tools/pc98disk.py delete image.fdi OLD.DAT
```

### 라이브러리 사용

```python
from tools.pc98disk import DiskImage

# 생성
img = DiskImage.create("game.fdi", "fdi-2hd")
img.add_file("DATA.BIN", data_bytes)
img.save()

# 기존 이미지 편집
img = DiskImage.open("game.fdi")
img.add_file("MSG.DAT", new_data)     # 추가 또는 교체
data = img.read_file("STAGE1.CMD")    # 추출
img.delete_file("OLD.DAT")            # 삭제
entries = img.list_files()             # 목록
img.save()
```

### PC-98 파티션 HDI 지원

부팅 가능한 PC-98 HDD 이미지(섹터0 IPL + 섹터1 파티션 테이블)는 섹터0이 BPB가 아니라
종전에는 non-FAT 으로 처리됐다. `open()` 이 파티션 테이블을 스캔해 **첫 FAT 파티션**을
자동 인식하며, ls/add/get/delete 가 파티션 안에서 동작한다 (포물장 `torimono_kr.hdi`).

- FAT 파라미터는 디스크 CHS가 아니라 **파티션 BPB 자체 값**(섹터 크기·총 섹터)으로 계산
- 모든 FAT/디렉토리 오프셋에 파티션 베이스(`part_base`)가 가산됨 — 읽기와 쓰기 모두.
  (쓰기 한쪽만 베이스를 빠뜨리면 IPL 뒤 빈 영역에 기록돼 조용히 유실된다 — 실제 겪은 버그)
- IPL·파티션 테이블 영역은 건드리지 않음 (부팅 보존)

### 제약 사항

- 루트 디렉토리만 지원 (서브디렉토리 미구현)
- 8.3 파일명만 지원 (LFN 없음)
- non-FAT 이미지는 목록 조회만 가능 (파일 추가/추출 불가)
- 파티션 HDI는 첫 FAT 파티션만 대상 (다중 파티션 미지원)
