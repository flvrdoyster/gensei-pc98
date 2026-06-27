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

  function idbKeys(db) {
    return new Promise(function (resolve, reject) {
      var req = db.transaction(IDB_STORE).objectStore(IDB_STORE).getAllKeys();
      req.onsuccess = function () { resolve(req.result || []); };
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

  // 고정 오버레이 패널. 페이지 팔레트(어두운 패널·#444 보더·KoddiUD 폰트)에 맞추고,
  // 액션 버튼은 기존 button 스타일을 그대로 쓴다. 상단 좌측에 떠서 하단 게임패드는 안 가린다.
  var STYLE =
    '#debug-panel{position:fixed;top:56px;left:8px;z-index:300;' +
    'background:rgba(38,38,38,0.97);border:1px solid rgba(68,68,68,1);border-radius:6px;' +
    'padding:12px 14px;max-width:min(360px,calc(100vw - 16px));' +
    'color:rgba(204,204,204,1);font-size:var(--font-sm);' +
    'box-shadow:0 6px 20px rgba(0,0,0,0.45);' +
    '-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}' +
    '#debug-panel.hidden{display:none}' +
    '#debug-panel h4{margin:0 0 8px;font-size:var(--font-md);color:rgba(170,170,170,1)}' +
    '#debug-panel .dbg-key{margin:2px 0;word-break:break-all}' +
    '#debug-panel .dbg-actions{display:flex;gap:8px;margin-top:10px}' +
    '#debug-panel button{font-size:var(--font-sm);padding:3px 10px}' +
    '#debug-panel button:disabled{opacity:0.4;cursor:default}' +
    '#debug-panel .dbg-msg{margin-top:8px;color:rgba(119,119,119,1);min-height:1.4em;word-break:break-all}';

  var db = null;
  var panel, listEl, msgEl, fileInput, btnToggle, btnExport, btnDelete;
  var pendingKey = null;
  var currentKeys = [];

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
    idbKeys(db).then(function (keys) {
      currentKeys = keys;
      listEl.innerHTML = '';
      keys.forEach(function (key) {
        var d = document.createElement('div');
        d.className = 'dbg-key';
        d.textContent = key;
        listEl.appendChild(d);
      });
      if (!keys.length) {
        var none = document.createElement('div');
        none.className = 'dbg-key';
        none.textContent = '캐시된 디스크 없음';
        listEl.appendChild(none);
      }
      btnExport.disabled = btnDelete.disabled = !keys.length;
    });
  }

  // 가져오기: 캐시에 키가 하나면 그 키를 덮어쓰고, 없거나 여럿이면 파일명을 키로 쓴다.
  function doImport() {
    pendingKey = currentKeys.length === 1 ? currentKeys[0] : null;
    fileInput.click();
  }

  function doExport() {
    currentKeys.forEach(function (key) {
      idbGet(db, key).then(function (buf) { if (buf) download(key, buf); });
    });
    setMsg('내보내기: ' + currentKeys.join(', '));
  }

  function doDelete() {
    Promise.all(currentKeys.map(function (k) { return idbDelete(db, k); })).then(function () {
      setMsg('삭제됨 — 새로고침하면 원본으로');
      refreshKeys();
    });
  }

  function onFile(e) {
    var file = e.target.files[0];
    fileInput.value = '';
    if (!file) return;
    var key = pendingKey || file.name;
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
    btnToggle.innerHTML =
      '<svg viewBox="2 4 28 24" height="22"><path fill="currentColor" d="M29,15h-5.1c-0.1-1.2-0.5-2.4-1-3.5c1.9-1.5,3.1-3.7,3.1-6.1V5c0-0.6-0.4-1-1-1s-1,0.4-1,1v0.4c0,1.8-0.8,3.4-2.2,4.5c-0.5-0.7-1.2-1.2-1.9-1.7c0-0.1,0-0.1,0-0.2c0-2.2-1.8-4-4-4s-4,1.8-4,4c0,0.1,0,0.1,0,0.2c-0.7,0.5-1.3,1-1.9,1.7C8.8,8.8,8,7.2,8,5.4V5c0-0.6-0.4-1-1-1S6,4.4,6,5v0.4c0,2.4,1.1,4.7,3.1,6.1c-0.5,1-0.9,2.2-1,3.5H3c-0.6,0-1,0.4-1,1s0.4,1,1,1h5.1c0.1,1.2,0.5,2.4,1,3.5C7.1,21.9,6,24.2,6,26.6V27c0,0.6,0.4,1,1,1s1-0.4,1-1v-0.4c0-1.8,0.8-3.4,2.2-4.5c1.5,1.8,3.5,2.9,5.8,2.9s4.4-1.1,5.8-2.9c1.4,1.1,2.2,2.7,2.2,4.5V27c0,0.6,0.4,1,1,1s1-0.4,1-1v-0.4c0-2.4-1.1-4.7-3.1-6.1c0.5-1,0.9-2.2,1-3.5H29c0.6,0,1-0.4,1-1S29.6,15,29,15z"/></svg>';
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
    listEl.className = 'dbg-list';

    var actions = document.createElement('div');
    actions.className = 'dbg-actions';
    actions.appendChild(makeBtn('가져오기', doImport, '파일 선택 → 캐시에 저장(키=단일 캐시키 또는 파일명)'));
    btnExport = makeBtn('내보내기', doExport, '캐시된 디스크를 파일로 저장');
    btnDelete = makeBtn('삭제', doDelete, '캐시에서 제거(원본 복귀)');
    actions.appendChild(btnExport);
    actions.appendChild(btnDelete);

    msgEl = document.createElement('div');
    msgEl.className = 'dbg-msg';

    panel.appendChild(h);
    panel.appendChild(listEl);
    panel.appendChild(actions);
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
