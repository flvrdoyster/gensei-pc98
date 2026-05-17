"""
번역 웹 에디터
==============

사용법:
  python3 tools/editor.py <title>
  브라우저에서 http://localhost:8421 접속

  <title>: hukyou | kaitou | torimono | kitan (기본값: hukyou)

translation.json의 kr 필드를 브라우저에서 편집, 저장.
"""

import http.server
import json
import os
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
td.type { overflow: visible; position: relative; }
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
.tag-menu { position: absolute; left: 0; bottom: calc(100% + 2px); background: #fff; border: 1px solid #ccc; border-radius: 4px; box-shadow: 0 -2px 8px rgba(0,0,0,0.15); z-index: 100; min-width: 80px; padding: 2px 0; }
.tag-menu div { padding: 4px 10px; font-size: 12px; cursor: pointer; font-weight: 400; color: #333; }
.tag-menu div:hover { background: #f0f0f0; }
.tag-menu div.active { font-weight: 600; }
.file { width: 120px; font-size: 12px; color: #666; }
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
  <span class="stats" id="stats"><svg id="donut" width="20" height="20" viewBox="0 0 36 36" style="vertical-align:middle;margin-right:4px"><circle cx="18" cy="18" r="14" fill="none" stroke="#e5e7eb" stroke-width="5"/><circle id="donutArc" cx="18" cy="18" r="14" fill="none" stroke="#22c55e" stroke-width="5" stroke-dasharray="0 88" stroke-linecap="round" transform="rotate(-90 18 18)"/></svg><span id="statsText"></span></span>
</div>
</div>
<table>
<thead><tr>
  <th class="type">타입</th>
  <th class="file">파일</th>
  <th class="jp">일본어 (JP)</th>
  <th class="kr-cell">한국어 (KR)</th>
  <th class="len">바이트</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<div class="toast" id="toast"></div>

<script>
let rows = [];
let modified = {};
let tagChanges = {};
let charmap = {};

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
    for (const entry of data.entries) {
      const base = entry.chunk * 200000;
      if (entry.type === 'skill') {
        for (const seg of (entry.segments || [])) {
          const segType = seg.type === 'name' ? 'skill_name' : seg.type === 'stat' ? 'skill_stat' : 'skill_desc';
          rows.push({
            type: segType, tag: seg.tag || null, file: 'DISK_B.DAT',
            chunk: entry.chunk, offset: base + seg.offset,
            jp: seg.jp, kr: seg.kr, jp_len: seg.jp_len, gaiji: false, taggable: true,
          });
        }
      } else if (entry.type === 'dialog') {
        const speaker = entry.speaker || '';
        for (const line of (entry.lines || [])) {
          rows.push({
            type: 'dialog', tag: line.tag || null, file: 'DISK_B.DAT',
            chunk: entry.chunk, offset: base + line.offset,
            jp: line.jp, kr: line.kr, jp_len: line.jp_len,
            gaiji: false, taggable: true, speaker: speaker,
          });
        }
      } else if (entry.type === 'title') {
        for (const line of (entry.lines || [])) {
          rows.push({
            type: 'title', tag: line.tag || null, file: 'DISK_B.DAT',
            chunk: entry.chunk, offset: base + line.offset,
            jp: line.jp, kr: line.kr, jp_len: line.jp_len,
            gaiji: false, taggable: true,
          });
        }
      } else { // unknown
        for (const line of (entry.lines || [])) {
          rows.push({
            type: 'unknown', tag: line.tag || null, file: 'DISK_B.DAT',
            chunk: entry.chunk, offset: base + line.offset,
            jp: line.jp, kr: line.kr, jp_len: line.jp_len,
            gaiji: false, taggable: true,
          });
        }
      }
    }
  } else {
    // hukyou 포맷: dialogs / items / ui 구조
    for (const dialog of data.dialogs) {
      for (const line of dialog.lines) {
        rows.push({
          type: 'dialog', tag: line.tag || null, file: dialog.file, index: dialog.index,
          offset: line.offset, jp: line.jp, kr: line.kr, gaiji: !!line.gaiji,
        });
      }
    }
    for (const item of (data.items || [])) {
      rows.push({ type: 'item_name', file: 'MESSAGE.CMD', offset: item.name.offset, jp: item.name.jp, kr: item.name.kr, gaiji: !!item.name.gaiji });
      if (item.stat) {
        rows.push({ type: 'item_stat', file: 'MESSAGE.CMD', offset: item.stat.offset, jp: item.stat.jp, kr: item.stat.kr, gaiji: !!item.stat.gaiji });
      }
      for (const desc of item.desc) {
        rows.push({ type: 'item_desc', file: 'MESSAGE.CMD', offset: desc.offset, jp: desc.jp, kr: desc.kr, gaiji: !!desc.gaiji });
      }
    }
    const UI_CAT_TAG = { system: 'system', status: 'menu', names: 'menu', battle: 'battle' };
    for (const entry of (data.ui || [])) {
      const defaultTag = UI_CAT_TAG[entry.category] || 'menu';
      const tag = entry.tag || defaultTag;  // JSON에 저장된 tag 우선, 없으면 category 기본값
      rows.push({ type: 'ui', tag: tag, file: 'GF2.COM', category: entry.category, offset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, gaiji: true });
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

const TAG_LABELS = { dialog: '대사', monolog: '독백', cutscene: '컷씬', char: '캐릭터', battle: '전투', item: '아이템', item_name: '아이템명', item_stat: '수치', item_desc: '설명', menu: '메뉴', location: '장소', system: '시스템', ignore: '제외',
  skill_name: '스킬명', skill_stat: '스탯', skill_desc: '스킬설명', title: '제목', unknown: '기타' };
const DIALOG_TAGS = ['dialog', 'monolog', 'cutscene', 'char', 'battle', 'item', 'menu', 'location', 'system', 'ignore'];

function typeLabel(r) {
  const effective = r.tag || r.type;
  const label = TAG_LABELS[effective] || effective;
  const TYPE_CSS = { dialog: 'type-dialog', monolog: 'type-monolog', cutscene: 'type-cutscene', char: 'type-char', battle: 'type-battle', item: 'type-item', item_name: 'type-item', item_stat: 'type-item', item_desc: 'type-item', menu: 'type-menu', location: 'type-location', system: 'type-system', ignore: 'type-ignore',
    skill_name: 'type-item', skill_stat: 'type-item', skill_desc: 'type-item', title: 'type-menu', unknown: 'type-system' };
  const cls = TYPE_CSS[effective] || 'type-dialog';
  const taggable = (r.type === 'dialog' || r.type === 'ui' || r.taggable) ? ' taggable' : '';
  return `<div class="${cls}"><span class="${taggable}" data-file="${r.file || ''}" data-offset="${r.offset}">${label}</span></div>`;
}

function render() {
  const filterType = document.getElementById('filterType').value;
  const filterFile = document.getElementById('filterFile').value;
  const search = document.getElementById('searchBox').value.toLowerCase();
  const untranslatedOnly = document.getElementById('filterUntranslated').checked;
  const gaijiOnly = document.getElementById('filterGaiji').checked;
  const showIgnore = document.getElementById('filterShowIgnore').checked;

  const filtered = rows.filter(r => {
    if (!showIgnore && (r.tag || r.type) === 'ignore') return false;
    if (untranslatedOnly) {
      if ((r.kr || '').trim() || (r.tag || r.type) === 'ignore') return false;
    }
    if (gaijiOnly && !r.gaiji) return false;
    if (filterType) {
      const effective = r.tag || r.type;
      if (filterType === 'item') {
        if (!r.type.startsWith('item') && !r.type.startsWith('skill') && effective !== 'item') return false;
      } else {
        if (effective !== filterType) return false;
      }
    }
    if (filterFile && r.file !== filterFile) return false;
    if (search && !r.jp.toLowerCase().includes(search) && !(r.kr || '').toLowerCase().includes(search)) return false;
    return true;
  });

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';

  for (const r of filtered) {
    const tr = document.createElement('tr');
    const key = r.type + ':' + r.file + ':' + r.offset;
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
  document.querySelectorAll('.tag-menu').forEach(m => m.remove());
  const offset = parseInt(span.dataset.offset);
  const file = span.dataset.file;
  const row = rows.find(r => r.offset === offset && r.file === file && (r.type === 'dialog' || r.type === 'ui' || r.taggable));
  if (!row) return;
  const current = row.tag || (row.type.startsWith('skill') ? 'item' : row.type === 'title' ? 'menu' : row.type === 'unknown' ? 'system' : 'dialog');
  const menu = document.createElement('div');
  menu.className = 'tag-menu';
  for (const tag of DIALOG_TAGS) {
    const div = document.createElement('div');
    div.textContent = TAG_LABELS[tag];
    if (tag === current) div.className = 'active';
    div.addEventListener('click', () => {
      row.tag = tag;
      tagChanges[file + ':' + offset] = tag;
      menu.remove();
      render();
      updateStats();
    });
    menu.appendChild(div);
  }
  span.style.position = 'relative';
  span.appendChild(menu);
  setTimeout(() => {
    const close = (ev) => { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('click', close); } };
    document.addEventListener('click', close);
  }, 0);
});

load();
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
            self.wfile.write(HTML.replace('__TITLE_KR__', TITLE_KR).encode())
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
                """전역 오프셋으로 entry + segment/line 반환."""
                chunk_idx = global_offset // CHUNK_BASE
                local_off = global_offset % CHUNK_BASE
                for entry in entries:
                    if entry.get('chunk') != chunk_idx:
                        continue
                    if typ in ('skill_name', 'skill_stat', 'skill_desc'):
                        seg_type_map = {'skill_name': 'name', 'skill_stat': 'stat', 'skill_desc': 'desc'}
                        want = seg_type_map[typ]
                        for seg in entry.get('segments', []):
                            if seg.get('offset') == local_off and seg.get('type') == want:
                                return seg
                    elif typ in ('dialog', 'title', 'unknown'):
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
                    for container in (entry.get('segments') or entry.get('lines') or []):
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
                elif typ == 'item_name':
                    for item in data.get('items', []):
                        if item['name']['offset'] == offset:
                            item['name']['kr'] = kr
                            updated += 1
                elif typ == 'item_stat':
                    for item in data.get('items', []):
                        if 'stat' in item and item['stat']['offset'] == offset:
                            item['stat']['kr'] = kr
                            updated += 1
                elif typ == 'item_desc':
                    for item in data.get('items', []):
                        for desc in item['desc']:
                            if desc['offset'] == offset:
                                desc['kr'] = kr
                                updated += 1
                elif typ == 'ui':
                    for entry in data.get('ui', []):
                        if entry['offset'] == offset:
                            entry['kr'] = kr
                            updated += 1

            for key, tag in tags.items():
                file_name, offset_str = key.split(':', 1)
                offset = int(offset_str)
                if file_name == 'GF2.COM':
                    for entry in data.get('ui', []):
                        if entry['offset'] == offset:
                            entry['tag'] = tag
                            updated += 1
                else:
                    for dialog in data['dialogs']:
                        if dialog['file'] != file_name:
                            continue
                        for line in dialog['lines']:
                            if line['offset'] == offset:
                                line['tag'] = tag
                                updated += 1

        with open(TRANS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {'updated': updated, 'skipped': skipped}

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
    port = 8421
    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    print(f'[{TITLE_KR}] 번역 에디터: http://localhost:{port}')
    print('종료: Ctrl+C')
    server.serve_forever()
