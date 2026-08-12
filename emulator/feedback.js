// 피드백(버그 신고·번역 오류·감상) 패널 — 게임 페이지 전용.
// Google Apps Script 웹앱으로 POST → 구글 시트 (수신 쪽은 tools/feedback-appsscript.gs).
// 허브(index)는 상단바가 없어 성격이 달라, 패널 대신 블로그 링크(CONFIG.blog)만 띄운다.
//
// 문구·항목·수치·치수는 전부 아래 CONFIG 에만 있다. 그 아래 동작 코드는 건드릴 일이 거의 없다.
//
// 동작 코드를 고칠 땐 주의:
//  - Content-Type 은 반드시 'text/plain'. Apps Script 는 preflight(OPTIONS)를 처리 못 해
//    application/json 이면 CORS 로 실패한다. mode:'no-cors' 도 쓰면 안 됨 — 응답을 못 읽어
//    실패해도 "전송됨"이 떠버린다.
//  - 응답은 반드시 검사한다(res.ok + 본문이 정확히 'ok'). 검사를 빼면 어떤 실패든
//    성공처럼 보여서 디버깅이 불가능해진다 — 실제로 그 상태로 한동안 방치된 적 있음.
//  - 오버레이 안 키 이벤트는 전파를 끊는다. 에뮬레이터가 document keydown 을 canvas 로
//    넘기므로 안 끊으면 타이핑이 게임에도 입력된다.
(function () {
  'use strict';

  // ── 설정 ────────────────────────────────────────────────────────────
  var CONFIG = {
    // 배포한 Apps Script 웹앱 URL (…/exec). 비어 있으면 버튼 자체를 만들지 않는다.
    endpoint: 'https://script.google.com/macros/s/AKfycbynrg-9ZMAgheqUp9-cGcfMKfOCSFd4m4pp4SwXU2ZmzcEJgG-qW9A0P4A9C_cGdYkW/exec',

    // 허브(index)는 상단바가 없는 별도 레이아웃이라, 피드백 패널 대신
    // 블로그로 나가는 단순 링크 버튼을 둔다(게임 페이지는 기존 피드백 패널 그대로).
    blog: {
      url: 'https://oysterbay.tistory.com/129',
      title: '블로그'
    },

    maxLength: 2000,          // 메시지 최대 글자수
    cooldownMs: 10 * 1000,    // 연속 전송 방지 간격 (localStorage 기준)
    attachShotByDefault: true, // 스크린샷 첨부 체크박스 기본값

    // ['시트에 기록될 값', '화면에 보일 이름']
    // ⚠ 왼쪽 값을 바꾸면 시트에 이미 쌓인 분류와 안 맞는다. 표시 이름만 바꾸는 건 안전.
    categories: [
      ['impression', '감상'],
      ['bug', '오류 제보'],
      ['translation', '번역 개선'],
    ],

    text: {
      buttonTitle: '의견 보내기',                   // 상단바 버튼 툴팁
      heading: '의견 보내기',                       // 모달 제목
      placeholder: '구체적으로 작성해 주시면 큰 도움이 됩니다.',
      attachShot: '현재 화면 첨부',                 // 스크린샷 체크박스 라벨
      send: '보내기',
      sending: '보내는 중...',
      close: '닫기',
      note: '타이틀·버전·브라우저 정보가 함께 전송됩니다.',
      sent: '감사합니다.',
      sendFail: '전송에 실패했습니다. 잠시 후 다시 시도해 주세요.',
      cooldown: '잠시 후 다시 보내주세요. ({sec}초)'  // {sec} 자리에 남은 초가 들어감
    },

    style: {
      panelWidth: '380px',
      backdrop: 'rgba(0,0,0,0.5)',
      textareaMinHeight: '88px'
    }
  };
  // ── 설정 끝 ─────────────────────────────────────────────────────────

  var T = CONFIG.text;
  var LS_KEY = 'gensei-feedback-last';

  var STYLE =
    // 가운데 모달. 캔버스·상단바가 640px 가운데 정렬이라 구석 고정 패널은 콘텐츠와 떨어져 보인다.
    '#fb-overlay{position:fixed;inset:0;z-index:300;display:flex;' +
    'align-items:center;justify-content:center;padding:16px;' +
    'background:' + CONFIG.style.backdrop + ';' +
    '-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}' +
    '#fb-overlay.hidden{display:none}' +
    // 패널 자체엔 font-size 를 안 둔다 — 여기서 다시 var(--font-*)를 걸면 안쪽 요소들의
    // em 이 이 축소된 값 기준으로 다시 곱해져 위계가 뒤집힌다(제목이 본문보다 작아짐).
    // 자식들은 전부 body(root) 기준으로 var(--font-sm/md)를 직접 쓴다.
    '#fb-panel{' +
    'background:rgba(38,38,38,0.98);border-radius:6px;' +
    'padding:14px 16px;width:min(' + CONFIG.style.panelWidth + ',100%);' +
    'max-height:calc(100vh - 32px);overflow-y:auto;' +
    'color:rgba(204,204,204,1);' +
    'box-shadow:0 8px 28px rgba(0,0,0,0.55)}' +
    '#fb-panel h4{margin:0 0 8px;font-size:var(--font-md);color:rgba(204,204,204,1)}' +
    // color-scheme:dark 를 줘야 네이티브 위젯이 다크로 그려진다 — 없으면 select 의
    // 드롭다운 화살표가 검게 나와 어두운 배경에서 안 보이고, 펼친 목록도 흰 바탕이 된다.
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
    // version.js 가 푸터에 주입한 값을 그대로 읽는다 (버전 단일 소스를 중복 정의하지 않으려고).
    var el = document.querySelector('.site-version');
    return el ? el.textContent.trim() : '';
  }

  // 캔버스 스냅샷. 게임 페이지에만 캔버스가 있고, 시작 전이면 빈 화면이라 의미 없다.
  function captureShot() {
    var c = document.getElementById('canvas');
    if (!c || !c.width || !c.height) return null;
    try {
      return c.toDataURL('image/png');
    } catch (e) {
      return null;   // WebGL 컨텍스트 등으로 실패하면 스크린샷 없이 진행
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
      return 0;   // 사파리 프라이빗 모드 등 localStorage 불가 — 쿨다운 없이 진행
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
      // 허니팟: 사람은 비워두고, 폼을 자동으로 채우는 봇만 값을 넣는다.
      website: panel.querySelector('.fb-hp').value,
      shot: (shotChk && shotChk.checked && shotData) ? shotData : ''
    };

    // Content-Type: text/plain → simple request 라 preflight 가 안 뜬다 (파일 상단 주석 참조)
    fetch(CONFIG.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      // 응답을 반드시 검사한다. 예전엔 res.text() 결과를 버리고 무조건 성공 처리해서,
      // 권한 오류로 로그인 HTML 이 오든 스크립트가 'error' 를 뱉든 사용자에겐 똑같이
      // "감사합니다" 가 떴다 — 실패가 드러나지 않아 원인 파악이 불가능했음.
      // Apps Script 는 정상 처리 시 본문에 'ok' 만 반환한다 (tools/feedback-appsscript.gs).
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
    // 열 때마다 현재 화면을 새로 캡처 (게임 진행 중 장면이 바뀌므로)
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
    setMsg('');
  }

  function isOpen() { return !overlay.classList.contains('hidden'); }

  // 허브(index)는 상단바가 없는 별도 레이아웃 — 피드백 패널 대신 블로그로 나가는
  // 단순 링크 하나만 목록 아래에 둔다. 게임 페이지의 build()와는 완전히 별개 경로.
  function buildBlogLink() {
    var a = document.createElement('a');
    a.className = 'btn-icon';
    a.id = 'btn-blog';
    a.href = CONFIG.blog.url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.title = CONFIG.blog.title;
    a.innerHTML = window.ICONS.blog;

    var host = document.createElement('div');
    host.style.cssText = 'display:flex;justify-content:center;margin:4px 0 8px';
    host.appendChild(a);

    var list = document.querySelector('.game-list');
    if (list && list.parentNode) list.parentNode.insertBefore(host, list.nextSibling);
    else document.body.appendChild(host);
  }

  function build() {
    var style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);

    btnToggle = document.createElement('button');
    btnToggle.className = 'btn-icon';
    btnToggle.id = 'btn-feedback';
    btnToggle.title = T.buttonTitle;
    btnToggle.innerHTML = window.ICONS.feedback;

    var topbar = document.querySelector('.top-bar');
    // 상단바 왼쪽(grid col1) 공유 컨테이너 `#topbar-left` — debug.js 와 같은 id 를 쓴다.
    // 스크립트마다 따로 만들면 grid-column:1 에 div 가 둘이 되어 상단바가 2행으로 깨진다.
    // (로드 순서는 debug.js → feedback.js 지만, 어느 쪽이 먼저 와도 동작하게 양쪽 다 생성 가능)
    var wrap = document.getElementById('topbar-left');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'topbar-left';
      wrap.style.cssText = 'grid-column:1;justify-self:start;display:flex;align-items:center';
      var existingLeft = document.getElementById('btn-disk');
      if (existingLeft) {
        topbar.insertBefore(wrap, existingLeft);
        wrap.appendChild(existingLeft);   // 기존 버튼을 컨테이너 안으로 흡수
        existingLeft.style.gridColumn = '';
      } else {
        topbar.insertBefore(wrap, topbar.firstChild);
      }
    }
    // 항상 보이는 건 피드백뿐이고 디스크(희담)·디버그(?debug)는 조건부라,
    // 피드백을 맨 왼쪽에 고정해 페이지마다 위치가 흔들리지 않게 한다.
    wrap.insertBefore(btnToggle, wrap.firstChild);

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

    // 허니팟 — 화면에서 감추고 보조기술에서도 제외
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

    // 스크린샷 첨부 — 게임 페이지에만. 자동 첨부하지 않고 미리보기 + 체크박스로 동의를 받는다.
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

    // 에뮬레이터가 document keydown 을 canvas 로 넘기므로 패널 입력이 게임에 새어 나간다.
    // 오버레이(패널 포함) 안에서 발생한 키 이벤트는 여기서 끊는다.
    ['keydown', 'keyup', 'keypress'].forEach(function (type) {
      overlay.addEventListener(type, function (e) {
        e.stopPropagation();
        if (type === 'keydown' && e.key === 'Escape') hide();   // ESC 로 닫기
      });
    });
    // 바깥(어두운 배경) 클릭으로 닫기 — 패널 내부 클릭은 무시
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
    var isHub = !document.querySelector('.top-bar');
    if (isHub) {
      if (!CONFIG.blog.url) return;
      if (!window.ICONS || !window.ICONS.blog) return;
      if (document.getElementById('btn-blog')) return;   // 중복 초기화 방지
      buildBlogLink();
      return;
    }
    if (!CONFIG.endpoint) return;       // 엔드포인트 미설정 — 버튼도 안 만든다
    if (!window.ICONS || !window.ICONS.feedback) return;
    if (document.getElementById('btn-feedback')) return;   // 중복 초기화 방지
    build();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
