# 환세풍광전 한글화 / 幻世風狂伝 Korean Translation Patch

Compile Inc.의 1994년 PC-98 RPG **환세풍광전(幻世風狂伝)** 한글화 프로젝트.

## 현황

| 단계 | 상태 |
|------|------|
| 역공학 (파일 포맷 파악) | ✅ 완료 |
| 텍스트 추출 파서 | ✅ 완료 |
| 번역 | 🔄 진행 중 |
| 재삽입 스크립트 | ⏳ 예정 |
| 한글 폰트 패치 | ⏳ 예정 |
| 동작 확인 (NP2kai) | ⏳ 예정 |

## 파일 구조

```
tools/
  gf2_parser.py    CMD 파일 파서. 압축 해제 + 텍스트 추출 + JSON 생성.
  NOTES.md         역공학 분석 노트. 다른 Compile 타이틀 적용 시 참고.
translation/
  translation.json 번역 작업 파일. JP/KR 쌍 + 재삽입용 오프셋 포함.
```

## 사용법

원본 게임 파일이 `original/` 디렉토리에 있을 때:

```bash
# 텍스트 추출 및 translation.json 생성
python tools/gf2_parser.py original/

# CMD 파일 압축 해제본 저장 (분석용)
python tools/gf2_parser.py original/ dump
```

## 기술 개요

- **실행파일(GF2.COM)**: 자가 압축(self-extracting), LZ 계열 알고리즘
- **스크립트(.CMD)**: 런타임에 동일 LZ 알고리즘으로 압축 해제 후 인터프리트
- **텍스트 인코딩**: Shift-JIS
- **대화 마커**: `0x65 0x00 [SJIS lead]` (시작) / `0x6b` (종료)
- **아이템 마커**: `0x0f 0x03` (시작)

자세한 내용은 `tools/NOTES.md` 참고.

## 라이선스

번역 데이터 및 도구 코드: MIT  
원본 게임 저작권: Compile Inc.
