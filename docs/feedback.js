(function () {
  'use strict';

  var CONFIG = {
    endpoint: 'https://script.google.com/macros/s/AKfycbynrg-9ZMAgheqUp9-cGcfMKfOCSFd4m4pp4SwXU2ZmzcEJgG-qW9A0P4A9C_cGdYkW/exec',
    showButton: false,

    maxLength: 2000,
    cooldownMs: 10 * 1000,
    attachShotByDefault: true,

    // 왼쪽 값은 시트에 쌓이는 분류 키라, 바꾸면 기존 기록과 어긋난다.
    categories: [
      ['impression', '감상'],
      ['bug', '오류 제보'],
      ['translation', '번역 개선'],
    ],

    text: {
      buttonTitle: '의견 보내기',
      heading: '의견 보내기',
      placeholder: '구체적으로 작성해 주시면 큰 도움이 됩니다.',
      attachShot: '현재 화면 첨부',
      send: '보내기',
      sending: '보내는 중...',
      close: '닫기',
      note: '타이틀·버전·브라우저 정보가 함께 전송됩니다.',
      sent: '감사합니다.',
      sendFail: '전송에 실패했습니다. 잠시 후 다시 시도해 주세요.',
      cooldown: '잠시 후 다시 보내주세요. ({sec}초)'
    },

    style: {
      panelWidth: '380px',
      backdrop: 'rgba(0,0,0,0.5)',
      textareaMinHeight: '88px'
    }
  };

  var T = CONFIG.text;
  var LS_KEY = 'gensei-feedback-last';

  var STYLE =
    '#fb-overlay{position:fixed;inset:0;z-index:300;display:flex;' +
    'align-items:center;justify-content:center;padding:16px;' +
    'background:' + CONFIG.style.backdrop + ';' +
    '-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}' +
    '#fb-overlay.hidden{display:none}' +
    // 패널에 font-size 를 두면 자식들의 em 이 이중으로 곱해진다.
    '#fb-panel{' +
    'background:rgba(38,38,38,0.98);border-radius:6px;' +
    'padding:14px 16px;width:min(' + CONFIG.style.panelWidth + ',100%);' +
    'max-height:calc(100vh - 32px);overflow-y:auto;' +
    'color:rgba(204,204,204,1);' +
    'box-shadow:0 8px 28px rgba(0,0,0,0.55)}' +
    '#fb-panel h4{margin:0 0 8px;font-size:var(--font-md);color:rgba(204,204,204,1)}' +
    '#fb-panel select,#fb-panel textarea{width:100%;box-sizing:border-box;' +
    'background:rgba(30,30,30,1);color:rgba(204,204,204,1);color-scheme:dark;' +
    'border:1px solid rgba(68,68,68,1);border-radius:4px;padding:5px 7px;' +
    'font-family:inherit;font-size:var(--font-sm)}' +
    '#fb-panel textarea{margin-top:6px;resize:vertical;line-height:1.5;' +
    'min-height:' + CONFIG.style.textareaMinHeight + '}' +
    '#fb-panel select:focus,#fb-panel textarea:focus{outline:none;border-color:rgba(119,119,119,1)}' +
    '#fb-panel .fb-shot{display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer;' +
    'user-select:none;color:rgba(153,153,153,1);font-size:var(--font-sm)}' +
    '#fb-panel .fb-shot img{width:64px;height:40px;object-fit:cover;border:1px solid rgba(68,68,68,1);' +
    'border-radius:3px;image-rendering:pixelated}' +
    '#fb-panel .fb-actions{display:flex;align-items:center;gap:8px;margin-top:10px}' +
    '#fb-panel .fb-count{margin-left:auto;color:rgba(119,119,119,1);font-size:var(--font-sm);' +
    'font-variant-numeric:tabular-nums}' +
    '#fb-panel .fb-count.over{color:rgba(224,128,128,1)}' +
    '#fb-panel button{font-size:var(--font-sm);padding:3px 12px}' +
    '#fb-panel button:disabled{opacity:0.4;cursor:default}' +
    '#fb-panel .fb-msg{margin-top:8px;color:rgba(119,119,119,1);font-size:var(--font-sm);' +
    'min-height:1.4em;word-break:break-all}' +
    '#fb-panel .fb-note{margin-top:6px;color:rgba(119,119,119,1);font-size:var(--font-sm);line-height:1.5}';

  var overlay, panel, msgEl, textEl, selEl, countEl, shotWrap, shotChk, shotImg, btnSend, btnToggle;
  var shotData = null;
  var sending = false;

  function setMsg(t) { if (msgEl) msgEl.textContent = t || ''; }

  function gameName() {
    return (typeof window.GAME !== 'undefined' && window.GAME) ? window.GAME : 'index';
  }

  function siteVersion() {
    var el = document.querySelector('.site-version');
    return el ? el.textContent.trim() : '';
  }

  /**
   * 캔버스 캡처를 가능하게 하는 준비 작업. **에뮬레이터 전역 렌더링에 영향을 준다.**
   *
   * SDL 이 WebGL 렌더러를 고르면 캔버스가 WebGL 컨텍스트가 되는데, WebGL 은 컴포지팅 직후
   * 드로잉 버퍼를 비운다(preserveDrawingBuffer 기본 false). 그래서 나중에(버튼 클릭 시점)
   * toDataURL 을 부르면 새까만 이미지가 나온다 — 화면엔 보이지만 버퍼엔 없는 상태.
   * 이 속성은 **컨텍스트 생성 시점에만** 지정 가능해서, 에뮬레이터가 컨텍스트를 만들기 전에
   * canvas.getContext 를 감싸 강제 주입한다. (글루 emnp2kai_sdl2.js 를 패치하면 NP2kai
   * 재빌드 때마다 날아가므로 이 방식을 택함)
   *
   * 비용: 프레임마다 버퍼 swap 대신 복사가 일어난다. 640x400 이라 프레임당 1MB 수준으로,
   * CPU 에뮬레이션 부하에 비하면 무시할 만하다(실기 체감 차이 없음 확인).
   *
   * SDL 이 2D 렌더러를 고른 경우엔 이 래퍼가 아무 일도 하지 않는다(2D 는 원래 캡처됨).
   * 실제로 같은 코드에서 환경에 따라 캡처가 되기도/안 되기도 했던 이유로 추정된다.
   */
  function enableCanvasCapture() {
    var c = document.getElementById('canvas');
    if (!c || c._captureReady) return;
    var orig = c.getContext;
    c.getContext = function (type, attrs) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
        attrs = Object.assign({}, attrs || {}, { preserveDrawingBuffer: true });
      }
      return orig.call(this, type, attrs);
    };
    c._captureReady = true;
  }

  function captureShot() {
    var c = document.getElementById('canvas');
    if (!c || !c.width || !c.height) return null;
    try {
      return c.toDataURL('image/png');
    } catch (e) {
      return null;
    }
  }

  function updateCount() {
    var n = textEl.value.length;
    countEl.textContent = n + ' / ' + CONFIG.maxLength;
    countEl.className = 'fb-count' + (n > CONFIG.maxLength ? ' over' : '');
    btnSend.disabled = sending || n === 0 || n > CONFIG.maxLength;
  }

  function cooldownLeft() {
    try {
      var last = parseInt(localStorage.getItem(LS_KEY) || '0', 10);
      var left = CONFIG.cooldownMs - (Date.now() - last);
      return left > 0 ? left : 0;
    } catch (e) {
      return 0;
    }
  }

  function send() {
    if (sending) return;
    var body = textEl.value.trim();
    if (!body) return;

    var left = cooldownLeft();
    if (left > 0) {
      setMsg(T.cooldown.replace('{sec}', Math.ceil(left / 1000)));
      return;
    }

    sending = true;
    btnSend.disabled = true;
    btnSend.textContent = T.sending;
    setMsg('');

    var payload = {
      category: selEl.value,
      message: body.slice(0, CONFIG.maxLength),
      game: gameName(),
      version: siteVersion(),
      ua: navigator.userAgent,
      url: location.href,
      website: panel.querySelector('.fb-hp').value,
      shot: (shotChk && shotChk.checked && shotData) ? shotData : ''
    };

    fetch(CONFIG.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.text();
    }).then(function (text) {
      if (text.trim() !== 'ok') throw new Error('unexpected response: ' + text.slice(0, 80));
      try { localStorage.setItem(LS_KEY, String(Date.now())); } catch (e) {}
      textEl.value = '';
      updateCount();
      setMsg(T.sent);
      if (typeof window.track === 'function') window.track('feedback_sent');
      setTimeout(hide, 1200);
    }).catch(function (e) {
      setMsg(T.sendFail);
      if (window.console) console.warn('feedback send failed:', e);
    }).then(function () {
      sending = false;
      btnSend.textContent = T.send;
      updateCount();
    });
  }

  function show() {
    overlay.classList.remove('hidden');
    btnToggle.classList.add('active');
    btnToggle.setAttribute('aria-expanded', 'true');
    shotData = captureShot();
    if (shotWrap) {
      if (shotData) {
        shotWrap.style.display = '';
        shotImg.src = shotData;
      } else {
        shotWrap.style.display = 'none';
        if (shotChk) shotChk.checked = false;
      }
    }
    textEl.focus();
  }

  function hide() {
    overlay.classList.add('hidden');
    btnToggle.classList.remove('active');
    btnToggle.setAttribute('aria-expanded', 'false');
    setMsg('');
  }

  function isOpen() { return !overlay.classList.contains('hidden'); }

  function build() {
    var style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);

    btnToggle = document.createElement('button');
    btnToggle.className = 'btn-icon';
    btnToggle.id = 'btn-feedback';
    btnToggle.title = T.buttonTitle;
    btnToggle.setAttribute('aria-label', T.buttonTitle);
    btnToggle.setAttribute('aria-expanded', 'false');
    btnToggle.setAttribute('aria-controls', 'fb-panel');
    btnToggle.innerHTML = window.ICONS.feedback;

    document.getElementById('topbar-left').appendChild(btnToggle);

    overlay = document.createElement('div');
    overlay.id = 'fb-overlay';
    overlay.className = 'hidden';

    panel = document.createElement('div');
    panel.id = 'fb-panel';

    var h = document.createElement('h4');
    h.textContent = T.heading;

    selEl = document.createElement('select');
    CONFIG.categories.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c[0];
      o.textContent = c[1];
      selEl.appendChild(o);
    });

    textEl = document.createElement('textarea');
    textEl.placeholder = T.placeholder;
    textEl.maxLength = CONFIG.maxLength;

    var hp = document.createElement('input');
    hp.type = 'text';
    hp.className = 'fb-hp';
    hp.tabIndex = -1;
    hp.setAttribute('autocomplete', 'off');
    hp.setAttribute('aria-hidden', 'true');
    hp.style.cssText = 'position:absolute;left:-9999px;width:1px;height:1px;opacity:0';

    panel.appendChild(h);
    panel.appendChild(selEl);
    panel.appendChild(textEl);
    panel.appendChild(hp);

    if (document.getElementById('canvas')) {
      shotWrap = document.createElement('label');
      shotWrap.className = 'fb-shot';
      shotChk = document.createElement('input');
      shotChk.type = 'checkbox';
      shotChk.checked = CONFIG.attachShotByDefault;
      shotImg = document.createElement('img');
      shotImg.alt = T.attachShot;
      var shotTxt = document.createElement('span');
      shotTxt.textContent = T.attachShot;
      shotWrap.appendChild(shotChk);
      shotWrap.appendChild(shotImg);
      shotWrap.appendChild(shotTxt);
      panel.appendChild(shotWrap);
    }

    var actions = document.createElement('div');
    actions.className = 'fb-actions';
    btnSend = document.createElement('button');
    btnSend.textContent = T.send;
    btnSend.disabled = true;
    btnSend.addEventListener('click', send);
    var btnClose = document.createElement('button');
    btnClose.textContent = T.close;
    btnClose.addEventListener('click', hide);
    countEl = document.createElement('span');
    countEl.className = 'fb-count';
    actions.appendChild(btnSend);
    actions.appendChild(btnClose);
    actions.appendChild(countEl);

    msgEl = document.createElement('div');
    msgEl.className = 'fb-msg';

    var note = document.createElement('div');
    note.className = 'fb-note';
    note.textContent = T.note;

    panel.appendChild(actions);
    panel.appendChild(msgEl);
    panel.appendChild(note);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    ['keydown', 'keyup', 'keypress'].forEach(function (type) {
      overlay.addEventListener(type, function (e) {
        e.stopPropagation();
        if (type === 'keydown' && e.key === 'Escape') hide();
      });
    });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) hide();
    });
    textEl.addEventListener('input', updateCount);
    btnToggle.addEventListener('click', function () {
      if (isOpen()) hide(); else show();
      btnToggle.blur();
    });

    updateCount();
  }

  function init() {
    if (!document.getElementById('topbar-left')) return;
    if (!CONFIG.endpoint || !CONFIG.showButton) return;
    if (!window.ICONS || !window.ICONS.feedback) return;
    if (document.getElementById('btn-feedback')) return;
    enableCanvasCapture();
    build();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
