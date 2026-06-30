# 환세 시리즈(PC-98) 한글화

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
+ **`original/`** — 원본 디스크에서 추출한 파일. 타이틀별 서브디렉토리로 구분.
+ **`translation/`** — 번역 데이터. 파서가 생성하고 에디터가 읽고 쓰는 `translation.json`이 타이틀별로 있음. JP·KR 쌍 + 오프셋 정보를 담음.
+ **`emulator/`** — 웹 에뮬레이터. NP2kai + Emscripten SDL2 빌드.  
타이틀별 HTML 페이지 + JS/데이터 번들로 구성.  
`docs/`는 GitHub Pages 서빙용으로 `emulator/`를 그대로 복사한 것으로, `https://pc98.atah.io`에 배포됨.
+ **`build/`** — 인서터 출력 디렉토리 (gitignore). 패치된 파일이 여기 생성됨.

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
      로컬 에뮬레이터로 확인
```

에디터는 번역 입력부터 재삽입·번들 생성까지 GUI로 처리할 수 있는 통합 도구.  
각 툴은 독립적인 Python 스크립트로도 사용 가능.

---

## 사용법

프로젝트 루트(`gensei-pc98/`)에서 실행.

```bash
# 1. 텍스트 추출 
python3 tools/hukyou_parser.py original/hukyou        # 풍광전
python3 tools/kaitou_parser.py original/kaitou        # 쾌도전
python3 tools/kitan_parser.py  original/kitan/data    # 희담
python3 tools/torimono_parser.py original/torimono    # 포물장
# 추출 결과는 translation/<title>/translation.json 으로 생성

# 2. 번역 에디터 → http://localhost:8182
python3 tools/editor.py hukyou                        # 풍광전
python3 tools/editor.py kaitou                        # 쾌도전
python3 tools/editor.py kitan  original/kitan/data    # 희담
python3 tools/editor.py torimono                      # 포물장

# 3. 재삽입 
python3 tools/hukyou_inserter.py original/hukyou          # 풍광전
python3 tools/kaitou_inserter.py  original/kaitou         # 쾌도전
python3 tools/kitan_inserter.py  original/kitan/data      # 희담 본편
python3 tools/kitan_demo_inserter.py original/kitan/data  # 희담 오프닝
python3 tools/torimono_inserter.py original/torimono      # 포물장
# 재삽입 결과는 build/<title>/ 에 같은 파일 이름으로 생성

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
**번역 도구 및 웹 배포**: flvrdoyster

---

## 소프트웨어 고지 / Software Notice

본 저장소는 환세 시리즈의 한국어 번역판을 브라우저 환경에서 실행하기 위한 도구와 디스크 이미지를 포함합니다.

원본 게임은 Compile이 개발하였으며, 디스크 이미지에는 게임 실행에 필요한 추가 시스템 소프트웨어가 포함될 수 있습니다. 게임 자산(디스크 이미지, 그래픽, 음악 등)의 모든 권리는 원저작권자에게 있습니다.

본 프로젝트는 비상업적 보존 및 한글화 목적으로만 운영됩니다.
저작권자로서 자료 삭제를 원하실 경우 Issue를 열어주시면 즉시 대응하겠습니다.

This repository contains tools and disk images for running Korean-localized versions of the Gensei (幻世) series for the PC-98 in a browser.

The games were originally developed by Compile. The disk images may include system software required to run them. All rights to the games and their assets (disk images, graphics, music, etc.) belong to their respective copyright holders.

This project exists solely for non-commercial preservation and Korean localization.
If you are a rights holder and would like this material removed, please open an issue and it will be promptly addressed.
