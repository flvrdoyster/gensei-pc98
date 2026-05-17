# 환세 시리즈 한글화 — 역공학 노트 인덱스

타이틀별 상세 노트:

- **[NOTES_hukyou.md](NOTES_hukyou.md)** — 환세풍광전 (幻世風狂伝, 1994)
  - GF2.COM LZ 압축 구조, CMD 포맷, 제어코드 완전 확정
  - 파서(`hukyou_parser.py`) + 인서터(`hukyou_inserter.py`) 구현 완료

- **[NOTES_kaitou.md](NOTES_kaitou.md)** — 환세쾌도전 (幻世快盗伝, 1995)
  - DISK_B.DAT 청크 구조, 제어코드 부분 확정 (72 XX만)
  - 파서(`kaitou_parser.py`) v2 완료, 인서터 미구현
  - 다음 단계: DOSBox-X 런타임 분석 → 제어코드 확정 → 파서 v3

---

## 공통 도구

| 파일 | 역할 |
|------|------|
| `compile_lz.py` | LZ 압축/해제 + SJIS/가이지 유틸 (Compile社 공통) |
| `editor.py` | 웹 번역 에디터 (localhost:8421) |
| `charmap.json` | 한글↔가이지 코드 매핑 (KS X 1001, JIS 2수준 영역) |

## 타이틀별 도구

| 파일 | 타이틀 | 역할 |
|------|--------|------|
| `hukyou_parser.py` | 풍광전 | CMD 파서 (대화/메뉴/아이템/UI) |
| `hukyou_inserter.py` | 풍광전 | 번역 재삽입 (LZ 재압축) |
| `kaitou_parser.py` | 쾌도전 | DISK_B.DAT 파서 (type=0000 청크) |
| `dosbox-kaitou.conf` | 쾌도전 | DOSBox-X PC-98 설정 (런타임 디버거) |

---

## Compile 타이틀 적용 체크리스트

### 압축 알고리즘 동일 여부 (풍광전 계열)
- COM 파일 0x100이 `FC 60 8C C8…`으로 시작하면 동일 구조
- `0x113~0x114 = F3 A5` (REP MOVSW) 확인
- `compile_lz.py`의 `decompress()` 재사용 가능

### 쾌도전/포물장 계열 (DAT 구조)
- DISK_B.DAT 앞 264바이트(0x108): 청크 인덱스
- type=0000 청크 = 스크립트/텍스트
- `kaitou_parser.py`의 `get_text_chunk_ranges()` 재사용 가능

### 제어코드 확인 순서
1. Shift-JIS 런 4자+ 주변 바이트 빈도 분석
2. `72 XX` (줄바꿈) 동일 가능성 높음
3. 앞뒤 패턴으로 블록 헤더 opcode 특정
4. 불명 opcode → DOSBox-X 런타임 브레이크포인트로 확정
