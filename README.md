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
#    - 태그 배지 클릭으로 분류 변경 (아래 태그 정의 참조)
#    - 가이지(외자) 항목은 '외' 배지로 표시
python3 tools/editor.py

# 3. 재삽입 (build/hukyou/ 에 패치된 파일 생성)
python3 tools/hukyou_inserter.py original/hukyou

# CMD 파일 압축 해제본 저장 (분석용)
python3 tools/hukyou_parser.py original/hukyou dump
```

## 텍스트 태그 정의

translation.json의 각 텍스트 항목에 `tag` 필드로 분류. 시리즈 공통.

| 태그 | 설명 | 예시 |
|------|------|------|
| `dialog` | NPC/파티 대사 | 「俺のブタを助け出さなければ。」 |
| `monolog` | 내레이션·독백 (대사창 밖) | MESSAGE.CMD 스테이지 간 파티 대화 |
| `cutscene` | 오프닝·엔딩 연출 텍스트 | OPEN.CMD, ENDING.CMD |
| `char` | 캐릭터 이름 표시 | ダリオス, ミズホ |
| `battle` | 전투 관련 (적 이름, 기술명, 전투 메뉴) | スライム, たいあたり, たたかう |
| `item` | 아이템 이름·설명·수치 | 導きの羽, HP+10 |
| `menu` | 메뉴·라벨·UI 텍스트 | データロード, はい/いいえ |
| `location` | 장소명 | 堺の町, 霜の山 |
| `system` | 시스템 메시지 | セーブ中, ディスクエラー |

## 라이선스

번역 데이터 및 도구 코드: MIT  
원본 게임 저작권: Compile Inc.
