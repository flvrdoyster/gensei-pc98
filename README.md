# 환세 시리즈(PC-98) 한글화

![License](https://img.shields.io/badge/license-MIT-blue) ![Platform](https://img.shields.io/badge/platform-PC--98-green)

Compile Inc.의 PC-98 환세 시리즈를 한국어로 번역하는 프로젝트.  
텍스트 추출·재삽입 툴과 웹 에뮬레이터를 포함.

| 타이틀 | 폴더 | 상태 |
|--------|------|------|
| 환세풍광전 (幻世風狂伝, 1994) | `hukyou` | 번역 완료, 최종 검수 중 |
| 환세쾌도전 (幻世快盗伝, 1995) | `kaitou` | 번역 진행 중, 인서터 미구현 |
| 환세포물장 (幻世捕物帳, 1996) | `torimono` | 미착수 |
| 환세희담 (幻世喜譚, 1995) | `kitan` | 미착수 |

---

## 웹 에뮬레이터 (`emulator/`)

NP2kai + Emscripten SDL2 빌드. 브라우저에서 패치 결과 즉시 확인.  
https://flvrdoyster.github.io/gensei-pc98/emulator

```bash
# 에뮬레이터 빌드 (emsdk + NP2kai 소스 필요)
source <emsdk_path>/emsdk_env.sh
make -C <NP2kai_path>/build_em emnp2kai_sdl2
cp <NP2kai_path>/build_em/emnp2kai_sdl2.{js,wasm} emulator/
```

기술 상세: [`emulator/NOTES.md`](emulator/NOTES.md)

---

## 한글화 툴 사용법

프로젝트 루트(`gensei-pc98/`)에서 실행.

```bash
# 1. 텍스트 추출 (translation/<title>/translation.json 생성)
python3 tools/hukyou_parser.py original/hukyou   # 풍광전
python3 tools/kaitou_parser.py original/kaitou   # 쾌도전

# 2. 번역 에디터 (http://localhost:8421)
python3 tools/editor.py hukyou    # 풍광전
python3 tools/editor.py kaitou    # 쾌도전

# 3. 재삽입 (build/<title>/ 에 패치된 파일 생성)
python3 tools/hukyou_inserter.py original/hukyou
```

역공학 분석 상세: [`tools/NOTES_hukyou.md`](tools/NOTES_hukyou.md) · [`tools/NOTES_kaitou.md`](tools/NOTES_kaitou.md)

---

## 파일 구조

```
tools/
  pc98disk.py            PC-98 디스크 이미지 생성/편집 (FDI/HDI/IMG)
  compile_lz.py          LZ 압축/해제 + SJIS 유틸 (공통)
  editor.py              웹 번역 에디터 (localhost:8421)
  charmap.json           한글↔SJIS 매핑 (KS X 1001, 2350자)
  NOTES_hukyou.md        풍광전 역공학 노트
  NOTES_kaitou.md        쾌도전 역공학 노트
  hukyou_parser.py       풍광전 텍스트 추출
  hukyou_inserter.py     풍광전 번역 재삽입
  kaitou_parser.py       쾌도전 텍스트 추출
original/
  hukyou/                풍광전 원본 디스크 파일
  kaitou/                쾌도전 원본 디스크 파일
  torimono/              포물장 원본 디스크 파일
translation/
  hukyou/translation.json   풍광전 번역 파일 (JP/KR 쌍 + 오프셋)
  kaitou/translation.json   쾌도전 번역 파일 (JP/KR 쌍 + 오프셋)
build/                   (gitignore) 패치된 파일 출력
emulator/
  index.html             허브 페이지 (타이틀 목록)
  hukyou.html            풍광전 에뮬레이터
  style.css / gamepad.js UI 스타일 + 모바일 가상 패드
  bios/ rom/             PC-98 BIOS + 게임 디스크 이미지
  emnp2kai_sdl2.*        NP2kai Emscripten 빌드 결과물
  NOTES.md               에뮬레이터 기술 노트
```

---

## 크레딧

**에뮬레이터**: [NP2kai](https://github.com/AZO234/NP2kai) by AZO — MIT License  
**번역 도구 및 웹 배포**: flvrdoyster

---

## 소프트웨어 고지

본 저장소는 환세 시리즈의 한국어 번역 패치를 위한 도구와 디스크 이미지를 포함합니다.

원본 게임은 Compile Inc.가 개발하였으며, 게임 자산(디스크 이미지, 그래픽, 음악 등)의 모든 권리는 원저작권자에게 있습니다.

본 프로젝트는 비상업적 보존 및 한글화 목적으로만 운영됩니다.  
저작권자로서 자료 삭제를 원하실 경우 Issue를 열어주시면 즉시 대응하겠습니다.
