# 환세 시리즈 한글화 / 幻世シリーズ Korean Translation Patch

Compile Inc. PC-98 **환세 시리즈** 한글화 프로젝트.

| 타이틀 | 폴더 | 상태 |
|--------|------|------|
| 환세풍광전 (幻世風狂伝, 1994) | `hukyou` | 파서·삽입기 완료, 번역 진행 중 |
| 환세쾌도전 (幻世快盗伝, 1994) | `kaitou` | 미착수 |
| 환세포물장 (幻世捕物帳, 1995) | `torimono` | 미착수 |

## 파일 구조

```
tools/
  compile_lz.py        LZ 압축/해제 + SJIS 유틸 (공통)
  hukyou_parser.py     환세풍광전 텍스트 추출
  hukyou_inserter.py   환세풍광전 번역 재삽입
  editor.py            웹 번역 에디터 (http://localhost:8421)
  charmap.json         한글↔SJIS 매핑 (KS X 1001, 2350자)
  NOTES.md             역공학 분석 노트
original/
  hukyou/              환세풍광전 원본
  kaitou/              환세쾌도전 원본
  torimono/            환세포물장 원본
translation/
  hukyou/
    translation.json   환세풍광전 번역 파일 (JP/KR 쌍 + 오프셋)
build/                 (gitignore) 패치된 파일 출력
```

## 사용법

프로젝트 루트(`gensei-pc98/`)에서 실행.

```bash
# 1. 텍스트 추출 (translation.json 생성)
python3 tools/hukyou_parser.py original/hukyou

# 2. 번역 에디터 (http://localhost:8421)
python3 tools/editor.py

# 3. 재삽입 (build/hukyou/ 에 패치된 파일 생성)
python3 tools/hukyou_inserter.py original/hukyou

# CMD 파일 압축 해제본 저장 (분석용)
python3 tools/hukyou_parser.py original/hukyou dump
```

## 기술 개요

- **LZ 압축**: Compile社 공통. COM 자가 압축 + CMD 런타임 압축 동일 알고리즘
- **텍스트 인코딩**: Shift-JIS (가이지 0x85XX 영역 포함)
- **대화 마커**: `65 00 [SJIS lead]` (시작) / `6B` (종료)
- **메뉴 마커**: `13 00 [포인터 테이블]` (선택지 블록)
- **아이템 마커**: `0F 03` (시작)

자세한 내용은 `tools/NOTES.md` 참고.

## 라이선스

번역 데이터 및 도구 코드: MIT  
원본 게임 저작권: Compile Inc.
