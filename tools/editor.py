"""
번역 웹 에디터
==============

사용법:
  python3 tools/editor.py <title>
  브라우저에서 http://localhost:8182 접속

  <title>: hukyou | kaitou | torimono | kitan (기본값: hukyou)

translation.json의 kr 필드를 브라우저에서 편집, 저장.
"""

import http.server
import json
import os
import re
import subprocess
import sys
import urllib.parse

TITLES = {
    'hukyou':   '환세풍광전',
    'kaitou':   '환세쾌도전',
    'torimono': '환세포물장',
    'kitan':    '환세희담',
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# emsdk file_packager.py 경로 (번들 재생성용)
FILE_PACKAGER = os.path.expanduser(
    '~/GitHub/emsdk/upstream/emscripten/tools/file_packager.py'
)

def resolve_title():
    title = sys.argv[1] if len(sys.argv) > 1 else 'hukyou'
    if title not in TITLES:
        print(f'알 수 없는 타이틀: {title!r}')
        print(f'사용 가능: {", ".join(TITLES)}')
        sys.exit(1)
    return title

TITLE = resolve_title()
TITLE_KR = TITLES[TITLE]
TRANS_PATH = os.path.join(PROJECT_ROOT, 'translation', TITLE, 'translation.json')
CHARMAP_PATH = os.path.join(PROJECT_ROOT, 'tools', 'charmap.json')
HAS_INSERTER = os.path.exists(os.path.join(PROJECT_ROOT, 'tools', f'{TITLE}_inserter.py'))
HAS_EMULATOR = (
    (TITLE == 'hukyou' and os.path.exists(os.path.join(PROJECT_ROOT, 'emulator', 'emnp2kai_sdl2.js'))) or
    (TITLE == 'kitan'  and os.path.exists(os.path.join(PROJECT_ROOT, 'emulator', 'kitan.js')))
)

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
#emulatorBtn { width: 80px; }
#jumpEditBtn { width: 32px; padding: 0; font-size: 14px; }
.build-btn:hover { background: #2a2a2a; color: #ddd; border-color: #555; }
.toast { position: fixed; bottom: 24px; right: 24px; background: #2a2a2a; color: #d4d4d4; border: 1px solid #3a3a3a; padding: 9px 16px; border-radius: 4px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity 0.2s; max-width: 340px; box-shadow: 0 4px 16px rgba(0,0,0,0.5); }
.toast.show { opacity: 1; }
tr.row-selected { background: #1a2840 !important; }
tr.range-start { background: #252000 !important; }
#tbody tr { cursor: pointer; }
#tbody tr td.kr-cell { cursor: default; }
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
    <button class="build-btn" id="buildBtn">빌드</button>
    <button class="build-btn" id="emulatorBtn">번들 생성</button>
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
    <option value="battle">전투</option>
    <option value="system">시스템</option>
  </select>
  <select id="filterFile">
    <option value="">전체 파일</option>
  </select>
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
  <select id="bulkTag">
    <option value="dialog">대사</option>
    <option value="monolog">독백</option>
    <option value="cutscene">컷씬</option>
    <option value="char">캐릭터</option>
    <option value="battle">전투</option>
    <option value="item">아이템</option>
    <option value="menu">메뉴</option>
    <option value="location">장소</option>
    <option value="system">시스템</option>
    <option value="ignore">제외</option>
  </select>
  <button class="bulk-apply" id="bulkApply">적용</button>
  <button class="bulk-cancel" id="bulkCancel">취소</button>
</div>

<script>
let rows = [];
let modified = {};
let tagChanges = {};
let charmap = {};
let selection = new Set();
let filteredRows = [];
let rangeStart = null;
let overflowRows = [];   // filteredRows 중 초과 항목
let overflowIdx = -1;
let lastSearch = '';
let lastEditedKey = null;

function rowKey(r) { return r.type + ':' + r.file + ':' + r.offset; }

function updateBulkBar() {
  const bar = document.getElementById('bulkBar');
  if (selection.size === 0) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  document.getElementById('bulkCount').textContent = selection.size + '행 선택';
}

async function load() {
  const [transRes, charmapRes] = await Promise.all([
    fetch('/api/translation'),
    fetch('/api/charmap'),
  ]);
  const data = await transRes.json();
  charmap = await charmapRes.json();
  rows = [];

  if (data.entries) {
    // kaitou / 새 포맷: flat entries 리스트
    // 전역 오프셋 = chunk * 200000 + local_offset (청크 내 최대 해제 크기 < 200000 보장)
    // 칼럼 헤더 + 필터 레이블을 청크용으로 교체
    document.querySelector('th.file').textContent = '청크';
    document.querySelector('#filterFile option[value=""]').textContent = '전체 청크';

    for (const entry of data.entries) {
      const base = entry.chunk * 200000;
      const speaker = entry.speaker || '';
      const chunkLabel = '청크 ' + String(entry.chunk).padStart(2, '0');
      for (const line of (entry.lines || [])) {
        rows.push({
          type: 'dialog', tag: line.tag || null, file: chunkLabel,
          chunk: entry.chunk, offset: base + line.offset, localOffset: line.offset,
          jp: line.jp, kr: line.kr, jp_len: line.jp_len,
          halfwidth: false, taggable: true, speaker: speaker,
        });
      }
    }
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

  render();
}

const ASCII_FULLWIDTH = new Set([' ', '.', ',', '!', '?', '(', ')', '+', '=', '~',
  '0','1','2','3','4','5','6','7','8','9',
  'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
  'a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z']);

function encodeByteLen(text, useHalfwidth) {
  let len = 0;
  for (const ch of text) {
    if (charmap[ch]) { len += 2; }
    else if (useHalfwidth) { len += 2; }
    else if (ASCII_FULLWIDTH.has(ch)) { len += 2; }
    else if (ch.charCodeAt(0) < 0x80) { len += 1; }
    else { len += 2; }
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

const TAG_LABELS = { dialog: '대사', monolog: '독백', cutscene: '컷씬', char: '캐릭터', battle: '전투', item: '아이템', menu: '메뉴', location: '장소', system: '시스템', ignore: '제외' };
const DIALOG_TAGS = ['dialog', 'monolog', 'cutscene', 'char', 'battle', 'item', 'menu', 'location', 'system', 'ignore'];

function typeLabel(r) {
  const effective = r.tag || r.type;
  const label = TAG_LABELS[effective] || effective;
  const TYPE_CSS = { dialog: 'type-dialog', monolog: 'type-monolog', cutscene: 'type-cutscene', char: 'type-char', battle: 'type-battle', item: 'type-item', item_name: 'type-item', item_stat: 'type-item', item_desc: 'type-item', menu: 'type-menu', location: 'type-location', system: 'type-system', ignore: 'type-ignore' };
  const cls = TYPE_CSS[effective] || 'type-dialog';
  const taggable = (r.type === 'dialog' || r.type === 'item' || r.type === 'ui' || r.type === 'gsovl' || r.type === 'demo' || r.taggable) ? ' taggable' : '';
  return `<div class="${cls}"><span class="${taggable}" data-file="${r.file || ''}" data-offset="${r.offset}">${label}</span></div>`;
}

function render() {
  const filterType = document.getElementById('filterType').value;
  const filterFile = document.getElementById('filterFile').value;
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
    tr.innerHTML = `
      <td class="type">${typeLabel(r)}</td>
      <td class="file">${r.file}</td>
      <td class="off">${r.localOffset !== undefined ? r.localOffset : ''}</td>
      <td class="jp" title="클릭하여 복사" onclick="navigator.clipboard.writeText(this.dataset.jp);this.classList.add('copied');setTimeout(()=>this.classList.remove('copied'),600)" data-jp="${escAttr(r.jp)}">${speakerHtml}${escHtml(r.jp)}${r.halfwidth ? '<span class="halfwidth-badge">반</span>' : ''}</td>
      <td class="kr-cell"><textarea class="kr-input${key in modified ? ' modified' : ''}" data-key="${key}" placeholder="번역 입력..." rows="1">${escHtml(kr)}</textarea></td>
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
  const changes = mod + tags;
  const pct = total ? Math.round(100 * done / total) : 0;
  const circ = 2 * Math.PI * 14;
  document.getElementById('donutArc').setAttribute('stroke-dasharray', `${circ * pct / 100} ${circ}`);
  const filteredInfo = filteredRows.length < total ? ` | 표시: ${filteredRows.length}건` : '';
  const modInfo = mod ? ` | 수정: ${mod}건` : '';
  const tagInfo = tags ? ` | 분류: ${tags}건` : '';
  document.getElementById('statsText').textContent = `${pct}% (${done}/${total})${filteredInfo}${modInfo}${tagInfo}`;
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

document.getElementById('bulkApply').addEventListener('click', () => {
  const tag = document.getElementById('bulkTag').value;
  for (const key of selection) {
    const row = rows.find(r => rowKey(r) === key);
    if (!row) continue;
    row.tag = tag;
    tagChanges[row.file + ':' + row.offset] = tag;
    // 제외 태그면 KR도 비우기 (잘못 채워진 KR이 인서터에 닿지 않도록)
    if (tag === 'ignore') {
      modified[key] = '';
      row.kr = '';
    }
  }
  selection.clear();
  rangeStart = null;
  updateBulkBar();
  updateStats();
  render();
});

function bulkCopyField(field, btn) {
  const texts = [];
  for (const key of selection) {
    const row = rows.find(r => rowKey(r) === key);
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

document.getElementById('tbody').addEventListener('input', e => {
  if (!e.target.classList.contains('kr-input')) return;
  const key = e.target.dataset.key;
  const row = rows.find(r => r.type + ':' + r.file + ':' + r.offset === key);
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
  } else {
    lenTd.textContent = `${jpLen}`;
    lenTd.className = 'len empty';
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
    const row = rows.find(r => r.type + ':' + r.file + ':' + r.offset === key);
    if (row) jps[key] = row.jp;
  }
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ translations: modified, tags: tagChanges, jps }),
  });
  const result = await res.json();

  for (const [key, val] of Object.entries(modified)) {
    const row = rows.find(r => r.type + ':' + r.file + ':' + r.offset === key);
    if (row) row.kr = val;
  }
  // 태그 변경도 in-memory rows에 반영 (화면 즉시 갱신)
  for (const [key, tag] of Object.entries(tagChanges)) {
    const [file, offsetStr] = key.split(':');
    const offset = parseInt(offsetStr);
    const row = rows.find(r => r.file === file && r.offset === offset);
    if (row) row.tag = tag;
  }
  modified = {};
  tagChanges = {};

  document.querySelectorAll('.kr-input.modified').forEach(el => {
    el.classList.remove('modified');
    el.classList.add('saved');
    setTimeout(() => el.classList.remove('saved'), 1500);
  });

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

document.getElementById('buildBtn').addEventListener('click', async () => {
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
document.getElementById('filterUntranslated').addEventListener('change', render);
document.getElementById('filterHalfwidth').addEventListener('change', render);
document.getElementById('filterShowIgnore').addEventListener('change', render);
document.getElementById('filterExact').addEventListener('change', render);

document.getElementById('searchBox').addEventListener('input', e => {
  const prev = lastSearch;
  lastSearch = e.target.value;
  render();
  // 검색 해제 시 단일 선택 항목으로 스크롤
  if (prev && !lastSearch && selection.size === 1) {
    const key = [...selection][0];
    const tr = document.querySelector(`#tbody tr[data-key="${CSS.escape(key)}"]`);
    if (tr) tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
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
  const btn = document.getElementById('emulatorBtn');
  btn.disabled = true;
  btn.textContent = '업데이트 중...';
  btn.style.background = '#555';

  try {
    const res = await fetch('/api/emulator-update', { method: 'POST' });
    const result = await res.json();
    showToast(result.message, result.ok ? 'ok' : 'err');
  } catch (e) {
    showToast('오류: ' + e.message, 'err');
  }

  btn.disabled = false;
  btn.textContent = '번들 생성';
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
    const btn = document.getElementById('emulatorBtn');
    btn.disabled = true;
    btn.title = '에뮬레이터 없음';
    btn.style.opacity = '0.35';
    btn.style.cursor = 'default';
  }
});
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
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
        else:
            self.send_error(404)

    def do_POST(self):
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

    def _handle_emulator_update_kitan(self):
        import tempfile, shutil, re
        build_dir    = os.path.join(PROJECT_ROOT, 'build', 'kitan')
        emulator_dir = os.path.join(PROJECT_ROOT, 'emulator')
        rom_dir      = os.path.join(emulator_dir, 'rom')
        bios_dir     = os.path.join(emulator_dir, 'bios')
        data_path    = os.path.join(emulator_dir, 'kitan.data')
        js_path      = os.path.join(emulator_dir, 'kitan.js')

        # 1. build/kitan/ → system/data FDI 패치
        if os.path.isdir(build_dir) and os.listdir(build_dir):
            try:
                from kitan_inserter import patch_fdi
                for fdi_name in ('kitan-system.fdi', 'kitan-data.fdi'):
                    fdi_path = os.path.join(rom_dir, fdi_name)
                    if not os.path.exists(fdi_path):
                        continue
                    with open(fdi_path, 'rb') as f:
                        fdi_data = f.read()
                    result, patched = patch_fdi(fdi_data, build_dir)
                    if patched:
                        with open(fdi_path, 'wb') as f:
                            f.write(result)
            except Exception as e:
                self._send_json_error(f'FDI 패치 실패: {e}', 500)
                return

        # 2. demo 디스크 패치
        try:
            demo_inserter = os.path.join(PROJECT_ROOT, 'tools', 'kitan_demo_inserter.py')
            game_dir = os.path.join(PROJECT_ROOT, 'original', 'kitan', 'data')
            subprocess.run(['python3', demo_inserter, game_dir],
                           capture_output=True, timeout=60, cwd=PROJECT_ROOT)
        except Exception:
            pass  # demo 패치 실패는 무시

        # 3. kitan.data 번들 재생성
        if not os.path.exists(FILE_PACKAGER):
            self._send_json_error(f'file_packager.py 없음: {FILE_PACKAGER}', 500)
            return

        tmpdir = tempfile.mkdtemp(prefix='kitan-bundle-')
        loader_js = os.path.join(tmpdir, 'loader.js')
        try:
            tmp_bios = os.path.join(tmpdir, 'bios')
            tmp_rom  = os.path.join(tmpdir, 'rom')
            os.makedirs(tmp_bios)
            os.makedirs(tmp_rom)
            for f in os.listdir(bios_dir):
                if not f.startswith('.'):
                    shutil.copy2(os.path.join(bios_dir, f), tmp_bios)
            for fdi in ('kitan-system.fdi', 'kitan-data.fdi', 'kitan-demo.fdi'):
                src = os.path.join(rom_dir, fdi)
                if os.path.exists(src):
                    shutil.copy2(src, tmp_rom)

            proc = subprocess.run(
                ['python3', FILE_PACKAGER, data_path,
                 '--js-output=' + loader_js,
                 '--preload', 'bios@/emulator/np2kai',
                 '--preload', 'rom@/rom'],
                capture_output=True, text=True, timeout=120, cwd=tmpdir,
            )
            if proc.returncode != 0:
                self._send_json_error(f'번들 재생성 실패: {proc.stderr.strip()[-300:]}', 500)
                return

            # 4. kitan.js 메타데이터 갱신
            with open(loader_js, 'r') as f:
                loader_content = f.read()
            meta_match = re.search(r'"files":\s*(\[.*?\]),\s*"remote_package_size":\s*(\d+)', loader_content)
            if not meta_match:
                self._send_json_error('메타데이터 추출 실패', 500)
                return
            new_files = meta_match.group(1)
            new_size  = meta_match.group(2)

            with open(js_path, 'r') as f:
                js_content = f.read()
            js_content = re.sub(
                r'loadPackage\(\{(?:"files"|files):\s*\[.*?\],\s*(?:"remote_package_size"|remote_package_size):\s*\d+\}\)',
                f'loadPackage({{"files":{new_files},"remote_package_size":{new_size}}})',
                js_content,
            )
            with open(js_path, 'w') as f:
                f.write(js_content)

        except Exception as e:
            self._send_json_error(f'번들 재생성 실패: {e}', 500)
            return
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        data_size = os.path.getsize(data_path)
        self._send_json({
            'ok': True,
            'message': f'에뮬레이터 업데이트 완료 — 번들 재생성 ({data_size:,} bytes)',
        })

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
        if TITLE == 'kitan':
            self._handle_emulator_update_kitan()
            return

        build_dir = os.path.join(PROJECT_ROOT, 'build', TITLE)
        if not os.path.isdir(build_dir):
            self._send_json_error(f'빌드 결과 없음: {build_dir}', 400)
            return

        build_files = [f for f in os.listdir(build_dir)
                       if os.path.isfile(os.path.join(build_dir, f))
                       and not f.startswith('.')]
        if not build_files:
            self._send_json_error('build/ 디렉토리가 비어 있습니다. 먼저 빌드하세요.', 400)
            return

        emulator_dir = os.path.join(PROJECT_ROOT, 'emulator')
        rom_dir      = os.path.join(emulator_dir, 'rom')
        bios_dir     = os.path.join(emulator_dir, 'bios')
        fdi_path     = os.path.join(rom_dir, 'hukyou_kr.fdi')
        data_path    = os.path.join(emulator_dir, 'hukyou.data')
        js_path      = os.path.join(emulator_dir, 'hukyou.js')

        # 1. FDI 패치
        try:
            from hukyou_inserter import patch_fdi
            patch_fdi(fdi_path, build_dir)
        except Exception as e:
            self._send_json_error(f'FDI 패치 실패: {e}', 500)
            return

        # 2. 임시 디렉토리에 bios + hukyou ROM만 모아서 번들 생성
        if not os.path.exists(FILE_PACKAGER):
            self._send_json_error(f'file_packager.py 없음: {FILE_PACKAGER}', 500)
            return
        import tempfile, shutil, re, json
        tmpdir = tempfile.mkdtemp(prefix='hukyou-bundle-')
        loader_js = os.path.join(tmpdir, 'loader.js')
        try:
            # 임시 번들 디렉토리 구성
            tmp_bios = os.path.join(tmpdir, 'bios')
            tmp_rom  = os.path.join(tmpdir, 'rom')
            os.makedirs(tmp_bios)
            os.makedirs(tmp_rom)
            for f in os.listdir(bios_dir):
                if not f.startswith('.'):
                    shutil.copy2(os.path.join(bios_dir, f), tmp_bios)
            shutil.copy2(fdi_path, tmp_rom)

            # file_packager 실행
            proc = subprocess.run(
                ['python3', FILE_PACKAGER,
                 data_path,
                 '--js-output=' + loader_js,
                 '--preload', 'bios@/emulator/np2kai',
                 '--preload', 'rom@/rom'],
                capture_output=True, text=True, timeout=120,
                cwd=tmpdir,
            )
            if proc.returncode != 0:
                self._send_json_error(f'번들 재생성 실패: {proc.stderr.strip()[-300:]}', 500)
                return

            # 3. loader.js에서 메타데이터 추출 → hukyou.js 교체
            with open(loader_js, 'r') as f:
                loader_content = f.read()
            meta_match = re.search(r'"files":\s*(\[.*?\]),\s*"remote_package_size":\s*(\d+)', loader_content)
            if not meta_match:
                self._send_json_error('메타데이터 추출 실패', 500)
                return
            new_files = meta_match.group(1)
            new_size  = meta_match.group(2)

            with open(js_path, 'r') as f:
                js_content = f.read()
            js_content = re.sub(
                r'loadPackage\(\{files:\[.*?\],remote_package_size:\d+\}\)',
                f'loadPackage({{files:{new_files},remote_package_size:{new_size}}})',
                js_content,
            )
            with open(js_path, 'w') as f:
                f.write(js_content)

        except Exception as e:
            self._send_json_error(f'번들 재생성 실패: {e}', 500)
            return
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        data_size = os.path.getsize(data_path)
        self._send_json({
            'ok': True,
            'message': f'완료 — FDI 패치 ({len(build_files)}개 파일), 번들 재생성 ({data_size:,} bytes)',
        })

    def run_build(self):
        game_dir = os.path.join(PROJECT_ROOT, 'original', TITLE)
        inserter = os.path.join(PROJECT_ROOT, 'tools', f'{TITLE}_inserter.py')
        try:
            proc = subprocess.run(
                ['python3', inserter, game_dir],
                capture_output=True, text=True, timeout=60,
                cwd=PROJECT_ROOT,
            )
            output = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0:
                lines = output.splitlines()
                file_lines = [l for l in lines if '건 교체' in l]
                if file_lines:
                    n_files = len(file_lines)
                    n_items = sum(int(l.split('건 교체')[0].split()[-1]) for l in file_lines)
                    msg = f'빌드 완료 — {n_files}개 파일 {n_items}건 교체'
                else:
                    msg = '빌드 완료 (교체 항목 없음)'
                return {'ok': True, 'message': msg}
            last = output.splitlines()[-1] if output else '빌드 실패'
            return {'ok': False, 'message': f'빌드 실패: {last}'}
        except Exception as e:
            return {'ok': False, 'message': str(e)}


if __name__ == '__main__':
    port = 8182  # JP(81) → KR(82)
    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    print(f'[{TITLE_KR}] 번역 에디터: http://localhost:{port}')
    print('종료: Ctrl+C')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
