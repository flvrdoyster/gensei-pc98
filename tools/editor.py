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
body { font-family: 'Malgun Gothic', sans-serif; background: #f5f5f5; color: #222; padding: 16px; padding-top: 0; font-size: 14px; max-width: 1240px; margin: 0 auto; }
.topbar { position: sticky; top: 0; z-index: 10; background: #f5f5f5; padding: 12px 0 8px; border-bottom: 2px solid #ddd; margin-bottom: 8px; }
h1 { font-size: 16px; font-weight: 600; margin-bottom: 8px; color: #333; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar select, .toolbar input { background: #fff; color: #222; border: 1px solid #ccc; padding: 5px 10px; border-radius: 4px; font-size: 13px; }
.toolbar .stats { margin-left: auto; font-size: 12px; color: #888; }
table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
th { background: #e8e8e8; padding: 7px 8px; text-align: left; border-bottom: 2px solid #ccc; font-weight: 600; color: #444; }
td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; vertical-align: top; overflow: hidden; }
tr:hover { background: #f0f0f0; }
.type { width: 88px; }
.type span { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.type-dialog span { background: #dbeafe; color: #1d4ed8; }
.type-monolog span { background: #e0e7ff; color: #4338ca; }
.type-cutscene span { background: #fce7f3; color: #9d174d; }
.type-item span { background: #dcfce7; color: #15803d; }
.type-menu span { background: #fef9c3; color: #854d0e; }
.type-location span { background: #fed7aa; color: #9a3412; }
.type-battle span { background: #fee2e2; color: #991b1b; }
.type-system span { background: #e5e7eb; color: #374151; }
.type-ignore span { background: #f5f5f5; color: #aaa; text-decoration: line-through; }
.type-char span { background: #cffafe; color: #0e7490; }
.type span.taggable { cursor: pointer; position: relative; }
.type span.taggable:hover { filter: brightness(0.9); }
.gaiji-badge { display: inline-block; padding: 1px 4px; border-radius: 2px; font-size: 10px; font-weight: 600; background: #f3e8ff; color: #7c3aed; margin-left: 4px; vertical-align: middle; }
.file { width: 100px; font-size: 12px; color: #666; }
.off { width: 58px; font-size: 11px; color: #aaa; font-family: monospace; text-align: right; padding-right: 10px; }
.jp { width: 26%; color: #444; white-space: pre-wrap; word-break: break-all; cursor: pointer; }
.jp:hover { background: #f0f4ff; }
.jp.copied { background: #d4edda; transition: background 0.1s; }
.kr-cell { width: 42%; }
.kr-input { width: 100%; background: #fff; color: #222; border: 1px solid #ccc; padding: 4px 7px; border-radius: 3px; font-size: 13px; font-family: inherit; }
.kr-input:focus { border-color: #555; outline: none; }
.kr-input.modified { border-color: #f59e0b; background: #fffbeb; }
.kr-input.saved { border-color: #22c55e; }
.len { width: 70px; font-size: 12px; text-align: center; color: #888; }
.len.over { color: #dc2626; font-weight: bold; }
.len.ok { color: #16a34a; }
.len.empty { color: #bbb; }
.save-btn { background: #333; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.save-btn:hover { background: #111; }
.save-btn:disabled { background: #bbb; cursor: default; }
.build-btn { background: #fff; color: #333; border: 1px solid #ccc; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.build-btn:hover { background: #f0f0f0; }
.toast { position: fixed; bottom: 24px; right: 24px; color: #fff; padding: 10px 18px; border-radius: 6px; font-size: 13px; opacity: 0; pointer-events: none; transition: opacity 0.25s; max-width: 340px; box-shadow: 0 2px 8px rgba(0,0,0,0.25); }
.toast.show { opacity: 1; }
tr.row-selected { background: #dbeafe !important; }
tr.range-start { background: #fef9c3 !important; }
#tbody tr { cursor: pointer; }
#tbody tr td.kr-cell { cursor: default; }
.bulk-bar { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 10px 18px; border-radius: 8px; display: flex; gap: 10px; align-items: center; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,0.35); z-index: 200; white-space: nowrap; }
.bulk-bar select { background: #555; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; font-size: 13px; cursor: pointer; }
.bulk-apply { background: #4ade80; color: #111; border: none; padding: 5px 14px; border-radius: 4px; font-size: 13px; cursor: pointer; font-weight: 600; }
.bulk-apply:hover { background: #22c55e; }
.bulk-cancel { background: #666; color: #fff; border: none; padding: 5px 14px; border-radius: 4px; font-size: 13px; cursor: pointer; }
.bulk-cancel:hover { background: #888; }
</style>
</head>
<body>
<div class="topbar">
<h1>__TITLE_KR__ 번역 에디터</h1>
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
  <label style="font-size:13px;cursor:pointer;user-select:none"><input type="checkbox" id="filterUntranslated" style="vertical-align:middle"> 미번역만</label>
  <label style="font-size:13px;cursor:pointer;user-select:none"><input type="checkbox" id="filterGaiji" style="vertical-align:middle"> 외자만</label>
  <label style="font-size:13px;cursor:pointer;user-select:none"><input type="checkbox" id="filterShowIgnore" style="vertical-align:middle"> 제외 포함</label>
  <input type="text" id="searchBox" placeholder="검색 (JP/KR)..." style="width:200px">
  <button class="save-btn" id="saveBtn" disabled>저장</button>
  <button class="build-btn" id="buildBtn">빌드</button>
  <button class="build-btn" id="emulatorBtn">번들 생성</button>
  <span class="stats" id="stats"><svg id="donut" width="20" height="20" viewBox="0 0 36 36" style="vertical-align:middle;margin-right:4px"><circle cx="18" cy="18" r="14" fill="none" stroke="#e5e7eb" stroke-width="5"/><circle id="donutArc" cx="18" cy="18" r="14" fill="none" stroke="#22c55e" stroke-width="5" stroke-dasharray="0 88" stroke-linecap="round" transform="rotate(-90 18 18)"/></svg><span id="statsText"></span></span>
</div>
</div>
<table>
<thead><tr>
  <th class="type">타입</th>
  <th class="file">파일</th>
  <th class="off">오프셋</th>
  <th class="jp">일본어 (JP)</th>
  <th class="kr-cell">한국어 (KR)</th>
  <th class="len">바이트</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<div class="toast" id="toast"></div>
<div class="bulk-bar" id="bulkBar" style="display:none">
  <span id="bulkCount"></span>
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
          gaiji: false, taggable: true, speaker: speaker,
        });
      }
    }
  } else {
    // hukyou 포맷: dialogs / items / ui 구조
    for (const dialog of data.dialogs) {
      for (const line of dialog.lines) {
        rows.push({
          type: 'dialog', tag: line.tag || null, file: dialog.file, index: dialog.index,
          offset: line.offset, localOffset: line.offset, jp: line.jp, kr: line.kr, gaiji: !!line.gaiji,
        });
      }
    }
    for (const item of (data.items || [])) {
      const n = item.name;
      rows.push({ type: 'item', tag: n.tag || 'item', file: 'MESSAGE.CMD', offset: n.offset, localOffset: n.offset, jp: n.jp, kr: n.kr, jp_len: n.jp_len, gaiji: !!n.gaiji });
      if (item.stat) {
        const s = item.stat;
        rows.push({ type: 'item', tag: s.tag || 'item', file: 'MESSAGE.CMD', offset: s.offset, localOffset: s.offset, jp: s.jp, kr: s.kr, jp_len: s.jp_len, gaiji: !!s.gaiji });
      }
      for (const desc of item.desc) {
        rows.push({ type: 'item', tag: desc.tag || 'item', file: 'MESSAGE.CMD', offset: desc.offset, localOffset: desc.offset, jp: desc.jp, kr: desc.kr, jp_len: desc.jp_len, gaiji: !!desc.gaiji });
      }
    }
    const UI_CAT_TAG = { system: 'system', status: 'menu', names: 'menu', battle: 'battle' };
    for (const entry of (data.ui || [])) {
      const defaultTag = UI_CAT_TAG[entry.category] || 'menu';
      const tag = entry.tag || defaultTag;  // JSON에 저장된 tag 우선, 없으면 category 기본값
      rows.push({ type: 'ui', tag: tag, file: 'GF2.COM', category: entry.category, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, gaiji: true });
    }
    // gsovl (kitan GS.OVL 고정 오프셋 문자열)
    const GSOVL_CAT_TAG = { battle: 'battle', status: 'system', name: 'char', stat: 'system', misc: 'menu' };
    for (const entry of (data.gsovl || [])) {
      const tag = GSOVL_CAT_TAG[entry.tag] ?? entry.tag ?? 'system';
      rows.push({ type: 'gsovl', tag, file: 'GS.OVL', category: entry.tag, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, gaiji: false });
    }
    // demo (kitan demo SP1.COM 텍스트)
    const DEMO_CAT_TAG = { intro: 'dialog', title: 'system', error: 'system' };
    for (const entry of (data.demo || [])) {
      const tag = DEMO_CAT_TAG[entry.tag] ?? entry.tag ?? 'dialog';
      rows.push({ type: 'demo', tag, file: 'SP1.COM', category: entry.tag, offset: entry.offset, localOffset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, gaiji: false });
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

function encodeByteLen(text, useGaiji) {
  let len = 0;
  for (const ch of text) {
    if (charmap[ch]) { len += 2; }
    else if (useGaiji) { len += 2; }
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
  const untranslatedOnly = document.getElementById('filterUntranslated').checked;
  const gaijiOnly = document.getElementById('filterGaiji').checked;
  const showIgnore = document.getElementById('filterShowIgnore').checked;

  filteredRows = rows.filter(r => {
    if (!showIgnore && (r.tag || r.type) === 'ignore') return false;
    if (untranslatedOnly) {
      if ((r.kr || '').trim() || (r.tag || r.type) === 'ignore') return false;
    }
    if (gaijiOnly && !r.gaiji) return false;
    if (filterType) {
      const effective = r.tag || r.type;
      if (effective !== filterType) return false;
    }
    if (filterFile && r.file !== filterFile) return false;
    if (search && !r.jp.toLowerCase().includes(search) && !(r.kr || '').toLowerCase().includes(search)) return false;
    return true;
  });

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';

  for (const r of filteredRows) {
    const tr = document.createElement('tr');
    const key = rowKey(r);
    const idx = filteredRows.indexOf(r);
    tr.dataset.key = key;
    if (selection.has(key)) tr.classList.add('row-selected');
    if (rangeStart !== null && idx === rangeStart) tr.classList.add('range-start');
    const kr = key in modified ? modified[key] : (r.kr || '');
    const isGaiji = r.gaiji || r.file === 'GF2.COM';
    const jpLen = getJpLen(r);
    const krLen = kr ? encodeByteLen(kr, isGaiji) : 0;

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
      <td class="jp" title="클릭하여 복사" onclick="navigator.clipboard.writeText(this.dataset.jp);this.classList.add('copied');setTimeout(()=>this.classList.remove('copied'),600)" data-jp="${escAttr(r.jp)}">${speakerHtml}${escHtml(r.jp)}${r.gaiji ? '<span class="gaiji-badge">외</span>' : ''}</td>
      <td class="kr-cell"><input class="kr-input${key in modified ? ' modified' : ''}" data-key="${key}" value="${escAttr(kr)}" placeholder="번역 입력..."></td>
      <td class="len ${lenClass}">${lenText}</td>
    `;
    tbody.appendChild(tr);
  }

  updateStats();
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
  document.getElementById('statsText').textContent = `${pct}% (${done}/${total}) | 수정: ${mod}건` + (tags ? ` | 분류: ${tags}건` : '');
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
  }
  selection.clear();
  rangeStart = null;
  updateBulkBar();
  updateStats();
  render();
});

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

  const isGaiji = row.gaiji || row.type === 'ui';
  const jpLen = getJpLen(row);
  const krLen = val ? encodeByteLen(val, isGaiji) : 0;
  const lenTd = e.target.closest('tr').querySelector('.len');
  if (val) {
    lenTd.textContent = `${krLen}/${jpLen}`;
    lenTd.className = 'len ' + (krLen <= jpLen ? 'ok' : 'over');
  } else {
    lenTd.textContent = `${jpLen}`;
    lenTd.className = 'len empty';
  }

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

document.getElementById('filterType').addEventListener('change', render);
document.getElementById('filterFile').addEventListener('change', render);
document.getElementById('filterUntranslated').addEventListener('change', render);
document.getElementById('filterGaiji').addEventListener('change', render);
document.getElementById('filterShowIgnore').addEventListener('change', render);
document.getElementById('searchBox').addEventListener('input', render);

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    const btn = document.getElementById('saveBtn');
    if (!btn.disabled) btn.click();
  }
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
