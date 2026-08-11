(function () {
  'use strict';

  // ?debug 가 있을 때만 동작. 평소엔 토글 버튼도 패널도 안 만든다.
  if (!new URLSearchParams(location.search).has('debug')) return;

  // 게임 페이지가 디스크를 읽고 쓰는 IDB (gensei-saves/disks). 키 = 디스크 파일명.
  var IDB_NAME  = 'gensei-saves';
  var IDB_STORE = 'disks';

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = function (e) { e.target.result.createObjectStore(IDB_STORE); };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror   = function () { reject(req.error); };
    });
  }

  function idbGet(db, key) {
    return new Promise(function (resolve, reject) {
      var req = db.transaction(IDB_STORE).objectStore(IDB_STORE).get(key);
      req.onsuccess = function () { resolve(req.result); };
      req.onerror   = function () { reject(req.error); };
    });
  }

  function idbPut(db, key, value) {
    return new Promise(function (resolve, reject) {
      var tx  = db.transaction(IDB_STORE, 'readwrite');
      var req = tx.objectStore(IDB_STORE).put(value, key);
      req.onsuccess = function () { resolve(); };
      req.onerror   = function () { reject(req.error); };
    });
  }

  function idbDelete(db, key) {
    return new Promise(function (resolve, reject) {
      var tx  = db.transaction(IDB_STORE, 'readwrite');
      var req = tx.objectStore(IDB_STORE).delete(key);
      req.onsuccess = function () { resolve(); };
      req.onerror   = function () { reject(req.error); };
    });
  }

  // 이 페이지가 실제로 다루는 디스크 키만 대상으로 삼는다 — IDB store는 전 타이틀
  // 공유라서 스코프를 안 좁히면 다른 타이틀에서 넣어둔 캐시까지 같이 나열/내보내기/
  // 삭제 대상이 되어버린다(실사고: 쾌도전 페이지에서 내보내기 눌렀는데 예전에
  // 캐시해둔 포물장 이미지가 같이 나옴). 페이지의 IDB_KEY(단일) 또는 DISKS(다중,
  // 희담류)를 읽어 현재 페이지 소유 키 목록만 구성.
  function pageKeys() {
    if (typeof DISKS !== 'undefined' && Array.isArray(DISKS)) {
      return DISKS.map(function (p) { return p.split('/').pop(); });
    }
    if (typeof IDB_KEY !== 'undefined') {
      return [IDB_KEY];
    }
    return [];
  }

  var STYLE =
    '#debug-panel{position:fixed;top:56px;left:8px;z-index:300;' +
    'background:rgba(38,38,38,0.97);border:1px solid rgba(68,68,68,1);border-radius:6px;' +
    'padding:12px 14px;max-width:min(360px,calc(100vw - 16px));' +
    'color:rgba(204,204,204,1);font-size:var(--font-sm);' +
    'box-shadow:0 6px 20px rgba(0,0,0,0.45);' +
    '-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}' +
    '#debug-panel.hidden{display:none}' +
    '#debug-panel h4{margin:0 0 8px;font-size:var(--font-md);color:rgba(170,170,170,1)}' +
    '#debug-panel .dbg-row{display:flex;align-items:center;gap:6px;margin:4px 0;flex-wrap:wrap}' +
    '#debug-panel .dbg-key{flex:1;min-width:120px;word-break:break-all}' +
    '#debug-panel .dbg-key.dbg-empty{color:rgba(119,119,119,1)}' +
    '#debug-panel button{font-size:var(--font-sm);padding:3px 10px}' +
    '#debug-panel button:disabled{opacity:0.4;cursor:default}' +
    '#debug-panel .dbg-msg{margin-top:8px;color:rgba(119,119,119,1);min-height:1.4em;word-break:break-all}';

  var db = null;
  var panel, listEl, msgEl, fileInput, btnToggle;
  var pendingKey = null;

  function setMsg(text) { if (msgEl) msgEl.textContent = text || ''; }

  function download(key, buf) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([buf], { type: 'application/octet-stream' }));
    a.download = key;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function makeBtn(label, onclick, title) {
    var b = document.createElement('button');
    b.textContent = label;
    if (title) b.title = title;
    b.onclick = onclick;
    return b;
  }

  function refreshKeys() {
    var keys = pageKeys();
    listEl.innerHTML = '';
    if (!keys.length) {
      var none = document.createElement('div');
      none.className = 'dbg-key';
      none.textContent = '이 페이지의 디스크 키를 확인할 수 없음';
      listEl.appendChild(none);
      return;
    }
    keys.forEach(function (key) {
      idbGet(db, key).then(function (buf) {
        var row = document.createElement('div');
        row.className = 'dbg-row';
        var label = document.createElement('span');
        label.className = 'dbg-key' + (buf ? '' : ' dbg-empty');
        label.textContent = key + (buf ? '' : ' (캐시 없음)');
        row.appendChild(label);
        row.appendChild(makeBtn('가져오기', function () { pickFile(key); }, '파일 선택 → 이 키로 저장(덮어쓰기)'));
        var exp = makeBtn('내보내기', function () {
          idbGet(db, key).then(function (b) {
            if (!b) { setMsg(key + ': 캐시 없음'); return; }
            download(key, b);
            setMsg(key + ' 내보냄');
          });
        });
        var del = makeBtn('삭제', function () {
          idbDelete(db, key).then(function () {
            setMsg(key + ' 삭제됨 — 새로고침하면 원본으로');
            refreshKeys();
          });
        }, '캐시에서 제거(원본 복귀)');
        exp.disabled = del.disabled = !buf;
        row.appendChild(exp);
        row.appendChild(del);
        listEl.appendChild(row);
      });
    });
  }

  function pickFile(key) {
    pendingKey = key;
    fileInput.click();
  }

  function onFile(e) {
    var file = e.target.files[0];
    fileInput.value = '';
    if (!file || !pendingKey) return;
    var key = pendingKey;
    file.arrayBuffer().then(function (buf) {
      return idbPut(db, key, buf);
    }).then(function () {
      setMsg('"' + key + '" 저장 (' + (file.size / 1048576).toFixed(2) + ' MB) — 새로고침하세요');
      refreshKeys();
    }).catch(function (err) {
      setMsg('실패: ' + err);
    });
  }

  function build() {
    var topbar = document.querySelector('.top-bar');
    if (!topbar) return;

    var style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);

    // 토글 버튼 — 기존 .btn-icon 그대로, 상단바 왼쪽(grid col1)
    btnToggle = document.createElement('button');
    btnToggle.className = 'btn-icon';
    btnToggle.id = 'btn-debug';
    btnToggle.title = 'DEBUG 디스크';
    // 아이콘 정의는 icons.js(window.ICONS) 단일 소스 — 여기선 안 둠.
    btnToggle.innerHTML = window.ICONS.debug;

    // 상단바 왼쪽(grid col1) flex 컨테이너. kitan 처럼 #btn-disk 가 이미 있으면 나란히 둔다.
    var wrap = document.createElement('div');
    wrap.style.cssText = 'grid-column:1;justify-self:start;display:flex;align-items:center';
    var existingLeft = document.getElementById('btn-disk');
    if (existingLeft) {
      topbar.insertBefore(wrap, existingLeft);
      wrap.appendChild(existingLeft);
      existingLeft.style.gridColumn = '';
    } else {
      topbar.insertBefore(wrap, topbar.firstChild);
    }
    wrap.appendChild(btnToggle);

    // 패널 — 고정 오버레이. 기본 숨김, 토글로만 표시.
    panel = document.createElement('div');
    panel.id = 'debug-panel';
    panel.className = 'hidden';

    var h = document.createElement('h4');
    h.textContent = 'DEBUG · 디스크';
    listEl = document.createElement('div');

    msgEl = document.createElement('div');
    msgEl.className = 'dbg-msg';

    panel.appendChild(h);
    panel.appendChild(listEl);
    panel.appendChild(msgEl);
    document.body.appendChild(panel);

    fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.fdi,.hdi,.hdm,.xdf,.d88';
    fileInput.style.display = 'none';
    fileInput.addEventListener('change', onFile);
    document.body.appendChild(fileInput);

    btnToggle.addEventListener('click', function () {
      panel.classList.toggle('hidden');
      btnToggle.classList.toggle('active');
    });

    openDB().then(function (d) { db = d; refreshKeys(); })
            .catch(function (err) { setMsg('IDB 열기 실패: ' + err); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
