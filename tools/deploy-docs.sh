#!/usr/bin/env bash
# emulator/ → docs/ 동기화 + 배포 정합 검사 (커밋은 하지 않음).
#   사용: ./tools/deploy-docs.sh [-f]
#   0) 빌드 신선도: translation/<title>/translation.json 이 emulator/<title>.data 보다
#      최신이면 = 편집 후 빌드 안 한 것으로 보고 복사 전에 중단 (-f 로 건너뜀)
#   1) emulator/* 를 docs/ 로 복사
#   2) docs ↔ emulator 전체 동일성 검사
#   3) 각 <title>.js 의 remote_package_size ↔ <title>.data 실제 크기 검사
# 하나라도 어긋나면 비정상 종료(코드 1). 버전(version.js)은 건드리지 않는다.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1   # 레포 루트로

force=0
[ "${1:-}" = "-f" ] && force=1

if [ -t 1 ]; then R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[1m'; N=$'\033[0m'; else R=; G=; Y=; B=; N=; fi
fail=0

echo "${B}0) 빌드 신선도 (json vs 번들)${N}"
# json·번들이 둘 다 커밋된(clean) 타이틀은 일관 가정하고 스킵.
# 작업 중(둘 중 하나라도 dirty)인 타이틀만 mtime으로 신선도 판정 —
# json 이 번들보다 최신이면 편집 후 빌드 안 한 것으로 본다.
stale=0
for data in emulator/*.data; do
  [ -e "$data" ] || continue
  t=$(basename "$data" .data)
  json="translation/$t/translation.json"
  [ -f "$json" ] || continue
  if git diff --quiet HEAD -- "$json" "$data" 2>/dev/null; then
    continue   # 둘 다 커밋됨 → 일관 가정, 스킵
  fi
  if [ "$json" -nt "$data" ]; then
    echo "  ${Y}⚠ $t: translation.json 이 $t.data 보다 최신 → 빌드 안 했을 수 있음${N}"
    stale=1
  else
    echo "  ${G}✓ $t (작업 중, 번들 최신)${N}"
  fi
done
[ "$stale" -eq 0 ] && echo "  ${G}✓ 미빌드 의심 없음${N}"
if [ "$stale" -eq 1 ]; then
  if [ "$force" -eq 1 ]; then
    echo "  ${Y}(-f 지정 — 신선도 경고 무시하고 진행)${N}"
  else
    echo
    echo "${R}${B}미빌드 의심 — 에디터에서 빌드·번들 생성 후 다시 실행하세요.${N}"
    echo "${Y}정말 그대로 배포하려면: ./tools/deploy-docs.sh -f${N}"
    exit 1
  fi
fi

echo "${B}1) emulator/ → docs/ 복사${N}"
cp -r emulator/* docs/ || { echo "${R}복사 실패${N}"; exit 1; }

echo "${B}2) docs ↔ emulator 동일성${N}"
if diff -rq --exclude='.DS_Store' emulator/ docs/ >/tmp/deploy-docs-diff 2>&1; then
  echo "  ${G}✓ 일치${N}"
else
  echo "  ${R}✗ 차이 발견:${N}"; sed 's/^/    /' /tmp/deploy-docs-diff; fail=1
fi

echo "${B}3) 번들 메타 ↔ 데이터 크기${N}"
for data in emulator/*.data; do
  [ -e "$data" ] || continue
  t=$(basename "$data" .data)
  js="docs/$t.js"; dd="docs/$t.data"
  [ -f "$js" ] || { echo "  ${R}✗ $t: $js 없음${N}"; fail=1; continue; }
  ds=$(wc -c < "$dd" | tr -d ' ')
  ms=$(grep -o '"remote_package_size":[0-9]*' "$js" | head -1 | grep -o '[0-9]*')
  if [ "$ds" = "$ms" ]; then
    echo "  ${G}✓ $t: $ds${N}"
  else
    echo "  ${R}✗ $t: data=$ds meta=${ms:-?} 불일치${N}"; fail=1
  fi
done

echo
if [ "$fail" -eq 0 ]; then
  echo "${G}${B}정합 OK — 커밋 준비됨${N}"
else
  echo "${R}${B}정합 실패 — 배포하지 말 것${N}"; exit 1
fi
