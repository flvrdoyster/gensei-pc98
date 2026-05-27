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

- `0x85A4~0x85A7`: 리/프/레/시 (희담 리프레시워터)
- `0x85A8~0x85EA`: 풍광전 적 이름용 한글 67자 (가/게/기/나/노/...)
- `0x85EB~0x85EC`: 아/템 (풍광전 UI 아이템 라벨 추가)

원본 반각 카나(`ヲ`, `ァ` 등) 글리프가 덮어씌워지지만, 게임 데이터에서 해당  
코드포인트를 안 쓰면 영향 없음.

ASCII 반각(`0x8540~0x859E`)은 게임 원본 폰트의 ANK 글리프를 그대로 사용 가능 →  
charmap에 `/0`, `/A`, `/G`, ... `/z` 형태로 ASCII printable 94자 전체 등록됨.

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
