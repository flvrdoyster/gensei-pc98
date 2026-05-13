"""
번역 웹 에디터
==============

사용법:
  python3 tools/editor.py
  브라우저에서 http://localhost:8421 접속

translation.json의 kr 필드를 브라우저에서 편집, 저장.
"""

import http.server
import json
import os
import subprocess
import urllib.parse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANS_PATH = os.path.join(PROJECT_ROOT, 'translation', 'hukyou', 'translation.json')
CHARMAP_PATH = os.path.join(PROJECT_ROOT, 'tools', 'charmap.json')

HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>환세풍광전 번역 에디터</title>
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
.type-item span { background: #dcfce7; color: #15803d; }
.type-ui span { background: #fef9c3; color: #854d0e; }
.file { width: 120px; font-size: 12px; color: #666; }
.jp { width: 26%; color: #444; white-space: pre-wrap; word-break: break-all; }
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
.toast { position: fixed; bottom: 20px; right: 20px; background: #222; color: #fff; padding: 10px 18px; border-radius: 4px; display: none; font-size: 13px; }
</style>
</head>
<body>
<div class="topbar">
<h1>환세풍광전 번역 에디터</h1>
<div class="toolbar">
  <select id="filterType">
    <option value="">전체 타입</option>
    <option value="dialog">대화</option>
    <option value="item">아이템</option>
    <option value="ui">UI</option>
  </select>
  <select id="filterFile">
    <option value="">전체 파일</option>
  </select>
  <input type="text" id="searchBox" placeholder="검색 (JP/KR)..." style="width:200px">
  <button class="save-btn" id="saveBtn" disabled>저장</button>
  <button class="build-btn" id="buildBtn">빌드</button>
  <span class="stats" id="stats"></span>
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
<div class="toast" id="toast">저장 완료</div>

<script>
let rows = [];
let modified = {};
let charmap = {};

async function load() {
  const [transRes, charmapRes] = await Promise.all([
    fetch('/api/translation'),
    fetch('/api/charmap'),
  ]);
  const data = await transRes.json();
  charmap = await charmapRes.json();
  rows = [];

  for (const dialog of data.dialogs) {
    for (const line of dialog.lines) {
      rows.push({
        type: 'dialog', file: dialog.file, index: dialog.index,
        offset: line.offset, jp: line.jp, kr: line.kr,
      });
    }
  }
  for (const item of (data.items || [])) {
    rows.push({ type: 'item_name', file: 'MESSAGE.CMD', offset: item.name.offset, jp: item.name.jp, kr: item.name.kr });
    if (item.stat) {
      rows.push({ type: 'item_stat', file: 'MESSAGE.CMD', offset: item.stat.offset, jp: item.stat.jp, kr: item.stat.kr });
    }
    for (const desc of item.desc) {
      rows.push({ type: 'item_desc', file: 'MESSAGE.CMD', offset: desc.offset, jp: desc.jp, kr: desc.kr });
    }
  }
  for (const entry of (data.ui || [])) {
    rows.push({ type: 'ui', file: 'GF2.COM', category: entry.category, offset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len });
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

const ASCII_FULLWIDTH = new Set([' ', '.', ',', '!', '?', '(', ')']);

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

function typeLabel(t) {
  const labels = { dialog: '대화', item_name: '아이템명', item_stat: '수치', item_desc: '설명', ui: 'UI' };
  const cls = t.startsWith('item') ? 'type-item' : t === 'ui' ? 'type-ui' : 'type-dialog';
  return `<div class="${cls}"><span>${labels[t] || t}</span></div>`;
}

function render() {
  const filterType = document.getElementById('filterType').value;
  const filterFile = document.getElementById('filterFile').value;
  const search = document.getElementById('searchBox').value.toLowerCase();

  const filtered = rows.filter(r => {
    if (filterType) {
      if (filterType === 'item' && !r.type.startsWith('item')) return false;
      if (filterType !== 'item' && r.type !== filterType && !(filterType === 'item' && r.type.startsWith('item'))) return false;
    }
    if (filterFile && r.file !== filterFile) return false;
    if (search && !r.jp.toLowerCase().includes(search) && !(r.kr || '').toLowerCase().includes(search)) return false;
    return true;
  });

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';

  for (const r of filtered) {
    const tr = document.createElement('tr');
    const key = r.type + ':' + r.offset;
    const kr = key in modified ? modified[key] : (r.kr || '');
    const isGaiji = r.type === 'ui';
    const jpLen = getJpLen(r);
    const krLen = kr ? encodeByteLen(kr, isGaiji) : 0;

    let lenClass = 'empty';
    let lenText = `${jpLen}`;
    if (kr) {
      lenText = `${krLen}/${jpLen}`;
      lenClass = krLen <= jpLen ? 'ok' : 'over';
    }

    tr.innerHTML = `
      <td class="type">${typeLabel(r.type)}</td>
      <td class="file">${r.file}</td>
      <td class="jp">${escHtml(r.jp)}</td>
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
  const done = rows.filter(r => (r.kr || '') || (modified[r.type+':'+r.offset] || '')).length;
  const mod = Object.keys(modified).length;
  document.getElementById('stats').textContent = `번역: ${done}/${total} | 수정: ${mod}건`;
  document.getElementById('saveBtn').disabled = mod === 0;
}

document.getElementById('tbody').addEventListener('input', e => {
  if (!e.target.classList.contains('kr-input')) return;
  const key = e.target.dataset.key;
  const row = rows.find(r => r.type + ':' + r.offset === key);
  const val = e.target.value;

  if (val === (row.kr || '')) {
    delete modified[key];
    e.target.classList.remove('modified');
  } else {
    modified[key] = val;
    e.target.classList.add('modified');
  }

  const isGaiji = row.type === 'ui';
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

  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(modified),
  });
  const result = await res.json();

  for (const [key, val] of Object.entries(modified)) {
    const row = rows.find(r => r.type + ':' + r.offset === key);
    if (row) row.kr = val;
  }
  modified = {};

  document.querySelectorAll('.kr-input.modified').forEach(el => {
    el.classList.remove('modified');
    el.classList.add('saved');
    setTimeout(() => el.classList.remove('saved'), 1500);
  });

  btn.textContent = '저장';
  updateStats();

  const toast = document.getElementById('toast');
  toast.textContent = `${result.updated}건 저장 완료`;
  toast.style.display = 'block';
  setTimeout(() => toast.style.display = 'none', 2000);
});

document.getElementById('buildBtn').addEventListener('click', async () => {
  const btn = document.getElementById('buildBtn');
  btn.disabled = true;
  btn.textContent = '빌드 중...';
  btn.style.background = '#555';

  try {
    const res = await fetch('/api/build', { method: 'POST' });
    const result = await res.json();
    const toast = document.getElementById('toast');
    if (result.ok) {
      toast.style.background = '#45e980';
      toast.textContent = result.message;
    } else {
      toast.style.background = '#e94560';
      toast.textContent = result.message;
    }
    toast.style.display = 'block';
    setTimeout(() => toast.style.display = 'none', 4000);
  } catch (e) {
    alert('빌드 실패: ' + e.message);
  }

  btn.disabled = false;
  btn.textContent = '빌드';
  btn.style.background = '';
});

document.getElementById('filterType').addEventListener('change', render);
document.getElementById('filterFile').addEventListener('change', render);
document.getElementById('searchBox').addEventListener('input', render);

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    const btn = document.getElementById('saveBtn');
    if (!btn.disabled) btn.click();
  }
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
            self.wfile.write(HTML.encode())
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
            updated = self.apply_changes(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'updated': updated}).encode())
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

    def apply_changes(self, changes):
        with open(TRANS_PATH, encoding='utf-8') as f:
            data = json.load(f)

        updated = 0
        for key, kr in changes.items():
            typ, offset_str = key.split(':', 1)
            offset = int(offset_str)

            if typ == 'dialog':
                for dialog in data['dialogs']:
                    for line in dialog['lines']:
                        if line['offset'] == offset:
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

        with open(TRANS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return updated

    def run_build(self):
        game_dir = os.path.join(PROJECT_ROOT, 'original', 'hukyou')
        inserter = os.path.join(PROJECT_ROOT, 'tools', 'hukyou_inserter.py')
        try:
            proc = subprocess.run(
                ['python3', inserter, game_dir],
                capture_output=True, text=True, timeout=60,
                cwd=PROJECT_ROOT,
            )
            output = (proc.stdout + proc.stderr).strip()
            if proc.returncode == 0:
                return {'ok': True, 'message': output or '빌드 완료'}
            return {'ok': False, 'message': output or '빌드 실패'}
        except Exception as e:
            return {'ok': False, 'message': str(e)}


if __name__ == '__main__':
    port = 8421
    server = http.server.HTTPServer(('127.0.0.1', port), Handler)
    print(f'번역 에디터: http://localhost:{port}')
    print('종료: Ctrl+C')
    server.serve_forever()
