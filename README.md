# 환세 시리즈(PC-98) 한글화

![License](https://img.shields.io/badge/license-MIT-blue) ![Platform](https://img.shields.io/badge/platform-PC--98-green)

Compile Inc.의 PC-98 환세 시리즈를 한국어로 번역하는 프로젝트. 텍스트 추출·재삽입 툴과 웹 에뮬레이터를 포함.

| 타이틀 | 폴더 | 상태 |
|--------|------|------|
| 환세풍광전 (幻世風狂伝, 1994) | `hukyou` | 번역 완료, 최종 검수 중 |
| 환세쾌도전 (幻世快盗伝, 1995) | `kaitou` | 미착수 |
| 환세포물장 (幻世捕物帳, 1996) | `torimono` | 미착수 |
| 환세희담 (幻世喜譚, 1995) | `kitan` | 미착수 |

## 웹 에뮬레이터 (`emulator/`)

NP2kai + Emscripten SDL2 빌드. 브라우저에서 패치 결과 즉시 확인.  
https://flvrdoyster.github.io/gensei-pc98/emulator

### 에뮬레이터 빌드

emsdk와 NP2kai 소스가 필요함.

```bash
source <emsdk_path>/emsdk_env.sh
make -C <NP2kai_path>/build_em emnp2kai_sdl2
cp <NP2kai_path>/build_em/emnp2kai_sdl2.{js,wasm} emulator/
```

기술 상세 및 세이브 지속성 구현 현황: [`emulator/NOTES.md`](emulator/NOTES.md)

## 파일 구조

```
tools/
  compile_lz.py        LZ 압축/해제 + SJIS 유틸 (공통)
  hukyou_parser.py     환세풍광전 텍스트 추출
  hukyou_inserter.py   환세풍광전 번역 재삽입
  editor.py            웹 번역 에디터 (http://localhost:8421)
  charmap.json         한글↔SJIS 매핑 (KS X 1001, 2350자)
  NOTES.md             역공학 분석 노트 (텍스트 태그 정의 포함)
original/
  hukyou/              환세풍광전 원본
  kaitou/              환세쾌도전 원본
  torimono/            환세포물장 원본
translation/
  hukyou/
    translation.json   환세풍광전 번역 파일 (JP/KR 쌍 + 오프셋)
build/                 (gitignore) 패치된 파일 출력
emulator/
  index.html           허브 페이지 (타이틀 목록)
  hukyou.html          환세풍광전 에뮬레이터
  style.css            UI 스타일
  gamepad.js           모바일 가상 게임패드
  img/                 로고 및 키캡 SVG 아이콘
  bios/                PC-98 BIOS 파일
  rom/                 게임 디스크 이미지
  emnp2kai_sdl2.*      NP2kai Emscripten 빌드 결과물
  NOTES.md             에뮬레이터 기술 노트
```

## 한글화 툴 사용법

프로젝트 루트(`gensei-pc98/`)에서 실행.

```bash
# 1. 텍스트 추출 (translation.json 생성)
python3 tools/hukyou_parser.py original/hukyou

# 2. 번역 에디터 (http://localhost:8421)
#    - 상단 도넛 차트: 번역 진행률 실시간 표시
#    - 태그 배지 클릭으로 분류 변경
#    - 필터: 타입/파일 드롭다운 + 미번역만/외자만/제외 포함 체크박스
#    - 검색창: JP/KR 텍스트 검색
#    - 바이트 열: KR 인코딩 길이/원문 길이 실시간 표시 (초과 시 빨간색)
#    - Cmd/Ctrl+S 로 저장, 빌드 버튼으로 build/ 출력
python3 tools/editor.py hukyou   # 또는 kaitou, torimono, kitan

# 3. 재삽입 (build/hukyou/ 에 패치된 파일 생성)
python3 tools/hukyou_inserter.py original/hukyou
```

텍스트 태그 정의 및 역공학 상세: [`tools/NOTES.md`](tools/NOTES.md)

## 크레딧

**에뮬레이터**: [NP2kai](https://github.com/AZO234/NP2kai) by AZO — MIT License

**번역 도구 및 웹 배포**: flvrdoyster

## 소프트웨어 고지

본 저장소는 환세 시리즈(幻世シリーズ)의 한국어 번역 패치를 위한 도구와 디스크 이미지를 포함합니다.

원본 게임은 Compile Inc.가 개발하였으며, 게임 자산(디스크 이미지, 그래픽, 음악 등)의 모든 권리는 원저작권자에게 있습니다.

본 프로젝트는 비상업적 보존 및 한글화 목적으로만 운영됩니다.

저작권자로서 자료 삭제를 원하실 경우 Issue를 열어주시면 즉시 대응하겠습니다.
