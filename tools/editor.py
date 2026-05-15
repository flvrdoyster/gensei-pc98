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
<h1>환세풍광전 번역 에디터</h1>
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
    <option value="ignore">제외</option>
    <option value="gaiji">외자(가이지)</option>
    <option value="_untranslated">미번역</option>
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
    const tag = UI_CAT_TAG[entry.category] || 'menu';
    rows.push({ type: 'ui', tag: tag, file: 'GF2.COM', category: entry.category, offset: entry.offset, jp: entry.jp, kr: entry.kr, jp_len: entry.jp_len, gaiji: true });
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

const TAG_LABELS = { dialog: '대사', monolog: '독백', cutscene: '컷씬', char: '캐릭터', battle: '전투', item: '아이템', item_name: '아이템명', item_stat: '수치', item_desc: '설명', menu: '메뉴', location: '장소', system: '시스템', ignore: '제외' };
const DIALOG_TAGS = ['dialog', 'monolog', 'cutscene', 'char', 'battle', 'item', 'menu', 'location', 'system', 'ignore'];

function typeLabel(r) {
  const effective = r.tag || r.type;
  const label = TAG_LABELS[effective] || effective;
  const TYPE_CSS = { dialog: 'type-dialog', monolog: 'type-monolog', cutscene: 'type-cutscene', char: 'type-char', battle: 'type-battle', item: 'type-item', item_name: 'type-item', item_stat: 'type-item', item_desc: 'type-item', menu: 'type-menu', location: 'type-location', system: 'type-system', ignore: 'type-ignore' };
  const cls = TYPE_CSS[effective] || 'type-dialog';
  const taggable = (r.type === 'dialog' || r.type === 'ui') ? ' taggable' : '';
  return `<div class="${cls}"><span class="${taggable}" data-file="${r.file || ''}" data-offset="${r.offset}">${label}</span></div>`;
}

function render() {
  const filterType = document.getElementById('filterType').value;
  const filterFile = document.getElementById('filterFile').value;
  const search = document.getElementById('searchBox').value.toLowerCase();

  const filtered = rows.filter(r => {
    if (filterType) {
      if (filterType === '_untranslated') {
        if ((r.kr || '').trim() || (r.tag || r.type) === 'ignore') return false;
      } else if (filterType === 'gaiji') {
        if (!r.gaiji) return false;
      } else {
        const effective = r.tag || r.type;
        if (filterType === 'item') {
          if (!r.type.startsWith('item') && effective !== 'item') return false;
        } else {
          if (effective !== filterType) return false;
        }
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

    tr.innerHTML = `
      <td class="type">${typeLabel(r)}</td>
      <td class="file">${r.file}</td>
      <td class="jp" title="클릭하여 복사" onclick="navigator.clipboard.writeText(this.dataset.jp);this.classList.add('copied');setTimeout(()=>this.classList.remove('copied'),600)" data-jp="${escAttr(r.jp)}">${escHtml(r.jp)}${r.gaiji ? '<span class="gaiji-badge">외</span>' : ''}</td>
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
  const tags = Object.keys(tagChanges).length;
  const changes = mod + tags;
  document.getElementById('stats').textContent = `번역: ${done}/${total} | 수정: ${mod}건` + (tags ? ` | 분류: ${tags}건` : '');
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

  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ translations: modified, tags: tagChanges }),
  });
  const result = await res.json();

  for (const [key, val] of Object.entries(modified)) {
    const row = rows.find(r => r.type + ':' + r.file + ':' + r.offset === key);
    if (row) row.kr = val;
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
  showToast(`${result.updated}건 저장됨`, 'ok');
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
  const row = rows.find(r => r.offset === offset && r.file === file && r.type === 'dialog');
  if (!row) return;
  const current = row.tag || 'dialog';
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

    def apply_changes(self, body):
        with open(TRANS_PATH, encoding='utf-8') as f:
            data = json.load(f)

        translations = body.get('translations', {})
        tags = body.get('tags', {})

        updated = 0
        for key, kr in translations.items():
            parts = key.split(':', 2)
            typ, file_name, offset_str = parts[0], parts[1], parts[2]
            offset = int(offset_str)

            if typ == 'dialog':
                for dialog in data['dialogs']:
                    if dialog['file'] != file_name:
                        continue
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
    print(f'번역 에디터: http://localhost:{port}')
    print('종료: Ctrl+C')
    server.serve_forever()
