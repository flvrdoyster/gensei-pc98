# 환세포물장 역공학 노트

**대상**: 환세포물장 / 幻世捕物帳 (Compile, 1996, PC-98)  
**상태**: 추출 완료, 번역 진행 중 (인서터·웹 에뮬레이터 준비 완료)  
**도구**: `torimono_parser.py` (추출) · `torimono_inserter.py` (인서트)

---

## 개요

### 파일 구성

```
original/torimono/
  GSC.COM         3,984 B   로더 (DISK_*.DAT 로드 + LZ 해제)
  FPLAY.COM      16,138 B   FM 음원 플레이어
  DISK_B.DAT    573,469 B   스크립트·텍스트·그래픽 (95개 청크)
  DISK_C.DAT  1,243,238 B   그래픽 데이터 (텍스트 없음 — 전 청크 디컴프 후 SJIS 밀도 검사로 확인)
  PLAY1~8.INF     3,193 B   스테이지 맵 데이터 (텍스트 없음)
  SONG.DAT       15,193 B   음악 데이터
```

**텍스트 소스**: DISK_B.DAT 단일 파일 (쾌도전과 동일 구성).

- FPLAY.COM·GSC.COM 에는 DOS 드라이버/플레이어 에러 메시지(일본어)가 있으나 **번역 대상 아님** (쾌도전과 동일 결정).

### DISK_B.DAT 청크 구조

쾌도전과 동일 — `0x000~0x3FF` 4-byte 엔트리 테이블, `compile_lz` 압축.
상세는 `KAITOU.md` 참조.

---

## 파서

`torimono_parser.py` 는 `kaitou_parser.py` 복제본 (게임별 파서 독립 컨벤션).
오피코드 워킹은 `compile_script.walk` 공유 — **BASE_SPEC 무수정으로 동작 확인**
(같은 엔진이라 오프너·마커·구분자 체계 동일).

### NOISE_CHUNKS 식별 절차 (재현 가능)

쾌도전의 NOISE 목록은 **타이틀마다 청크 배치가 달라 재사용 불가**
(예: 쾌도전 노이즈 42·44 가 포물장에선 SJIS 밀도 35~46% 의 텍스트 청크).
포물장은 다음 절차로 자체 식별:

1. **NOISE 비우고 전체 파싱** — 예단 금지. 전 청크를 일단 통과시킨다.
2. **청크별 정량 지표**: ① 디컴프 SJIS 밀도 ② 추출 글자 중 가나/한자 비율
   ③ 1글자 라인 비율. 정상 텍스트 청크는 가나/한자 80~92%.
3. **회색지대는 추출물을 눈으로 검증** — 지표만으로 확정하지 않는다.
   - 노이즈: 키릴 문자, 동일 희귀한자 반복, 의미 없는 한자 조합, `ｃ` 반복 등
   - **저밀도여도 정상인 것**: 적/캐릭터 이름 블록 (`ネコタマ`·`シノビ` 등,
     짧은 텍스트 + 스탯 바이너리라 밀도가 원래 낮음) — 밀도 기준만 쓰면 학살됨
4. 확정 목록은 `torimono_parser.py` 의 `NOISE_CHUNKS` (단일 소스).

## 배포 형태 — HDI (시리즈 유일)

포물장은 DISK_C(그래픽)가 2HD 플로피 용량을 넘어 **부팅 가능한 PC-98 HDD 이미지(HDI)** 로
구동한다 (다른 타이틀은 FDI). 베이스는 `emulator/rom/torimono_kr.hdi` —
IPL1 부트코드 + `MS-DOS 6.20` 활성 파티션 + 게임 파일 전체.

- **인서트**: `torimono_inserter.py` 가 DISK_B 청크 패치 후 `patch_hdi` 로 베이스 HDI에 교체.
  `pc98disk.py` 가 PC-98 파티션 테이블을 해석해 파티션 내 FAT 파일을 교체한다 (`NOTES.md` 참조).
  쾌도전과 달리 CONFIG.SYS 가 없어 EMM386 제거 단계도 없음.
- **웹 에뮬**: np2kai 웹빌드의 커맨드라인 확장자 분기에 `.hdi` 가 없어 `arguments` 로는
  못 물린다. `torimono.html` 이 preRun 에서 번들 내 `np2kai.cfg` 에 `HDD1FILE` 을 주입해
  SASI HDD 로 마운트 (페이지 번들 FS 안에서만 — 공유 cfg 원본 무영향). 부팅·게임 기동 검증 완료.
- 세이브: 다른 타이틀과 동일한 IDB 방식, 키는 `torimono_kr.hdi` (HDI 통째 저장).

### 잔여 리스크 (쾌도전에서 실증된 패턴 — 번역·검수 중 발견 대상)

- **x86 임베드 라벨**: 코드 청크의 status 라벨은 walk 가 선행 글자를 놓치거나
  offset 이 어긋날 수 있음 (쾌도전 `運` 누락·`武器` 어긋남 사례, `KAITOU.md` 참조)
- **단독 `01` 종료 줄**: break_lead 없이 끝나는 줄은 walk 모델 밖 (쾌도전 `「いた！` 사례)
- 발견 시 파서를 고치지 말고 translation.json 수동 보정 (carried 라인) — 사유는 `KAITOU.md`
