"""
번역 웹 에디터
==============

사용법:
  python3 tools/editor.py                 # 터미널에서 대상 선택
  python3 tools/editor.py <title>         # 바로 지정
  python3 tools/editor.py <title> --no-open   # 브라우저 자동 실행 안 함
  → http://localhost:8182 (기본적으로 브라우저가 자동으로 열린다)

  <title>: hukyou | kaitou | torimono | kitan
           dashboard — 4개 타이틀 빌드/번들/배포 대시보드

translation.json의 kr 필드를 브라우저에서 편집, 저장.
빌드/번들/배포 파이프라인 로직은 tools/pipeline.py 공용 모듈 참조.
"""

import http.server
import json
import os
import re
import sys
import threading
import urllib.parse
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lint      # 빌드 시 검수(lint) 통합
import pipeline  # 빌드/번들/배포 공용 파이프라인

TITLES = pipeline.TITLES

CHOICES = list(TITLES) + ['dashboard']
CHOICE_LABELS = dict(TITLES, dashboard='빌드·배포 대시보드')

NO_OPEN = '--no-open' in sys.argv[1:]
POSITIONAL = [a for a in sys.argv[1:] if not a.startswith('-')]


def pick_title():
    """인자 없이 실행됐을 때 터미널에서 대상 선택. 기본값으로 임의의 타이틀을 열지 않는다."""
    if not sys.stdin.isatty():
        print('대상을 지정하세요: python3 tools/editor.py <title>')
        print(f'사용 가능: {", ".join(CHOICES)}')
        sys.exit(1)

    tty = sys.stdout.isatty()
    B, D, N = ('\033[1m', '\033[2m', '\033[0m') if tty else ('', '', '')

    # 키(ASCII)를 먼저 고정폭으로 — 한글은 터미널에서 2칸이라 글자 수로 정렬하면 어긋난다.
    print(f'\n{B}환세 시리즈 번역 도구{N}\n')
    for i, key in enumerate(CHOICES, 1):
        sep = '\n' if key == 'dashboard' else ''
        print(f'{sep}  {B}{i}{N}) {key:<10}{D}{CHOICE_LABELS[key]}{N}')

    while True:
        try:
            raw = input(f'\n선택 {D}(1-{len(CHOICES)}, 이름 직접 입력 가능, q=종료){N}: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if raw.lower() in ('q', 'quit', 'exit'):
            sys.exit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(CHOICES):
            return CHOICES[int(raw) - 1]
        if raw in CHOICES:
            return raw
        print('  잘못된 입력입니다.')


def resolve_title():
    if not POSITIONAL:
        return pick_title()
    title = POSITIONAL[0]
    if title not in CHOICES:
        print(f'알 수 없는 타이틀: {title!r}')
        print(f'사용 가능: {", ".join(CHOICES)}')
        sys.exit(1)
    return title

TITLE = resolve_title()
DASHBOARD_MODE = (TITLE == 'dashboard')

if DASHBOARD_MODE:
    TITLE_KR = '빌드·배포 대시보드'
    TRANS_PATH = CHARMAP_PATH = DRAFT_DIR = None
    HAS_INSERTER = HAS_EMULATOR = False
else:
    TITLE_KR = TITLES[TITLE]
    TRANS_PATH = os.path.join(PROJECT_ROOT, 'translation', TITLE, 'translation.json')
    CHARMAP_PATH = os.path.join(PROJECT_ROOT, 'tools', 'charmap.json')
    HAS_INSERTER = pipeline.has_inserter(TITLE)
    DRAFT_DIR = os.path.join(PROJECT_ROOT, 'translation', TITLE, 'draft')
    HAS_EMULATOR = pipeline.has_emulator(TITLE)


def load_draft_map():
    """draft/ 폴더의 chunk_XX.md 파일을 파싱해 {globalOffset: {main, alt, star}} 반환.
    globalOffset = chunk * 200000 + localOffset (JS rows 와 동일 규칙)."""
    if not os.path.isdir(DRAFT_DIR):
        return {}
    CHUNK_BASE = 200000
    result = {}
    for fname in sorted(os.listdir(DRAFT_DIR)):
        if not fname.endswith('.md'):
            continue
        m = re.match(r'chunk_(\d+)\.md$', fname)
        if not m:
            continue
        chunk_num = int(m.group(1))
        with open(os.path.join(DRAFT_DIR, fname), encoding='utf-8') as f:
            lines = f.readlines()
        last_star_global = None
        for line in lines:
            line = line.strip()
            if not line.startswith('|') or line.startswith('|--') or line.startswith('|오프'):
                continue
            cells = [c.strip() for c in line.split('|')]
            if len(cells) < 7:
                continue
            offset_str = cells[1]
            translation = cells[5]
            bytecount = cells[6] if len(cells) > 6 else ''

            if offset_str == '':
                if translation.startswith('↳압축') and last_star_global is not None:
                    alt_text = translation[3:].strip()
                    if last_star_global in result:
                        result[last_star_global]['alt'] = alt_text
                continue

            if not offset_str.isdigit():
                continue

            local_offset = int(offset_str)
            global_offset = chunk_num * CHUNK_BASE + local_offset

            if '[확정]' in translation:
                last_star_global = None
                continue

            if not translation:
                last_star_global = None
                continue

            is_star = '★' in bytecount
            result[global_offset] = {'main': translation, 'alt': None, 'star': is_star}
            last_star_global = global_offset if is_star else None

    return result


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>__TITLE_KR__ 번역 에디터</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Malgun Gothic', sans-serif; background: #1e1e1e; color: #d4d4d4; padding: 16px; padding-top: 0; font-size: 14px; width: 800px; }
.topbar { position: sticky; top: 0; z-index: 10; background: #181818; padding: 10px 0 8px; border-bottom: 1px solid #333; }
h1 { font-size: 15px; font-weight: 600; color: #bbb; }
.topbar-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.topbar-actions { display: flex; align-items: center; gap: 8px; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: nowrap; }
.toolbar-search { margin-top: 4px; }
.toolbar select, .toolbar input[type="text"] { background: #252525; color: #ccc; border: 1px solid #3a3a3a; height: 28px; padding: 0 8px; border-radius: 4px; font-size: 12px; font-family: inherit; }
.toolbar select:focus, .toolbar input:focus { outline: none; border-color: #555; }
.toolbar label { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #888; cursor: pointer; user-select: none; white-space: nowrap; }
.toolbar label input[type="checkbox"] { accent-color: #999; width: 12px; height: 12px; }
#filterType { width: 128px; }
#filterFile { width: 128px; }
#filterSpeaker { width: 120px; }
#searchBox { width: 264px; }
.stats { font-size: 12px; color: #666; }
table { width: 768px; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
th { background: #1a1a1a; padding: 6px 8px; text-align: left; border-bottom: 1px solid #333; font-weight: 600; color: #666; font-size: 11px; position: sticky; top: var(--topbar-h, 72px); z-index: 5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
td { padding: 5px 8px; border-bottom: 1px solid #252525; vertical-align: top; overflow: hidden; }
tr:hover { background: #232323; }
.type { width: 76px; }
.type span { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.type-dialog span { background: #1e3a5c; color: #7ec4f8; }
.type-monolog span { background: #2a2450; color: #a5a0f0; }
.type-cutscene span { background: #3d1a30; color: #f0a0cc; }
.type-item span { background: #1a3520; color: #70c880; }
.type-menu span { background: #332800; color: #d4b060; }
.type-location span { background: #3a2010; color: #d09060; }
.type-battle span { background: #3a1a1a; color: #e08080; }
.type-system span { background: #2a2a2a; color: #aaa; }
.type-ignore span { background: #222; color: #555; text-decoration: line-through; }
.type-char span { background: #0d3040; color: #60c8e0; }
.type-enemy span { background: #401020; color: #f08090; }
.type span.taggable { cursor: pointer; position: relative; }
.type span.taggable:hover { filter: brightness(1.2); }
.halfwidth-badge { display: inline-block; padding: 1px 4px; border-radius: 2px; font-size: 10px; font-weight: 600; background: #2e1a50; color: #c090f0; margin-left: 4px; vertical-align: middle; }
.file { width: 82px; color: #555; }
td.file { font-size: 12px; }
.off { width: 50px; color: #555; font-family: monospace; text-align: right; padding-right: 10px; }
td.off { font-size: 11px; }
.jp { width: 200px; color: #999; white-space: pre-wrap; word-break: break-all; cursor: pointer; }
.jp:hover { background: #1e2433; }
.jp.copied { background: #1a3322; transition: background 0.1s; }
.kr-cell { width: 304px; }
.kr-input { width: 100%; background: #252525; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 4px 7px; border-radius: 4px; font-size: 13px; font-family: inherit; resize: none; overflow-y: auto; line-height: 1.5; display: block; box-sizing: border-box; }
.kr-input:focus { border-color: #666; outline: none; }
.kr-input.modified { border-color: #b87820; background: #1e1600; }
.kr-input.saved { border-color: #2a8040; }
.len { width: 56px; text-align: center; color: #555; }
td.len { font-size: 12px; }
.len.over { color: #c04040; font-weight: bold; }
.len.ok { color: #408040; }
.len.empty { color: #3a3a3a; }
.save-btn { background: #2e2e2e; color: #ccc; border: 1px solid #4a4a4a; height: 28px; width: 56px; border-radius: 4px; cursor: pointer; font-size: 12px; font-family: inherit; }
.save-btn:hover { background: #3a3a3a; color: #fff; }
.save-btn:disabled { background: #1e1e1e; color: #444; border-color: #2a2a2a; cursor: default; }
.build-btn { background: transparent; color: #999; border: 1px solid #3a3a3a; height: 28px; border-radius: 4px; cursor: pointer; font-size: 12px; font-family: inherit; }
#buildBtn { width: 56px; }
#emulatorBtn { width: 56px; }
#deployBtn { width: 56px; }
#jumpEditBtn { width: 32px; padding: 0; font-size: 14px; }
.build-btn:hover { background: #2a2a2a; color: #ddd; border-color: #555; }
.toast { position: fixed; bottom: 24px; right: 24px; background: #2a2a2a; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 9px 16px; border-radius: 4px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity 0.2s; max-width: 340px; box-shadow: 0 4px 16px rgba(0,0,0,0.5); }
.toast.show { opacity: 1; }
tr.row-selected { background: #1a2840 !important; }
tr.range-start { background: #252000 !important; }
#tbody tr { cursor: pointer; }
#tbody tr td.kr-cell { cursor: default; }
#tbody td.len.empty { cursor: pointer; }  /* 빈 KR — 클릭 시 placeholder 제안 채움 */
.bulk-bar { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #252525; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 9px 16px; border-radius: 6px; display: flex; gap: 10px; align-items: center; font-size: 13px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); z-index: 200; white-space: nowrap; }
.bulk-bar select { background: #333; color: #ccc; border: 1px solid #4a4a4a; padding: 4px 8px; border-radius: 4px; font-size: 12px; cursor: pointer; }
.bulk-apply { background: #1a3d1a; color: #7dc87d; border: 1px solid #2d5c2d; padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; font-weight: 600; }
.bulk-apply:hover { background: #234d23; }
.bulk-cancel { background: #2a2a2a; color: #999; border: 1px solid #3a3a3a; padding: 4px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; }
.bulk-cancel:hover { background: #333; color: #ccc; }
.fill-bar { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 4px; padding: 7px 12px; margin-bottom: 8px; display: flex; gap: 8px; align-items: center; font-size: 13px; }
.fill-bar input { flex: 1; background: #252525; border: 1px solid #3a3a3a; color: #d4d4d4; padding: 4px 8px; border-radius: 4px; font-size: 13px; font-family: inherit; }
.fill-bar input:focus { outline: none; border-color: #555; }
.fill-bar button { background: #2a2a2a; color: #bbb; border: 1px solid #3a3a3a; padding: 4px 12px; border-radius: 4px; font-size: 13px; cursor: pointer; font-weight: 600; white-space: nowrap; }
.fill-bar button:hover { background: #333; color: #ddd; }
.fill-bar .fill-info { color: #666; white-space: nowrap; }
.over-nav { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #666; }
.over-nav button { background: #252525; border: 1px solid #3a3a3a; border-radius: 4px; height: 28px; width: 48px; cursor: pointer; font-size: 12px; color: #999; font-family: inherit; }
.over-nav button:hover { background: #2e2e2e; color: #ccc; }
.over-nav .over-count { color: #c04040; font-weight: 600; }
tr.overflow-focus { outline: 2px solid #c04040; outline-offset: -2px; }
.draft-hint { display: flex; gap: 4px; margin-top: 4px; }
.draft-btn { background: #1a2e40; color: #6aadcc; border: 1px solid #2a4560; padding: 2px 8px; border-radius: 3px; font-size: 11px; cursor: pointer; font-family: inherit; white-space: nowrap; }
.draft-btn:hover { background: #1e3a52; color: #8ccce8; }
.draft-alt { background: #1a2a1a; color: #6acc88; border-color: #2a452a; }
.draft-alt:hover { background: #1e3a1e; color: #88e8aa; }

</style>
</head>
<body>
<div class="topbar">
<div class="topbar-title">
  <h1>__TITLE_KR__ 번역 에디터</h1>
  <div class="topbar-actions">
    <span class="stats" id="stats"><svg id="donut" width="16" height="16" viewBox="0 0 36 36" style="vertical-align:middle;margin-right:4px"><circle cx="18" cy="18" r="14" fill="none" stroke="#333" stroke-width="5"/><circle id="donutArc" cx="18" cy="18" r="14" fill="none" stroke="#22c55e" stroke-width="5" stroke-dasharray="0 88" stroke-linecap="round" transform="rotate(-90 18 18)"/></svg><span id="statsText"></span></span>
    <button class="build-btn" id="jumpEditBtn" title="마지막 편집 위치로 (Ctrl+D)" disabled>↩</button>
    <button class="save-btn" id="saveBtn" disabled>저장</button>
    <button class="build-btn" id="buildBtn" title="번역을 디스크 이미지에 삽입 (build/)">빌드</button>
    <button class="build-btn" id="emulatorBtn" title="웹 번들 재생성 (emulator 데이터)">번들</button>
    <button class="build-btn" id="deployBtn" title="emulator → docs 동기화·정합 검사">배포</button>
  </div>
</div>
<div class="toolbar">
  <select id="filterType">
    <option value="">전체 타입</option>
    <option value="dialog">대사</option>
    <option value="monolog">독백</option>
    <option value="cutscene">컷씬</option>
    <option value="item">아이템</option>
    <option value="menu">메뉴/라벨</option>
    <option value="location">장소</option>
    <option value="char">캐릭터명</option>
    <option value="enemy">적</option>
    <option value="battle">전투</option>
    <option value="system">시스템</option>
  </select>
  <select id="filterFile">
    <option value="">전체 파일</option>
  </select>
  <span id="filterSpeakerWrap" style="display:none">
  <select id="filterSpeaker">
    <option value="">전체 화자</option>
  </select>
  </span>
  <label><input type="checkbox" id="filterUntranslated"> 미번역만</label>
  <label><input type="checkbox" id="filterHalfwidth"> 반각만</label>
  <label><input type="checkbox" id="filterShowIgnore"> 제외 포함</label>
</div>
<div class="toolbar toolbar-search">
  <input type="text" id="searchBox" placeholder="검색 (JP/KR)...">
  <label><input type="checkbox" id="filterExact"> 완전 일치</label>
  <span class="over-nav" id="overNav" style="display:none"><span class="over-count" id="overCount"></span>초과 <button id="overPrev">이전</button><button id="overNext">다음</button></span>
</div>
</div>
<div class="fill-bar" id="fillBar" style="display:none">
  <span class="fill-info" id="fillInfo"></span>
  <input type="text" id="fillInput" placeholder="KR 입력...">
  <button id="fillApply">전체 적용</button>
</div>
<table>
<thead><tr>
  <th class="type">타입</th>
  <th class="file">파일</th>
  <th class="off">OFF</th>
  <th class="jp">JP</th>
  <th class="kr-cell">KR</th>
  <th class="len">Byte</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<div class="toast" id="toast"></div>

<div class="bulk-bar" id="bulkBar" style="display:none">
  <span id="bulkCount"></span>
  <button class="bulk-apply" id="bulkCopyJp">JP 복사</button>
  <button class="bulk-apply" id="bulkCopyKr">KR 복사</button>
  <span id="bulkModeWrap" style="display:none">
    <label><input type="radio" name="bulkMode" value="tag" checked> 태그</label>
    <label><input type="radio" name="bulkMode" value="speaker"> 화자</label>
  </span>
  <span id="bulkTagControls">
    <select id="bulkTag">
      <option value="dialog">대사</option>
      <option value="monolog">독백</option>
      <option value="cutscene">컷씬</option>
      <option value="char">캐릭터</option>
      <option value="enemy">적</option>
      <option value="battle">전투</option>
      <option value="item">아이템</option>
      <option value="menu">메뉴</option>
      <option value="location">장소</option>
      <option value="system">시스템</option>
      <option value="ignore">제외</option>
    </select>
  </span>
  <span id="bulkSpeakerControls" style="display:none">
    <input type="text" id="bulkSpeakerInput" list="speakerList" placeholder="화자명(빈칸=해제)" style="width:128px">
    <datalist id="speakerList"></datalist>
  </span>
  <button class="bulk-apply" id="bulkApply">적용</button>
  <button class="bulk-cancel" id="bulkCancel">취소</button>
</div>

<script>
let rows = [];
let rowIndex = new Map();   // rowKey(r) → row, O(1) 조회용 (rows 적재 후 load()에서 1회 구축)
let modified = {};
let tagChanges = {};
let speakerChanges = {};   // file:offset → 수동 화자 지정값 (''=미상 override)
let charmap = {};
let selection = new Set();
let filteredRows = [];
let rangeStart = null;
let hasSpeakers = false;   // entries 포맷(쾌도전·포물장)이면 화자 그룹핑 활성
let overflowRows = [];   // filteredRows 중 초과 항목
let overflowIdx = -1;
let lastSearch = '';
let lastEditedKey = null;

function rowKey(r) { return r.type + ':' + r.file + ':' + r.offset; }
// 입력 보조 정규화: 공백·약물·특수문자 제거, 글자(가나·한자·영숫자)만. lint.py _norm_jp 와 범위 일치.
const NORM_KEEP_RE = /[0-9A-Za-z０-ｚ぀-ヿ一-鿿｡-ﾟ]/g;
function normJp(s) { return ((s || '').match(NORM_KEEP_RE) || []).join(''); }

function updateBulkBar() {
  const bar = document.getElementById('bulkBar');
  if (selection.size === 0) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  document.getElementById('bulkCount').textContent = selection.size + '행 선택';
}

async function load() {
  const [transRes, charmapRes, glossRes, draftRes] = await Promise.all([
    fetch('/api/translation'),
    fetch('/api/charmap'),
    fetch('/api/series-glossary'),
    fetch('/api/draft'),
  ]);
  const data = await transRes.json();
  charmap = await charmapRes.json();
  // 입력 보조: 시리즈 전 타이틀의 jp→{kr,t} 용어집 (현재 타이틀 우선, 없으면 타 타이틀 제안)
  window.__jpSuggest = await glossRes.json();
  window.__draftMap = await draftRes.json();
  rows = [];

  if (data.entries) {
    // kaitou / 새 포맷: flat entries 리스트
    // 전역 오프셋 = chunk * 200000 + local_offset (청크 내 최대 해제 크기 < 200000 보장)
    // 칼럼 헤더 + 필터 레이블을 청크용으로 교체
    document.querySelector('th.file').textContent = '청크';
    document.querySelector('#filterFile option[value=""]').textContent = '전체 청크';

    for (const entry of data.entries) {
      const base = entry.chunk * 200000;
      const chunkLabel = '청크 ' + String(entry.chunk).padStart(2, '0');
      const elines = entry.lines || [];
      for (let li = 0; li < elines.length; li++) {
        const line = elines[li];
        rows.push({
          type: 'dialog', tag: line.tag || null, file: chunkLabel,
          chunk: entry.chunk, offset: base + line.offset, localOffset: line.offset,
          jp: line.jp, kr: line.kr, jp_len: line.jp_len,
          halfwidth: false, taggable: true, speaker: '',
          speakerOverride: line.speaker || '',
          entryType: entry.type, entryFirst: li === 0,
        });
      }
    }
    // 표시 정렬: 청크 경계는 유지하고 청크 내에서만 line offset 순.
    // 전역 offset = chunk*200000 + local 이라, 정렬하면 청크별로 묶이며 내부가 offset 순이 된다.
    // (데이터/파서는 건드리지 않음 — 표시 단계에서만 정렬)
    rows.sort((a, b) => a.offset - b.offset);
  } else {
    // hukyou 포맷: dialogs / items / ui 구조
    for (const dialog of data.dialogs) {
      for (const line of dialog.lines) {
        rows.push({
          type: 'dialog', tag: line.tag || null, file: dialog.file, index: dialog.index,
          offset: line.offset, localOffset: line.offset, jp: line.jp, kr: line.kr, halfwidth: !!line.halfwidth,
        });
      }
    }
    for (const item of (data.items || [])) {
      const n = item.name;
      rows.push({ type: 'item', tag: n.tag || 'item', file: 'MESSAGE.CMD', offset: n.offset, localOffset: n.offset, jp: n.jp, kr: n.kr, jp_len: n.jp_len, halfwidth: !!n.halfwidth });
      if (item.stat) {
        const s = item.stat;
        rows.push({ type: 'item', tag: s.tag || 'item', file: 'MESSAGE.CMD', offset: s.offset, localOffset: s.offset, jp: s.jp, kr: s.kr, jp_len: s.jp_len, halfwidth: !!s.halfwidth });
      }
      for (const desc of item.desc) {
        rows.push({ type: 'item', tag: desc.tag || 'item', file: 'MESSAGE.CMD', offset: desc.offset, localOffset: desc.offset, jp: desc.jp, kr: desc.kr, jp_len: desc.jp_len, halfwidth: !!desc.halfwidth });
      }
    }
    const UI_CAT_TAG = { system: 'system', status: 'menu', names: 'menu', battle: 'battle' };
    for (const entry of (data.ui || [])) {
      const defaultTag = UI_CAT_TAG[entry.category] || 'menu';
      const tag = entry.tag || defaultTag;  // JSON에 저장된 tag 우선, 없으면 category 기본값
      rows.push({ type: 'ui', tag: tag, file: 'GF2.COM', category: entry.category, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, halfwidth: true });
    }
    // gsovl (kitan GS.OVL 고정 오프셋 문자열)
    const GSOVL_CAT_TAG = { battle: 'battle', status: 'system', name: 'char', stat: 'system', misc: 'menu' };
    for (const entry of (data.gsovl || [])) {
      const tag = GSOVL_CAT_TAG[entry.tag] ?? entry.tag ?? 'system';
      rows.push({ type: 'gsovl', tag, file: 'GS.OVL', category: entry.tag, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, halfwidth: false });
    }
    // demo (kitan demo SP1.COM 텍스트)
    const DEMO_CAT_TAG = { intro: 'dialog', title: 'system', error: 'system' };
    for (const entry of (data.demo || [])) {
      const tag = DEMO_CAT_TAG[entry.tag] ?? entry.tag ?? 'dialog';
      rows.push({ type: 'demo', tag, file: 'SP1.COM', category: entry.tag, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, halfwidth: false });
    }
  }

  const files = [...new Set(rows.map(r => r.file))];
  const sel = document.getElementById('filterFile');
  for (const f of files) {
    const opt = document.createElement('option');
    opt.value = f; opt.textContent = f;
    sel.appendChild(opt);
  }

  // 화자 그룹핑 (entries 포맷 전용). json 비파괴 — 화면용 파생 라벨만 계산.
  if (data.entries) {
    hasSpeakers = true;
    computeSpeakers(rows);
    populateSpeakerDropdown(rows);
    document.getElementById('filterSpeakerWrap').style.display = '';
    document.getElementById('bulkModeWrap').style.display = '';
  }

  rowIndex = new Map();
  for (const r of rows) rowIndex.set(rowKey(r), r);

  render();
}

const ASCII_FULLWIDTH = new Set([' ', '.', ',', '!', '?', '(', ')', '+', '=', '~',
  '0','1','2','3','4','5','6','7','8','9',
  'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
  'a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z']);

function encodeByteLen(text, useHalfwidth) {
  // 인서터 encode_korean_kitan과 동일 규칙.
  // `/X` 반각 마커는 charmap에 '/X' 키가 있으면 한 쌍(2바이트)으로 계산.
  let len = 0;
  const arr = [...text];
  let i = 0;
  while (i < arr.length) {
    const ch = arr[i];
    if (ch === '/' && i + 1 < arr.length && charmap['/' + arr[i + 1]]) {
      len += 2; i += 2; continue;
    }
    if (charmap[ch]) { len += 2; }
    else if (useHalfwidth) { len += 2; }
    else if (ASCII_FULLWIDTH.has(ch)) { len += 2; }
    else if (ch.charCodeAt(0) < 0x80) { len += 1; }
    else { len += 2; }
    i += 1;
  }
  return len;
}

function getJpLen(r) {
  if (r.jp_len) return r.jp_len;
  let len = 0;
  for (const ch of r.jp) {
    if (ch.charCodeAt(0) < 0x80) len += 1;
    else len += 2;
  }
  return len;
}

const TAG_LABELS = { dialog: '대사', monolog: '독백', cutscene: '컷씬', char: '캐릭터', enemy: '적', battle: '전투', item: '아이템', menu: '메뉴', location: '장소', system: '시스템', ignore: '제외' };
const DIALOG_TAGS = ['dialog', 'monolog', 'cutscene', 'char', 'battle', 'item', 'menu', 'location', 'system', 'ignore'];

function typeLabel(r) {
  const effective = r.tag || r.type;
  const label = TAG_LABELS[effective] || effective;
  const TYPE_CSS = { dialog: 'type-dialog', monolog: 'type-monolog', cutscene: 'type-cutscene', char: 'type-char', battle: 'type-battle', item: 'type-item', item_name: 'type-item', item_stat: 'type-item', item_desc: 'type-item', menu: 'type-menu', location: 'type-location', system: 'type-system', ignore: 'type-ignore' };
  const cls = TYPE_CSS[effective] || 'type-dialog';
  const taggable = (r.type === 'dialog' || r.type === 'item' || r.type === 'ui' || r.type === 'gsovl' || r.type === 'demo' || r.taggable) ? ' taggable' : '';
  return `<div class="${cls}"><span class="${taggable}" data-file="${r.file || ''}" data-offset="${r.offset}">${label}</span></div>`;
}

const UNKNOWN_SPEAKER = '(미상)';
// 화자 그룹핑에서 제외할 비-대사 태그 (UI·라벨류). 미상에도 안 잡히고 집계서 빠짐.
const NON_DIALOG_TAGS = new Set(['item', 'menu', 'enemy', 'system', 'battle', 'location', 'cutscene']);

// 화자 귀속: rows(전역 offset 순 정렬됨)를 청크별로 상태 워크.
//  - speaker 엔트리 첫 줄 = 화자명 → 현재화자 설정
//  - 「로 시작 않고 선행 공백도 없는 짧은 줄인데 '다음 줄이 「' 면 이름으로 인정 (手下A·암거래상 등)
//  - 「 대사·선행 공백(이어지는 줄)은 현재화자에 귀속, 화자 없이 「면 미상
//  - 지문(def)·메뉴 등은 현재화자 미상으로 리셋
// json 은 건드리지 않고 r.speaker(화면용)만 채운다.
function computeSpeakers(rows) {
  const lead = /^[\s　]+/;
  let cur = '';
  let prevChunk = null;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.chunk !== prevChunk) { cur = ''; prevChunk = r.chunk; }
    const jp = r.jp || '';
    const trimmed = jp.replace(lead, '');
    const isKagi = trimmed.startsWith('「');
    const isCont = lead.test(jp);

    // 새 엔트리가 '이어지는 줄'(선행 전각공백)이 아니면 현재화자 만료.
    // → 이름표 없이 「로 시작하는 엔트리는 cur가 비어 미상이 된다(화자 없는 「 귀속 금지).
    //   진짜 이름줄은 자기 「와 같은 엔트리에 있어(手下+「お頭) 이 리셋에 안 깨진다.
    if (r.entryFirst && !isCont) cur = '';

    // 수동 화자 지정 (최우선). 빈 문자열 override 는 강제 미상.
    if (r.speakerOverride !== undefined && r.speakerOverride !== '') {
      r.speaker = r.speakerOverride; r.isName = false;
      continue;
    }

    // UI·라벨류 태그는 대사가 아니므로 화자 그룹핑에서 제외 (미상에도 안 잡음).
    // 장면 컨텍스트 끊김으로 보고 현재화자도 리셋.
    if (NON_DIALOG_TAGS.has(r.tag)) {
      cur = ''; r.speaker = ''; r.isName = false;
      continue;
    }

    // char 태그 = 사용자 확정 화자명 (1순위, 무조건)
    if (r.tag === 'char' && !isKagi) {
      cur = (r.kr || r.jp || '').trim();
      r.speaker = cur; r.isName = true;
      continue;
    }

    if (r.entryType === 'speaker') {
      if (r.entryFirst && !isKagi) {
        cur = (r.kr || r.jp || '').trim();
        r.speaker = cur; r.isName = true;
      } else {
        r.speaker = cur || UNKNOWN_SPEAKER;
      }
      continue;
    }
    // dialog 등에 섞인 이름줄 휴리스틱: 짧은 비-「 줄 + 다음 줄이 「
    let isName = false;
    if (!isKagi && !isCont && r.entryType !== 'def' && [...jp].length <= 8) {
      const nx = rows[i + 1];
      if (nx && nx.chunk === r.chunk && (nx.jp || '').replace(lead, '').startsWith('「')) isName = true;
    }
    if (isName) {
      cur = (r.kr || r.jp || '').trim();
      r.speaker = cur; r.isName = true;
      continue;
    }
    if (isKagi || isCont) {
      r.speaker = cur || UNKNOWN_SPEAKER;
      continue;
    }
    cur = '';
    r.speaker = UNKNOWN_SPEAKER;  // 지문·메뉴 등
  }
}

function populateSpeakerDropdown(rows) {
  const counts = new Map();
  for (const r of rows) {
    if (r.isName) continue;  // 이름표 자체는 집계 제외
    const s = r.speaker;
    if (!s) continue;
    counts.set(s, (counts.get(s) || 0) + 1);
  }
  // 빈도순, (미상)은 맨 끝
  const names = [...counts.keys()].sort((a, b) => {
    if (a === UNKNOWN_SPEAKER) return 1;
    if (b === UNKNOWN_SPEAKER) return -1;
    return counts.get(b) - counts.get(a);
  });
  const sel = document.getElementById('filterSpeaker');
  const prev = sel.value;   // 재계산 시 선택 유지
  sel.innerHTML = '<option value="">전체 화자</option>';
  for (const n of names) {
    const opt = document.createElement('option');
    opt.value = n; opt.textContent = `${n} (${counts.get(n)})`;
    sel.appendChild(opt);
  }
  // 이전 선택이 아직 존재하면 복원 (사라진 화자면 '전체 화자'로)
  sel.value = [...sel.options].some(o => o.value === prev) ? prev : '';

  // 벌크바 화자 지정용 datalist. (미상)을 맨 위에 둬 강제 미상 지정도 가능.
  const dl = document.getElementById('speakerList');
  dl.innerHTML = '';
  const unkOpt = document.createElement('option');
  unkOpt.value = UNKNOWN_SPEAKER;
  dl.appendChild(unkOpt);
  for (const n of names) {
    if (n === UNKNOWN_SPEAKER) continue;
    const opt = document.createElement('option');
    opt.value = n;
    dl.appendChild(opt);
  }
}

// 태그 변경 등으로 화자 라벨이 바뀐 뒤 재계산 (rows는 이미 offset 순 정렬·유지됨).
// O(n) 한 번이라 태그 적용·저장마다 호출해도 가볍다.
function refreshSpeakers() {
  if (!hasSpeakers) return;
  computeSpeakers(rows);
  populateSpeakerDropdown(rows);
}

function render() {
  const filterType = document.getElementById('filterType').value;
  const filterFile = document.getElementById('filterFile').value;
  const filterSpeaker = document.getElementById('filterSpeaker').value;
  const search = document.getElementById('searchBox').value.toLowerCase();
  const exactMatch = document.getElementById('filterExact').checked;
  const untranslatedOnly = document.getElementById('filterUntranslated').checked;
  const halfwidthOnly = document.getElementById('filterHalfwidth').checked;
  const showIgnore = document.getElementById('filterShowIgnore').checked;

  filteredRows = rows.filter(r => {
    if (!showIgnore && (r.tag || r.type) === 'ignore') return false;
    if (untranslatedOnly) {
      if ((r.kr || '').trim() || (r.tag || r.type) === 'ignore') return false;
    }
    if (halfwidthOnly && !r.halfwidth) return false;
    if (filterType) {
      const effective = r.tag || r.type;
      if (effective !== filterType) return false;
    }
    if (filterFile && r.file !== filterFile) return false;
    if (filterSpeaker && r.speaker !== filterSpeaker) return false;
    if (search) {
      const jp = r.jp.toLowerCase(), kr = (r.kr || '').toLowerCase();
      if (exactMatch ? (jp !== search && kr !== search) : (!jp.includes(search) && !kr.includes(search))) return false;
    }
    return true;
  });

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';

  for (let idx = 0; idx < filteredRows.length; idx++) {
    const r = filteredRows[idx];
    const tr = document.createElement('tr');
    const key = rowKey(r);
    tr.dataset.key = key;
    if (selection.has(key)) tr.classList.add('row-selected');
    if (rangeStart !== null && idx === rangeStart) tr.classList.add('range-start');
    const kr = key in modified ? modified[key] : (r.kr || '');
    const isHalfwidth = r.halfwidth || r.file === 'GF2.COM';
    const jpLen = getJpLen(r);
    const krLen = kr ? encodeByteLen(kr, isHalfwidth) : 0;

    let lenClass = 'empty';
    let lenText = `${jpLen}`;
    if (kr) {
      lenText = `${krLen}/${jpLen}`;
      lenClass = krLen <= jpLen ? 'ok' : 'over';
    }

    const speakerHtml = r.speaker ? `<span style="font-size:11px;color:#999;display:block">${escHtml(r.speaker)}：</span>` : '';
    const draft = !kr && window.__draftMap && window.__draftMap[r.offset];
    const draftHtml = draft ? (() => {
      const mainBtn = `<button class="draft-btn" data-kr="${escAttr(draft.main)}">${draft.star ? '★초벌' : '초벌'}</button>`;
      const altBtn = draft.alt ? `<button class="draft-btn draft-alt" data-kr="${escAttr(draft.alt)}">압축안</button>` : '';
      return `<div class="draft-hint">${mainBtn}${altBtn}</div>`;
    })() : '';
    tr.innerHTML = `
      <td class="type">${typeLabel(r)}</td>
      <td class="file">${r.file}</td>
      <td class="off">${r.localOffset !== undefined ? r.localOffset : ''}</td>
      <td class="jp" title="클릭하여 복사" onclick="navigator.clipboard.writeText(this.dataset.jp);this.classList.add('copied');setTimeout(()=>this.classList.remove('copied'),600)" data-jp="${escAttr(r.jp)}">${speakerHtml}${escHtml(r.jp)}${r.halfwidth ? '<span class="halfwidth-badge">반</span>' : ''}</td>
      <td class="kr-cell"><textarea class="kr-input${key in modified ? ' modified' : ''}" data-key="${key}" placeholder="${(() => { const s = (!kr && window.__jpSuggest) ? window.__jpSuggest[normJp(r.jp)] : null; if (s) return escAttr(s.kr + ' (' + ({hukyou:'풍',kitan:'희',kaitou:'쾌',torimono:'포'}[s.t] || '?') + ')'); if (draft) return escAttr(draft.main); return '번역 입력...'; })()}" rows="1">${escHtml(kr)}</textarea>${draftHtml}</td>
      <td class="len ${lenClass}">${lenText}</td>
    `;
    tbody.appendChild(tr);
  }

  // 완전 일치 검색 중일 때 fill bar 표시
  const fillBar = document.getElementById('fillBar');
  if (exactMatch && search && filteredRows.length > 0) {
    document.getElementById('fillInfo').textContent = `${filteredRows.length}건`;
    fillBar.style.display = 'flex';
  } else {
    fillBar.style.display = 'none';
  }
  requestAnimationFrame(updateStickyOffset);

  recomputeOverflow();

  updateStats();
}

function recomputeOverflow() {
  overflowRows = [];
  for (const r of filteredRows) {
    const key = rowKey(r);
    const kr = key in modified ? modified[key] : (r.kr || '');
    if (!kr) continue;
    const isHalfwidth = r.halfwidth || r.file === 'GF2.COM';
    const jpLen = getJpLen(r);
    const krLen = encodeByteLen(kr, isHalfwidth);
    if (krLen > jpLen) overflowRows.push(r);
  }
  const overNav = document.getElementById('overNav');
  if (overflowRows.length > 0) {
    document.getElementById('overCount').textContent = overflowRows.length + '건 ';
    overNav.style.display = 'inline-flex';
    if (overflowIdx >= overflowRows.length) overflowIdx = overflowRows.length - 1;
  } else {
    overNav.style.display = 'none';
    overflowIdx = -1;
  }
}


function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;'); }

function updateStats() {
  const total = rows.length;
  const done = rows.filter(r => (r.kr || '') || (modified[r.type+':'+r.file+':'+r.offset] || '')).length;
  const mod = Object.keys(modified).length;
  const tags = Object.keys(tagChanges).length;
  const spk = Object.keys(speakerChanges).length;
  const changes = mod + tags + spk;
  const pct = total ? Math.round(100 * done / total) : 0;
  const circ = 2 * Math.PI * 14;
  document.getElementById('donutArc').setAttribute('stroke-dasharray', `${circ * pct / 100} ${circ}`);
  const filteredInfo = filteredRows.length < total ? ` | 표시: ${filteredRows.length}건` : '';
  const modInfo = mod ? ` | 수정: ${mod}건` : '';
  const tagInfo = tags ? ` | 분류: ${tags}건` : '';
  const spkInfo = spk ? ` | 화자: ${spk}건` : '';
  document.getElementById('statsText').textContent = `${pct}% (${done}/${total})${filteredInfo}${modInfo}${tagInfo}${spkInfo}`;
  document.getElementById('saveBtn').disabled = changes === 0;
}

document.getElementById('tbody').addEventListener('click', e => {
  if (!e.target.closest('td.type') || e.target.closest('.taggable')) return;
  const tr = e.target.closest('tr');
  if (!tr || !tr.dataset.key) return;
  const key = tr.dataset.key;
  const idx = filteredRows.findIndex(r => rowKey(r) === key);
  if (idx < 0) return;

  if (rangeStart === null) {
    selection.clear();
    rangeStart = idx;
    render();
  } else if (rangeStart === idx) {
    rangeStart = null;
    selection.clear();
    updateBulkBar();
    render();
  } else {
    const lo = Math.min(rangeStart, idx);
    const hi = Math.max(rangeStart, idx);
    selection.clear();
    for (let i = lo; i <= hi; i++) selection.add(rowKey(filteredRows[i]));
    rangeStart = null;
    updateBulkBar();
    render();
  }
});

// 모드 토글: 태그 ↔ 화자 (둘 중 하나만 적용 가능 — 섞임 방지)
function bulkMode() {
  const r = document.querySelector('input[name="bulkMode"]:checked');
  return r ? r.value : 'tag';
}
for (const radio of document.querySelectorAll('input[name="bulkMode"]')) {
  radio.addEventListener('change', () => {
    const speaker = bulkMode() === 'speaker';
    document.getElementById('bulkTagControls').style.display = speaker ? 'none' : '';
    document.getElementById('bulkSpeakerControls').style.display = speaker ? '' : 'none';
  });
}

// 적용: 현재 모드(태그/화자) 하나만 실행.
document.getElementById('bulkApply').addEventListener('click', () => {
  if (bulkMode() === 'speaker') {
    const name = document.getElementById('bulkSpeakerInput').value.trim();
    for (const key of selection) {
      const row = rowIndex.get(key);
      if (!row) continue;
      row.speakerOverride = name;
      speakerChanges[row.file + ':' + row.offset] = name;
    }
    document.getElementById('bulkSpeakerInput').value = '';
  } else {
    const tag = document.getElementById('bulkTag').value;
    for (const key of selection) {
      const row = rowIndex.get(key);
      if (!row) continue;
      row.tag = tag;
      tagChanges[row.file + ':' + row.offset] = tag;
      // 제외 태그면 KR도 비우기 (잘못 채워진 KR이 인서터에 닿지 않도록)
      if (tag === 'ignore') {
        modified[key] = '';
        row.kr = '';
      }
    }
  }
  selection.clear();
  rangeStart = null;
  updateBulkBar();
  updateStats();
  refreshSpeakers();
  render();
});

function bulkCopyField(field, btn) {
  const texts = [];
  for (const key of selection) {
    const row = rowIndex.get(key);
    if (!row) continue;
    if (field === 'kr') {
      texts.push(key in modified ? modified[key] : (row.kr || ''));
    } else {
      texts.push(row.jp || '');
    }
  }
  navigator.clipboard.writeText(texts.join('\n'));
  selection.clear();
  rangeStart = null;
  updateBulkBar();
  render();
}
document.getElementById('bulkCopyJp').addEventListener('click', e => bulkCopyField('jp', e.target));
document.getElementById('bulkCopyKr').addEventListener('click', e => bulkCopyField('kr', e.target));

document.getElementById('bulkCancel').addEventListener('click', () => {
  selection.clear();
  rangeStart = null;
  document.querySelectorAll('#tbody tr.row-selected, #tbody tr.range-start').forEach(tr => {
    tr.classList.remove('row-selected', 'range-start');
  });
  updateBulkBar();
});

// 바이트(len) 칸 클릭 → placeholder 제안을 KR에 채움 (빈 칸 + 시리즈 제안이 있을 때만).
// 값 주입 후 input 이벤트를 버블링 디스패치해 아래의 기존 입력 경로(변경 추적·바이트 갱신)를 그대로 탄다.
document.getElementById('tbody').addEventListener('click', e => {
  const td = e.target.closest('td.len');
  if (!td) return;
  const tr = td.closest('tr');
  const ta = tr && tr.querySelector('.kr-input');
  if (!ta || ta.value.trim()) return;
  const jp = (tr.querySelector('td.jp') || {}).dataset ? tr.querySelector('td.jp').dataset.jp : '';
  const s = window.__jpSuggest && window.__jpSuggest[normJp(jp)];
  if (!s) return;
  ta.value = s.kr;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
});

document.getElementById('tbody').addEventListener('input', e => {
  if (!e.target.classList.contains('kr-input')) return;
  const key = e.target.dataset.key;
  const row = rowIndex.get(key);
  const val = e.target.value;

  if (val === (row.kr || '')) {
    delete modified[key];
    e.target.classList.remove('modified');
  } else {
    modified[key] = val;
    e.target.classList.add('modified');
  }
  lastEditedKey = key;
  document.getElementById('jumpEditBtn').disabled = false;

  const isHalfwidth = row.halfwidth || row.type === 'ui';
  const jpLen = getJpLen(row);
  const krLen = val ? encodeByteLen(val, isHalfwidth) : 0;
  const lenTd = e.target.closest('tr').querySelector('.len');
  if (val) {
    lenTd.textContent = `${krLen}/${jpLen}`;
    lenTd.className = 'len ' + (krLen <= jpLen ? 'ok' : 'over');
    // kr이 채워지면 draft 버튼 제거
    const hint = e.target.closest('td.kr-cell').querySelector('.draft-hint');
    if (hint) hint.remove();
  } else {
    lenTd.textContent = `${jpLen}`;
    lenTd.className = 'len empty';
    // kr이 비워지면 draft 버튼 복원
    const cell = e.target.closest('td.kr-cell');
    if (!cell.querySelector('.draft-hint') && window.__draftMap && window.__draftMap[row.offset]) {
      const draft = window.__draftMap[row.offset];
      const mainBtn = `<button class="draft-btn" data-kr="${escAttr(draft.main)}">${draft.star ? '★초벌' : '초벌'}</button>`;
      const altBtn = draft.alt ? `<button class="draft-btn draft-alt" data-kr="${escAttr(draft.alt)}">압축안</button>` : '';
      cell.insertAdjacentHTML('beforeend', `<div class="draft-hint">${mainBtn}${altBtn}</div>`);
    }
  }

  recomputeOverflow();
  updateStats();
});

document.getElementById('saveBtn').addEventListener('click', async () => {
  const btn = document.getElementById('saveBtn');
  btn.disabled = true;
  btn.textContent = '저장 중...';

  // 저장 시 JP 텍스트도 함께 전송 — 서버에서 오프셋 일치 여부 검증용
  const jps = {};
  for (const key of Object.keys(modified)) {
    const row = rowIndex.get(key);
    if (row) jps[key] = row.jp;
  }
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ translations: modified, tags: tagChanges, speakers: speakerChanges, jps }),
  });
  const result = await res.json();

  const tbody = document.getElementById('tbody');
  // 저장된 KR 행: in-memory 반영 + 해당 DOM만 콕 집어 갱신 (전체 행 순회 제거)
  for (const [key, val] of Object.entries(modified)) {
    const row = rowIndex.get(key);
    if (row) row.kr = val;
    const tr = tbody.querySelector(`tr[data-key="${key}"]`);  // 렌더된 경우만
    if (!tr) continue;
    const el = tr.querySelector('.kr-input.modified');
    if (el) {
      el.classList.remove('modified');
      el.classList.add('saved');
      setTimeout(() => el.classList.remove('saved'), 1500);
    }
    // kr이 채워졌으면 draft 버튼 제거
    if (row && row.kr) {
      const hint = tr.querySelector('.draft-hint');
      if (hint) hint.remove();
    }
  }
  // 태그 변경도 in-memory rows에 반영 (화면 즉시 갱신)
  for (const [key, tag] of Object.entries(tagChanges)) {
    const [file, offsetStr] = key.split(':');
    const offset = parseInt(offsetStr);
    const row = rows.find(r => r.file === file && r.offset === offset);
    if (row) row.tag = tag;
  }
  refreshSpeakers();
  modified = {};
  tagChanges = {};
  speakerChanges = {};

  btn.textContent = '저장';
  updateStats();
  const msg = result.skipped
    ? `${result.updated}건 저장됨 (⚠ ${result.skipped}건 JP 불일치로 스킵 — 페이지 새로고침 필요)`
    : `${result.updated}건 저장됨`;
  showToast(msg, result.skipped ? 'err' : 'ok');
});

let _toastTimer = null;
function showToast(msg, type) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.style.background = type === 'ok' ? '#2a9d5c' : type === 'err' ? '#c0392b' : '#333';
  clearTimeout(_toastTimer);
  toast.classList.add('show');
  const dur = type === 'err' ? 6000 : 2500;
  _toastTimer = setTimeout(() => toast.classList.remove('show'), dur);
}

// 미저장 편집 여부 (메모리에만 있고 디스크 미반영). 빌드/번들/배포는 디스크 json을 읽으므로 가드.
function hasUnsaved() {
  return Object.keys(modified).length + Object.keys(tagChanges).length + Object.keys(speakerChanges).length > 0;
}

// 미저장 상태로 탭 닫기·새로고침 시 브라우저 경고
window.addEventListener('beforeunload', e => {
  if (hasUnsaved()) { e.preventDefault(); e.returnValue = ''; }
});

document.getElementById('buildBtn').addEventListener('click', async () => {
  if (hasUnsaved()) { showToast('미저장 변경이 있습니다 — 저장 후 빌드하세요', 'err'); return; }
  const btn = document.getElementById('buildBtn');
  btn.disabled = true;
  btn.textContent = '빌드 중...';
  btn.style.background = '#555';

  try {
    const res = await fetch('/api/build', { method: 'POST' });
    const result = await res.json();
    showToast(result.message, result.ok ? 'ok' : 'err');
  } catch (e) {
    showToast('빌드 실패: ' + e.message, 'err');
  }

  btn.disabled = false;
  btn.textContent = '빌드';
  btn.style.background = '';
});

// ── 헤더 sticky offset ──
function updateStickyOffset() {
  const h = document.querySelector('.topbar').offsetHeight;
  document.documentElement.style.setProperty('--topbar-h', h + 'px');
}
updateStickyOffset();

// ── Enter → 다음 행 이동 ──
document.getElementById('tbody').addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.shiftKey) return;
  const ta = e.target.closest('.kr-input');
  if (!ta) return;
  e.preventDefault();
  const all = Array.from(document.querySelectorAll('#tbody .kr-input'));
  const idx = all.indexOf(ta);
  if (idx >= 0 && idx < all.length - 1) {
    all[idx + 1].focus();
    all[idx + 1].select();
  }
});

document.getElementById('filterType').addEventListener('change', render);
document.getElementById('filterFile').addEventListener('change', render);
document.getElementById('filterSpeaker').addEventListener('change', render);
document.getElementById('filterUntranslated').addEventListener('change', render);
document.getElementById('filterHalfwidth').addEventListener('change', render);
document.getElementById('filterShowIgnore').addEventListener('change', render);
document.getElementById('filterExact').addEventListener('change', render);

let searchTimer = null;
document.getElementById('searchBox').addEventListener('input', e => {
  const prev = lastSearch;
  lastSearch = e.target.value;
  // 디바운스 — 대용량 타이틀(포물장 ~1.4만 행)에서 키 입력마다 전체 렌더 방지
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    render();
    // 검색 해제 시 단일 선택 항목으로 스크롤
    if (prev && !lastSearch && selection.size === 1) {
      const key = [...selection][0];
      const tr = document.querySelector(`#tbody tr[data-key="${CSS.escape(key)}"]`);
      if (tr) tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, 130);
});

// ── 초과 항목 이동 ──
function scrollToOverflow(idx) {
  if (overflowRows.length === 0) return;
  overflowIdx = (idx + overflowRows.length) % overflowRows.length;
  const r = overflowRows[overflowIdx];
  const key = rowKey(r);
  document.querySelectorAll('#tbody tr.overflow-focus').forEach(tr => tr.classList.remove('overflow-focus'));
  const tr = document.querySelector(`#tbody tr[data-key="${CSS.escape(key)}"]`);
  if (tr) {
    tr.classList.add('overflow-focus');
    tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

document.getElementById('overPrev').addEventListener('click', () => {
  scrollToOverflow(overflowIdx <= 0 ? overflowRows.length - 1 : overflowIdx - 1);
});
document.getElementById('overNext').addEventListener('click', () => {
  scrollToOverflow(overflowIdx + 1);
});


document.getElementById('fillApply').addEventListener('click', () => {
  const val = document.getElementById('fillInput').value;
  if (!val) return;
  for (const r of filteredRows) {
    const key = rowKey(r);
    modified[key] = val;
    r.kr = val;
  }
  render();
  updateStats();
});

function jumpToLastEdit() {
  if (!lastEditedKey) return;
  const tr = document.querySelector(`#tbody tr[data-key="${CSS.escape(lastEditedKey)}"]`);
  if (!tr) return;
  tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  const ta = tr.querySelector('.kr-input');
  if (ta) ta.focus();
}
document.getElementById('jumpEditBtn').addEventListener('click', jumpToLastEdit);

document.addEventListener('keydown', e => {
  if (e.ctrlKey && !e.metaKey && e.code === 'KeyS') {
    e.preventDefault();
    const btn = document.getElementById('saveBtn');
    if (!btn.disabled) btn.click();
    return;
  }
  if (e.ctrlKey && !e.metaKey && e.code === 'KeyD') {
    e.preventDefault();
    jumpToLastEdit();
    return;
  }
  // 입력 필드 안에서는 무시
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === '[') { e.preventDefault(); scrollToOverflow(overflowIdx <= 0 ? overflowRows.length - 1 : overflowIdx - 1); }
  if (e.key === ']') { e.preventDefault(); scrollToOverflow(overflowIdx + 1); }
});

document.getElementById('tbody').addEventListener('click', e => {
  const draftBtn = e.target.closest('.draft-btn');
  if (draftBtn) {
    e.stopPropagation();
    const textarea = draftBtn.closest('td.kr-cell').querySelector('.kr-input');
    textarea.value = draftBtn.dataset.kr;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.focus();
    return;
  }
  const span = e.target.closest('.taggable');
  if (!span) return;
  e.stopPropagation();
  const offset = parseInt(span.dataset.offset);
  const file = span.dataset.file;
  const row = rows.find(r => r.offset === offset && r.file === file && (r.type === 'dialog' || r.type === 'item' || r.type === 'ui' || r.type === 'gsovl' || r.type === 'demo' || r.taggable));
  if (!row) return;
  selection.clear();
  selection.add(rowKey(row));
  rangeStart = null;
  document.querySelectorAll('#tbody tr.row-selected').forEach(tr => tr.classList.remove('row-selected'));
  e.target.closest('tr').classList.add('row-selected');
  updateBulkBar();
  updateStats();
});

document.getElementById('emulatorBtn').addEventListener('click', async () => {
  if (hasUnsaved()) { showToast('미저장 변경이 있습니다 — 저장 후 진행하세요', 'err'); return; }
  const btn = document.getElementById('emulatorBtn');
  btn.disabled = true;
  btn.textContent = '생성 중...';
  btn.style.background = '#555';

  try {
    const res = await fetch('/api/emulator-update', { method: 'POST' });
    const result = await res.json();
    showToast(result.message, result.ok ? 'ok' : 'err');
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  }

  btn.disabled = false;
  btn.textContent = '번들';
  btn.style.background = '';
});

document.getElementById('deployBtn').addEventListener('click', async () => {
  if (hasUnsaved()) { showToast('미저장 변경이 있습니다 — 저장 후 진행하세요', 'err'); return; }
  const btn = document.getElementById('deployBtn');
  btn.disabled = true;
  btn.textContent = '배포 중...';
  btn.style.background = '#555';

  try {
    const res = await fetch('/api/deploy-docs', { method: 'POST' });
    const result = await res.json();
    showToast(result.message, result.ok ? 'ok' : 'err');
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  }

  btn.disabled = false;
  btn.textContent = '배포';
  btn.style.background = '';
});

load().then(() => {
  if (!__HAS_INSERTER__) {
    const btn = document.getElementById('buildBtn');
    btn.disabled = true;
    btn.title = '인서터 미구현';
    btn.style.opacity = '0.35';
    btn.style.cursor = 'default';
  }
  if (!__HAS_EMULATOR__) {
    for (const id of ['emulatorBtn', 'deployBtn']) {
      const btn = document.getElementById(id);
      btn.disabled = true;
      btn.title = '에뮬레이터 없음';
      btn.style.opacity = '0.35';
      btn.style.cursor = 'default';
    }
  }
});
</script>
</body>
</html>"""


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>빌드·배포 대시보드</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Malgun Gothic', sans-serif; background: #1e1e1e; color: #d4d4d4; padding: 16px; font-size: 14px; width: 800px; }
h1 { font-size: 15px; font-weight: 600; color: #bbb; margin-bottom: 12px; }
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.btn { background: transparent; color: #999; border: 1px solid #3a3a3a; height: 28px; padding: 0 14px; border-radius: 4px; cursor: pointer; font-size: 12px; font-family: inherit; }
.btn:hover { background: #2a2a2a; color: #ddd; border-color: #555; }
.btn:disabled { opacity: 0.35; cursor: default; }
.btn.primary { background: #1a3d1a; color: #7dc87d; border-color: #2d5c2d; }
.btn.primary:hover { background: #234d23; }
.btn.danger { background: #3d1a1a; color: #e08080; border-color: #5c2d2d; }
.btn.danger:hover { background: #4d2323; }
table { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
th { text-align: left; padding: 6px 8px; font-size: 11px; color: #666; border-bottom: 1px solid #333; font-weight: 600; }
td { padding: 8px; border-bottom: 1px solid #252525; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
.title-name { color: #ccc; font-weight: 600; white-space: nowrap; }
.stage { display: flex; align-items: center; gap: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.badge-ok { background: #1a3520; color: #70c880; }
.badge-stale { background: #332800; color: #d4b060; }
.badge-missing { background: #2a2a2a; color: #777; }
.badge-err { background: #3a1a1a; color: #e08080; }
.hint { font-size: 11px; color: #666; margin-left: 4px; }
.stage-btn { background: #2e2e2e; color: #ccc; border: 1px solid #4a4a4a; height: 24px; padding: 0 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-family: inherit; }
.stage-btn:hover { background: #3a3a3a; color: #fff; }
.stage-btn:disabled { background: #1e1e1e; color: #444; border-color: #2a2a2a; cursor: default; }
.deploy-bar { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.deploy-row { display: flex; align-items: center; gap: 10px; }
.deploy-warn { font-size: 12px; color: #d4b060; }
.deploy-warn b { color: #e0a060; }
.commit-bar { background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 4px; padding: 12px; display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
#commitFiles { font-family: monospace; font-size: 11px; color: #777; white-space: pre-wrap; max-height: 100px; overflow-y: auto; background: #141414; border: 1px solid #2a2a2a; border-radius: 4px; padding: 6px 8px; }
#commitMsg { width: 100%; background: #252525; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 6px 8px; border-radius: 4px; font-size: 13px; font-family: inherit; resize: vertical; }
#commitMsg:focus { outline: none; border-color: #555; }
details.log { margin-top: 14px; }
summary { cursor: pointer; font-size: 12px; color: #888; padding: 4px 0; }
summary:hover { color: #bbb; }
#logContent { background: #141414; border: 1px solid #2a2a2a; border-radius: 4px; padding: 10px; margin-top: 6px; font-family: monospace; font-size: 11px; color: #999; white-space: pre-wrap; word-break: break-all; max-height: 320px; overflow-y: auto; }
.toast { position: fixed; bottom: 24px; right: 24px; background: #2a2a2a; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 9px 16px; border-radius: 4px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity 0.2s; max-width: 340px; box-shadow: 0 4px 16px rgba(0,0,0,0.5); z-index: 100; }
.toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="topbar">
  <h1>빌드·배포 대시보드</h1>
  <button class="btn primary" id="runAllBtn">전체 빌드+번들</button>
</div>
<table>
<thead><tr>
  <th style="width:90px">타이틀</th>
  <th>빌드</th>
  <th>번들</th>
  <th>배포</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<div class="deploy-bar">
  <div class="deploy-row">
    <button class="btn primary" id="deployBtn">배포</button>
    <span id="deployHint" class="hint">emulator → docs 동기화 + 정합 검사 (전 타이틀 공용)</span>
  </div>
  <div class="deploy-row" id="sharedStatus"></div>
  <div id="deployWarn" style="display:none"></div>
</div>
<div class="commit-bar" id="commitBar" style="display:none">
  <div class="deploy-row">
    <span class="hint" style="margin-left:0">커밋 대상 (translation/·emulator/·docs/ — tools/ 등 다른 작업 중인 변경은 포함 안 함)</span>
  </div>
  <div id="commitFiles"></div>
  <textarea id="commitMsg" rows="2" placeholder="커밋 메시지 (자동 작성됨, 수정 가능)"></textarea>
  <div class="deploy-row">
    <button class="btn primary" id="commitBtn">커밋</button>
  </div>
</div>
<details class="log" id="logPanel">
  <summary>실행 로그</summary>
  <div id="logContent"></div>
</details>
<div class="toast" id="toast"></div>

<script>
const TITLE_ORDER = ['hukyou', 'kaitou', 'torimono', 'kitan'];
const STAGE_LABELS = {
  build:  { missing: '미빌드',   stale: '빌드 필요',   ok: '빌드됨' },
  bundle: { missing: '미번들',   stale: '번들 필요',   ok: '번들됨' },
  deploy: { missing: '미배포',   stale: '배포 필요',   ok: '배포됨' },
};
let statusData = {};
let sharedData = { state: 'ok', files: [] };
let commitData = { files: [], message: '' };
// 배치·단일 실행 중 잠금. render() 가 행을 다시 그려도 이 플래그로 잠금이 복원된다
// (안 그러면 배치 도중 loadStatus→render 마다 버튼이 되살아나 중복 실행됨).
let busy = false;

function badge(kind, stage) {
  const cls = stage === 'ok' ? 'badge-ok' : stage === 'stale' ? 'badge-stale' : 'badge-missing';
  const label = STAGE_LABELS[kind][stage] || stage;
  return `<span class="badge ${cls}">${label}</span>`;
}

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.borderColor = type === 'err' ? '#5c2d2d' : '#3a3a3a';
  t.style.color = type === 'err' ? '#e08080' : '#d4d4d4';
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3200);
}

function appendLog(titleKr, action, result) {
  const el = document.getElementById('logContent');
  const time = new Date().toLocaleTimeString('ko-KR', { hour12: false });
  let line = `[${time}] ${titleKr} · ${action} — ${result.ok ? 'OK' : 'FAIL'} : ${result.message}`;
  if (result.warnings && result.warnings.length) line += `\n  ⚠ ${result.warnings.join(' / ')}`;
  if (result.output) line += `\n${result.output.trim()}`;
  el.textContent = (el.textContent ? el.textContent + '\n\n' : '') + line;
  el.scrollTop = el.scrollHeight;
  document.getElementById('logPanel').open = true;
}

async function loadStatus() {
  const [statusRes, commitRes] = await Promise.all([
    fetch('/api/pipeline/status'),
    fetch('/api/pipeline/commit-status'),
  ]);
  const data = await statusRes.json();
  statusData = data.titles;
  sharedData = data.shared;
  commitData = await commitRes.json();
  render();
}

function render() {
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  let anyBlocked = [];

  for (const t of TITLE_ORDER) {
    const s = statusData[t];
    if (!s) continue;
    if (s.deploy_blocked) anyBlocked.push(s.title_kr);

    const tr = document.createElement('tr');

    // 고유 비활성(인서터·에뮬 없음 등)은 data-off 로 표시만 하고, 최종 disabled 는
    // syncButtons() 가 busy 와 함께 계산한다.
    const buildOff = !s.has_inserter ? 'data-off="1"' : '';
    const bundleOff = (!s.has_emulator || s.build === 'missing') ? 'data-off="1"' : '';

    let bundleExtra = '';
    if (t === 'kitan' && s.demo === 'missing') {
      bundleExtra = '<span class="hint">데모 스킵됨</span>';
    }

    tr.innerHTML = `
      <td class="title-name">${s.title_kr}</td>
      <td><div class="stage">${badge('build', s.build)}<button class="stage-btn" data-action="build" data-title="${t}" ${buildOff}>빌드</button></div></td>
      <td><div class="stage">${badge('bundle', s.bundle)}<button class="stage-btn" data-action="bundle" data-title="${t}" ${bundleOff}>번들</button>${bundleExtra}</div></td>
      <td><div class="stage">${badge('deploy', s.deploy)}${s.deploy_blocked ? '<span class="hint">⚠ 배포 시 이 타이틀에서 막힘</span>' : ''}</div></td>
    `;
    tbody.appendChild(tr);
  }

  // 공용 파일(version.js·audio.js·bios/ 등) — 어느 타이틀에도 안 묶이지만 배포 대상.
  const sharedEl = document.getElementById('sharedStatus');
  if (sharedData.state === 'ok') {
    sharedEl.innerHTML = `공용 파일 ${badge('deploy', 'ok')}`;
  } else {
    const list = sharedData.files.length ? ` <span class="hint">${sharedData.files.join(', ')}</span>` : '';
    sharedEl.innerHTML = `공용 파일 ${badge('deploy', sharedData.state)}${list}`;
  }

  const warnEl = document.getElementById('deployWarn');
  if (anyBlocked.length) {
    warnEl.style.display = 'block';
    warnEl.innerHTML = `<span class="deploy-warn">⚠ <b>${anyBlocked.join(', ')}</b> 빌드 신선도 경고로 배포가 막힐 수 있습니다.
      <button class="btn danger" id="forceDeployBtn" style="margin-left:8px">경고 무시하고 배포(-f)</button></span>`;
    document.getElementById('forceDeployBtn').addEventListener('click', () => runDeploy(true));
  } else {
    warnEl.style.display = 'none';
    warnEl.innerHTML = '';
  }

  renderCommit();
  syncButtons();
}

function renderCommit() {
  const bar = document.getElementById('commitBar');
  const msgEl = document.getElementById('commitMsg');
  if (!commitData.files || !commitData.files.length) {
    bar.style.display = 'none';
    return;
  }
  bar.style.display = 'flex';
  document.getElementById('commitFiles').textContent =
    commitData.files.map(f => `${f.status}  ${f.path}`).join('\n');
  // 사용자가 편집 중이면 자동 갱신으로 덮어쓰지 않는다.
  if (msgEl.dataset.dirty !== '1') msgEl.value = commitData.message;
}

function syncButtons() {
  document.querySelectorAll('.stage-btn, #runAllBtn, #deployBtn, #forceDeployBtn, #commitBtn').forEach(b => {
    b.disabled = busy || b.dataset.off === '1';
  });
}

function setBusy(v) { busy = v; syncButtons(); }

// fetch/파싱 예외까지 결과 객체로 흡수 — 호출부가 항상 {ok, message} 를 받게 해
// 예외로 흐름이 끊겨 잠금이 안 풀리는 일을 막는다.
async function callStage(action, title) {
  const label = action === 'build' ? '빌드' : '번들';
  try {
    const res = await fetch(`/api/pipeline/${action}?title=${title}`, { method: 'POST' });
    const result = await res.json();
    appendLog(statusData[title] ? statusData[title].title_kr : title, label, result);
    return result;
  } catch (e) {
    const result = { ok: false, message: `${label} 실패: ${e.message}` };
    appendLog(statusData[title] ? statusData[title].title_kr : title, label, result);
    return result;
  }
}

async function runDeploy(force) {
  setBusy(true);
  const btn = document.getElementById('deployBtn');
  const origText = btn.textContent;
  btn.textContent = '배포 중...';
  try {
    const res = await fetch(`/api/pipeline/deploy${force ? '?force=1' : ''}`, { method: 'POST' });
    const result = await res.json();
    appendLog('전체', force ? '배포(-f)' : '배포', result);
    showToast(result.message, result.ok ? 'ok' : 'err');
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  } finally {
    btn.textContent = origText;
    try { await loadStatus(); } catch (e) {}
    setBusy(false);
  }
}

document.getElementById('tbody').addEventListener('click', async (e) => {
  const btn = e.target.closest('.stage-btn');
  if (!btn || btn.disabled) return;
  const { action, title } = btn.dataset;
  setBusy(true);
  const origText = btn.textContent;
  btn.textContent = action === 'build' ? '빌드 중...' : '번들 중...';
  try {
    const result = await callStage(action, title);
    showToast(result.message, result.ok ? 'ok' : 'err');
  } finally {
    btn.textContent = origText;
    try { await loadStatus(); } catch (e) {}
    setBusy(false);
  }
});

document.getElementById('deployBtn').addEventListener('click', () => runDeploy(false));

document.getElementById('runAllBtn').addEventListener('click', async () => {
  setBusy(true);
  const runBtn = document.getElementById('runAllBtn');
  const origText = runBtn.textContent;
  try {
    await loadStatus();

    for (const t of TITLE_ORDER) {
      const s = statusData[t];
      if (!s || !s.has_inserter || s.build === 'ok') continue;
      runBtn.textContent = `${s.title_kr} 빌드 중...`;
      const r = await callStage('build', t);
      await loadStatus();
      if (!r.ok) { showToast(`${s.title_kr} 빌드 실패 — 중단`, 'err'); return; }
    }

    for (const t of TITLE_ORDER) {
      const s = statusData[t];
      if (!s || !s.has_emulator || s.bundle === 'ok') continue;
      runBtn.textContent = `${s.title_kr} 번들 중...`;
      const r = await callStage('bundle', t);
      await loadStatus();
      if (!r.ok) { showToast(`${s.title_kr} 번들 실패 — 중단`, 'err'); return; }
    }

    showToast('전체 빌드+번들 완료', 'ok');
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  } finally {
    runBtn.textContent = origText;
    setBusy(false);
  }
});

document.getElementById('commitMsg').addEventListener('input', (e) => {
  e.target.dataset.dirty = '1';
});

document.getElementById('commitBtn').addEventListener('click', async () => {
  const msgEl = document.getElementById('commitMsg');
  const message = msgEl.value.trim();
  if (!message) { showToast('커밋 메시지를 입력하세요', 'err'); return; }

  setBusy(true);
  const btn = document.getElementById('commitBtn');
  const origText = btn.textContent;
  btn.textContent = '커밋 중...';
  try {
    const res = await fetch('/api/pipeline/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const result = await res.json();
    appendLog('전체', '커밋', result);
    showToast(result.message, result.ok ? 'ok' : 'err');
    if (result.ok) {
      delete msgEl.dataset.dirty;
      await loadStatus();
    }
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  } finally {
    btn.textContent = origText;
    setBusy(false);
  }
});

loadStatus();
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if DASHBOARD_MODE:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())
            elif parsed.path == '/api/pipeline/status':
                self._send_json(pipeline.status())
            elif parsed.path == '/api/pipeline/commit-status':
                self._send_json(pipeline.commit_status())
            else:
                self.send_error(404)
            return

        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = (HTML
                    .replace('__TITLE_KR__', TITLE_KR)
                    .replace('__HAS_INSERTER__', 'true' if HAS_INSERTER else 'false')
                    .replace('__HAS_EMULATOR__', 'true' if HAS_EMULATOR else 'false'))
            self.wfile.write(html.encode())
        elif self.path == '/api/translation':
            self.send_json_file(TRANS_PATH)
        elif self.path == '/api/charmap':
            self.send_json_file(CHARMAP_PATH)
        elif self.path == '/api/series-glossary':
            # 입력 보조용 시리즈 용어집 (현재 타이틀 우선)
            self._send_json(lint.series_glossary(TITLE))
        elif self.path == '/api/draft':
            self._send_json(load_draft_map())
        else:
            self.send_error(404)

    def do_POST(self):
        if DASHBOARD_MODE:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            title = qs.get('title', [''])[0]
            if parsed.path == '/api/pipeline/build':
                if title not in pipeline.TITLES:
                    self._send_json_error('알 수 없는 타이틀', 400)
                    return
                self._send_json(pipeline.build(title))
            elif parsed.path == '/api/pipeline/bundle':
                if title not in pipeline.TITLES:
                    self._send_json_error('알 수 없는 타이틀', 400)
                    return
                self._send_json(pipeline.bundle(title))
            elif parsed.path == '/api/pipeline/deploy':
                force = qs.get('force', ['0'])[0] in ('1', 'true')
                self._send_json(pipeline.deploy(force=force))
            elif parsed.path == '/api/pipeline/commit':
                length = int(self.headers.get('Content-Length', 0))
                try:
                    body = json.loads(self.rfile.read(length)) if length else {}
                except Exception:
                    body = {}
                self._send_json(pipeline.commit(body.get('message', '')))
            else:
                self.send_error(404)
            return

        if self.path == '/api/save':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            result = self.apply_changes(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == '/api/build':
            result = self.run_build()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif self.path == '/api/emulator-update':
            self.handle_emulator_update()
        elif self.path == '/api/deploy-docs':
            result = self.run_deploy_docs()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_error(404)

    def send_json_file(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)

    def apply_changes(self, body):
        with open(TRANS_PATH, encoding='utf-8') as f:
            data = json.load(f)

        translations = body.get('translations', {})
        tags = body.get('tags', {})
        speakers = body.get('speakers', {})  # 수동 화자 지정 (kaitou 포맷 전용)
        jps = body.get('jps', {})  # JP 텍스트 검증용

        updated = skipped = 0

        if data.get('entries') is not None:
            # kaitou 포맷: flat entries 리스트
            # 전역 오프셋 = chunk * 200000 + local_offset
            CHUNK_BASE = 200000

            def _find_kaitou_seg(entries, typ, global_offset):
                """전역 오프셋으로 lines 항목 반환."""
                chunk_idx = global_offset // CHUNK_BASE
                local_off = global_offset % CHUNK_BASE
                for entry in entries:
                    if entry.get('chunk') != chunk_idx:
                        continue
                    for line in entry.get('lines', []):
                        if line.get('offset') == local_off:
                            return line
                return None

            for key, kr in translations.items():
                parts = key.split(':', 2)
                typ, file_name, offset_str = parts[0], parts[1], parts[2]
                global_offset = int(offset_str)
                expected_jp = jps.get(key)
                target = _find_kaitou_seg(data['entries'], typ, global_offset)
                if target is None:
                    skipped += 1
                    continue
                if expected_jp and target.get('jp') != expected_jp:
                    skipped += 1
                else:
                    target['kr'] = kr
                    updated += 1

            for key, tag in tags.items():
                file_name, offset_str = key.split(':', 1)
                global_offset = int(offset_str)
                chunk_idx = global_offset // CHUNK_BASE
                local_off = global_offset % CHUNK_BASE
                for entry in data['entries']:
                    if entry.get('chunk') != chunk_idx:
                        continue
                    for container in entry.get('lines', []):
                        if container.get('offset') == local_off:
                            container['tag'] = tag
                            updated += 1

            # 수동 화자 지정: line['speaker'] 에 기록. 빈값 = override 해제(필드 제거 → 자동 복귀)
            for key, name in speakers.items():
                file_name, offset_str = key.split(':', 1)
                global_offset = int(offset_str)
                line = _find_kaitou_seg(data['entries'], None, global_offset)
                if line is not None:
                    if name:
                        line['speaker'] = name
                    else:
                        line.pop('speaker', None)
                    updated += 1

        else:
            # hukyou 포맷: dialogs / items / ui 구조
            for key, kr in translations.items():
                parts = key.split(':', 2)
                typ, file_name, offset_str = parts[0], parts[1], parts[2]
                offset = int(offset_str)
                expected_jp = jps.get(key)

                if typ == 'dialog':
                    for dialog in data['dialogs']:
                        if dialog['file'] != file_name:
                            continue
                        for line in dialog['lines']:
                            if line['offset'] == offset:
                                if expected_jp and line['jp'] != expected_jp:
                                    skipped += 1
                                else:
                                    line['kr'] = kr
                                    updated += 1
                elif typ == 'item':
                    for item in data.get('items', []):
                        for field in ([item['name']] +
                                      ([item['stat']] if 'stat' in item else []) +
                                      item['desc']):
                            if field['offset'] == offset:
                                field['kr'] = kr
                                updated += 1
                elif typ == 'ui':
                    for entry in data.get('ui', []):
                        if entry['offset'] == offset:
                            entry['kr'] = kr
                            updated += 1
                elif typ == 'gsovl':
                    for entry in data.get('gsovl', []):
                        if entry['offset'] == offset:
                            entry['kr'] = kr
                            updated += 1
                elif typ == 'demo':
                    for entry in data.get('demo', []):
                        if entry['offset'] == offset:
                            entry['kr'] = kr
                            updated += 1

            for key, tag in tags.items():
                file_name, offset_str = key.split(':', 1)
                offset = int(offset_str)
                for section in ('ui', 'gsovl', 'demo'):
                    for entry in data.get(section, []):
                        if entry['offset'] == offset:
                            entry['tag'] = tag
                            updated += 1
                for dialog in data.get('dialogs', []):
                    if dialog['file'] != file_name:
                        continue
                    for line in dialog['lines']:
                        if line['offset'] == offset:
                            line['tag'] = tag
                            updated += 1
                for item in data.get('items', []):
                    for field in ([item['name']] +
                                  ([item['stat']] if 'stat' in item else []) +
                                  item['desc']):
                        if field['offset'] == offset:
                            field['tag'] = tag
                            updated += 1

        with open(TRANS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {'updated': updated, 'skipped': skipped}

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json_error(self, message, code=400):
        body = json.dumps({'message': message}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_emulator_update(self):
        if not HAS_EMULATOR:
            self._send_json_error('에뮬레이터 업데이트 미지원', 400)
            return
        result = pipeline.bundle(TITLE)
        # 편집 화면의 기존 규약 유지: 실패는 400/500 + {message}, 성공은 200 + {ok, message}.
        # (대시보드는 같은 pipeline.bundle 을 쓰되 output·warnings 까지 그대로 받아 간다)
        if not result.get('ok'):
            self._send_json_error(result['message'], result.get('code', 500))
            return
        self._send_json({'ok': True, 'message': result['message']})

    def run_build(self):
        return pipeline.build(TITLE)

    def run_deploy_docs(self):
        return pipeline.deploy()


if __name__ == '__main__':
    port = 8182  # JP(81) → KR(82)
    url = f'http://localhost:{port}'
    try:
        server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    except OSError as e:
        print(f'포트 {port} 를 열 수 없습니다: {e}')
        print('이미 에디터가 떠 있지 않은지 확인하세요 (편집·대시보드는 한 번에 하나만).')
        sys.exit(1)

    label = TITLE_KR if DASHBOARD_MODE else f'[{TITLE_KR}] 번역 에디터'
    print(f'{label}: {url}')
    print('종료: Ctrl+C')

    # 서버를 백그라운드로 먼저 띄운다 — serve_forever() 전에 브라우저를 열면
    # 연결 거부를 맞는다.
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if not NO_OPEN:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f'(브라우저 자동 실행 실패 — 직접 열어주세요: {e})')

    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass
