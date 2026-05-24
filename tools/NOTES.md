# 공통 도구 노트

---

## 로컬 서버 포트 규칙

| 용도 | 포트 | 연상 |
|------|------|------|
| 번역 에디터 (`editor.py`) | **8182** | JP(81) → KR(82) |
| 에뮬레이터 (`python3 -m http.server`) | **9801** | PC-9801 |

```bash
# 번역 에디터
python3 tools/editor.py <title>
# → http://localhost:8182

# 에뮬레이터 (프로젝트 루트에서 실행)
python3 -m http.server 9801 --directory emulator
# → http://localhost:9801
```

---

## editor.py — 번역 에디터

웹 기반 번역 GUI. 800px 고정 폭, 다크 테마.

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
- 태그 변경 + 적용/취소

### 검색

상단 검색바에서 JP/KR 부분 일치, 완전 일치 토글 가능.  
완전 일치 모드에서는 매칭된 모든 행에 같은 KR을 한 번에 채우는 "전체 적용" 표시.

### 빌드 / 번들

`빌드` 버튼 — 인서터 실행 (`build/` 생성).  
`번들 생성` 버튼 — `emulator/<title>.data` 재생성 (emsdk 환경 필요).

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

### 제약 사항

- 루트 디렉토리만 지원 (서브디렉토리 미구현)
- 8.3 파일명만 지원 (LFN 없음)
- non-FAT 이미지는 목록 조회만 가능 (파일 추가/추출 불가)
