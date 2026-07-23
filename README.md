# PC-98 환세 시리즈 한글화

**▶ 바로 플레이: [pc98.atah.io](https://pc98.atah.io)**

## 개요

Compile이 PC-98로 발매한 환세 시리즈를 한국어로 번역하는 프로젝트.  
텍스트 추출 툴·재삽입 툴·번역 에디터 및 웹 에뮬레이터를 포함.

| 타이틀 | 폴더 | 번역 라인 | JP 글자수 | 상태 |
|--------|------|----------:|----------:|------|
| 환세풍광전 (幻世風狂伝, 1994) | `hukyou` | 2,436 | 21,743 | 완료 |
| 환세희담 (幻世喜譚, 1995) | `kitan` | 7,376 | 73,527 | 완료 |
| 환세쾌도전 (幻世快盗伝, 1995) | `kaitou` | 6,276 | 54,805 | 완료 |
| 환세포물장 (幻世捕物帳, 1996) | `torimono` | 13,930 | 127,183 | 완료 |

### 구성

+ **`tools/`** — 한글화 도구 모음.  
`compile_lz.py` · `compile_script.py` · `pc98disk.py`는 공통 라이브러리. 나머지는 타이틀별 파서·인서터와 공용 웹 에디터(`editor.py`).
+ **`original/`** — 원본 디스크에서 추출한 파일. 타이틀별 서브디렉토리로 구분 (저장소에는 없음, 로컬에 직접 준비 필요).
+ **`translation/`** — 번역 데이터. 파서가 생성하고 에디터가 읽고 쓰는 `translation.json`이 타이틀별로 있음. JP·KR 쌍 + 오프셋 정보를 담음.
+ **`emulator/`** — 웹 에뮬레이터. NP2kai + Emscripten SDL2 빌드.  
타이틀별 HTML 페이지 + JS/데이터 번들로 구성.  
`docs/`는 GitHub Pages 서빙용으로 `emulator/`를 그대로 복사한 것으로, `https://pc98.atah.io`에 배포됨.
+ **`build/`** — 인서터 출력 디렉토리. 패치된 파일이 여기에 생성.

### 작업 흐름

```
파서 → translation.json 생성
         ↓
      에디터 (번역 입력 · 저장)
         ↓
      인서터 → build/ 폴더에 패치 파일 생성
         ↓
      번들 생성 → emulator/ 폴더의 번들을 갱신
         ↓
      웹 에뮬레이터 또는 로컬 에뮬레이터로 확인
```

에디터는 번역 입력부터 재삽입·번들 생성까지 GUI로 처리할 수 있는 통합 도구.  
각 툴은 독립적인 Python 스크립트로도 사용 가능.

---

## 사용법

프로젝트 루트(`gensei-pc98/`)에서 실행. 아래 두 경로 모두 **원본 일본어 디스크 이미지** 필요.

> ⚠ 이 한글화는 한글 글리프를 새로 그려 넣은 전용 폰트 이미지(`emulator/bios/font.bmp`,
> 도깨비DNR고딕 Light)를 함께 사용해야 정상적으로 보인다. 디스크 이미지만 패치하고 원본
> 폰트 그대로 두면 한글이 깨지거나 안 보인다.

### 0. 원본 디스크 이미지에서 파일 추출 (공통, 최초 1회)

파서·에디터·인서터는 `original/<title>/`에 이미 **개별 파일로 추출된 상태**를 전제.

```bash
# 디스크 이미지(FDI/HDI) 안의 파일 목록 확인
python3 tools/pc98disk.py ls <원본이미지.hdi>

# 필요한 파일을 하나씩 추출 (일괄 추출 명령 없음 — ls 결과를 보고 반복)
python3 tools/pc98disk.py get <원본이미지.hdi> DISK_B.DAT original/torimono/DISK_B.DAT
python3 tools/pc98disk.py get <원본이미지.hdi> DISK_C.DAT original/torimono/DISK_C.DAT
# ...
```

타이틀별로 필요한 정확한 파일 목록·디스크 매수·이미지 포맷(FDI/HDI)은 각 기술 노트의 "파일 구성" 절 참조 — [`tools/HUKYOU.md`](tools/HUKYOU.md) · [`tools/KAITOU.md`](tools/KAITOU.md) · [`tools/KITAN.md`](tools/KITAN.md) · [`tools/TORIMONO.md`](tools/TORIMONO.md).

---

### A. 저장소의 번역 결과를 이미지에 적용하기

`translation/<title>/translation.json`은 이미 번역 완료 상태(위 표 참조). 직접 번역 없이 재삽입만 실행.

인서터는 재삽입한 파일들을 `build/<title>/`에 놓는 것과 별개로, 그 자리에서 바로 부팅 가능한
완성된 디스크 이미지도 만들어준다. 이를 위해 아래 이름 그대로 **자신이 준비한 원본 디스크 이미지의
사본**을 미리 두어야 한다 (파일명이 다르면 인식하지 못함):

| 타이틀 | 준비할 파일 | 비고 |
|---|---|---|
| 풍광전 | `emulator/rom/hukyou_kr.fdi` | 부팅 FDI 1장 |
| 쾌도전 | `emulator/rom/kaitou_kr.fdi` | 부팅 FDI 1장 |
| 희담 | `emulator/rom/kitan-system.fdi`<br>`emulator/rom/kitan-data.fdi`<br>`emulator/rom/kitan-demo.fdi` | 시스템·데이터·데모 FDI 3장 |
| 포물장 | `emulator/rom/torimono_kr.hdi` | 부팅 HDI 1장 |

```bash
# 재삽입 (0단계에서 채운 original/<title>/ 대상으로 바로 실행)
python3 tools/hukyou_inserter.py original/hukyou          # 풍광전 → build/hukyou/hukyou_kr.fdi
python3 tools/kaitou_inserter.py  original/kaitou         # 쾌도전 → build/kaitou/kaitou_kr.fdi
python3 tools/kitan_inserter.py  original/kitan/data      # 희담 본편 → build/kitan/kitan-{system,data}.fdi
python3 tools/kitan_demo_inserter.py original/kitan/data  # 희담 오프닝 → build/kitan-demo/kitan-demo.fdi
python3 tools/torimono_inserter.py original/torimono      # 포물장 → build/torimono/torimono_kr.hdi
```

`build/<title>/` 안에 생성된 이미지를 실기나 다른 PC-98 에뮬레이터에서 바로 사용.

#### 디스크 이미지 없이 패치 파일만 얻기

`emulator/rom/`에 이미지를 준비하지 않았거나 다른 이미지에 직접 적용하고 싶다면 `--no-fdi`로
디스크 이미지 생성을 끄고, `build/<title>/`에 나온 개별 파일을 원본 이미지 복사본에 직접 얹는다.

```bash
python3 tools/hukyou_inserter.py original/hukyou --no-fdi
python3 tools/kaitou_inserter.py  original/kaitou --no-fdi
python3 tools/kitan_inserter.py  original/kitan/data --no-fdi
python3 tools/kitan_demo_inserter.py original/kitan/data --no-fdi
python3 tools/torimono_inserter.py original/torimono --no-fdi
# build/<title>/ 에 패치된 CMD/DAT 파일만 생성 (디스크 이미지는 안 만듦)

cp <원본이미지.hdi> <패치이미지.hdi>   # 원본은 보존 권장
python3 tools/pc98disk.py add <패치이미지.hdi> build/torimono/DISK_B.DAT
python3 tools/pc98disk.py add <패치이미지.hdi> build/torimono/DISK_C.DAT
# ... build/<title>/ 안의 파일마다 반복 (희담은 GS.OVL·CMD류는 시스템 이미지, PARTY7.CMD는 데이터 이미지)
```

---

### B. 처음부터 번역 작업 직접 해보기

```bash
# 1. 텍스트 추출 
python3 tools/hukyou_parser.py original/hukyou        # 풍광전
python3 tools/kaitou_parser.py original/kaitou        # 쾌도전
python3 tools/kitan_parser.py  original/kitan/data    # 희담
python3 tools/torimono_parser.py original/torimono    # 포물장
# 추출 결과는 translation/<title>/translation.json 으로 생성 (기존 파일을 덮어씀 — 주의)

# 2. 번역 에디터 → http://localhost:8182
python3 tools/editor.py hukyou                        # 풍광전
python3 tools/editor.py kaitou                        # 쾌도전
python3 tools/editor.py kitan  original/kitan/data    # 희담
python3 tools/editor.py torimono                      # 포물장

# 3. 재삽입 (A와 동일 — emulator/rom/ 준비 여부에 따라 --no-fdi 여부 결정)
python3 tools/hukyou_inserter.py original/hukyou          # 풍광전
python3 tools/kaitou_inserter.py  original/kaitou         # 쾌도전
python3 tools/kitan_inserter.py  original/kitan/data      # 희담 본편
python3 tools/kitan_demo_inserter.py original/kitan/data  # 희담 오프닝
python3 tools/torimono_inserter.py original/torimono      # 포물장

# 4. 번역 검수 lint (미번역·잘림·깨진문자·일관성·offset 정합)
python3 tools/lint.py kaitou        # 요약 (-v 상세)

# 5. 로컬 에뮬레이터 확인 → http://localhost:9801
python3 -m http.server 9801 --directory emulator
```

---

## 기술 노트

역공학 분석 및 구현 상세:

- [`tools/HUKYOU.md`](tools/HUKYOU.md) — 풍광전
- [`tools/KAITOU.md`](tools/KAITOU.md) — 쾌도전
- [`tools/KITAN.md`](tools/KITAN.md) — 희담
- [`tools/TORIMONO.md`](tools/TORIMONO.md) — 포물장
- [`tools/NOTES.md`](tools/NOTES.md) — 한글화 도구
- [`emulator/NOTES.md`](emulator/NOTES.md) — 에뮬레이터

---

## 크레딧

**에뮬레이터**: [NP2kai](https://github.com/AZO234/NP2kai) by AZO — MIT License  
**게임 내 한글 폰트**: 도깨비DNR고딕 Light (도깨비디나루를 복원해 제작) by flvrdoyster  
**번역 도구 및 웹 배포**: flvrdoyster

---

## 소프트웨어 고지 / Software Notice

본 저장소는 환세 시리즈의 한국어 번역판을 브라우저 환경에서 실행하기 위한 도구를 포함합니다. 원본 디스크 이미지(`original/`)는 저작권상 저장소에 포함하지 않으며, 로컬에서만 사용합니다. 배포용 웹 에뮬레이터(`emulator/`·`docs/`)에는 한글화가 반영된 게임 데이터 번들이 포함됩니다.

원본 게임은 Compile이 개발하였으며, 게임 자산(그래픽, 음악 등)의 모든 권리는 원저작권자에게 있습니다.

본 프로젝트는 비상업적 보존 및 한글화 목적으로만 운영됩니다.
저작권자로서 자료 삭제를 원하실 경우 Issue를 열어주시면 즉시 대응하겠습니다.

This repository contains tools for running Korean-localized versions of the Gensei (幻世) series for the PC-98 in a browser. Original disk images (`original/`) are excluded from the repository for copyright reasons and are used locally only. The deployed web emulator (`emulator/`/`docs/`) includes the localized game data bundles.

The games were originally developed by Compile. All rights to the games and their assets (graphics, music, etc.) belong to their respective copyright holders.

This project exists solely for non-commercial preservation and Korean localization.
If you are a rights holder and would like this material removed, please open an issue and it will be promptly addressed.
