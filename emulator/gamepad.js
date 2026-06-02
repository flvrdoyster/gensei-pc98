(function() {
  'use strict';

  var KEY_MAP = {
    ArrowUp:    { key: 'ArrowUp',    code: 'ArrowUp',    keyCode: 38 },
    ArrowDown:  { key: 'ArrowDown',  code: 'ArrowDown',  keyCode: 40 },
    ArrowLeft:  { key: 'ArrowLeft',  code: 'ArrowLeft',  keyCode: 37 },
    ArrowRight: { key: 'ArrowRight', code: 'ArrowRight', keyCode: 39 },
    Enter:      { key: 'Enter',      code: 'Enter',      keyCode: 13 },
    Escape:     { key: 'Escape',     code: 'Escape',     keyCode: 27 }
  };

  var canvas = null;
  var active = false;

  function dispatchKey(keyName, type) {
    var props = KEY_MAP[keyName];
    if (!props) return;
    var target = canvas || document;
    target.dispatchEvent(new KeyboardEvent(type, {
      key: props.key,
      code: props.code,
      keyCode: props.keyCode,
      which: props.keyCode,
      charCode: 0,
      bubbles: true,
      cancelable: true
    }));
  }

  function activate() {
    if (active) return;
    active = true;
    document.body.classList.add('mobile-active');
  }

  function updateUrl() {
    var params = new URLSearchParams(location.search);
    params.delete('gamepad');
    var rest = params.toString();
    history.replaceState(null, '', location.pathname + (rest ? '?gamepad&' + rest : '?gamepad'));
  }

  function shouldAutoActivate() {
    if (new URLSearchParams(location.search).has('gamepad')) return true;
    return ('ontouchstart' in window) && window.innerWidth <= 680;
  }

  function init() {
    canvas = document.getElementById('canvas');

    // 터치 이벤트 바인딩 (활성화 여부와 무관하게 항상)
    var gamepad = document.getElementById('virtual-gamepad');
    if (!gamepad) return;

    gamepad.querySelectorAll('button').forEach(function(btn) {
      btn.setAttribute('tabindex', '-1');
    });

    var activeKey = null;

    gamepad.addEventListener('touchstart', function(e) {
      e.preventDefault();
      if (typeof resumeAudio === 'function') resumeAudio();
      var btn = e.target.closest('[data-key]');
      if (!btn) return;
      var key = btn.dataset.key;
      if (activeKey && activeKey !== key) {
        dispatchKey(activeKey, 'keyup');
        var prev = gamepad.querySelector('[data-key="' + activeKey + '"]');
        if (prev) prev.classList.remove('active');
      }
      activeKey = key;
      btn.classList.add('active');
      dispatchKey(key, 'keydown');
    }, { passive: false });

    gamepad.addEventListener('touchend', function(e) {
      e.preventDefault();
      if (activeKey) {
        dispatchKey(activeKey, 'keyup');
        var btn = gamepad.querySelector('[data-key="' + activeKey + '"]');
        if (btn) btn.classList.remove('active');
        activeKey = null;
      }
    }, { passive: false });

    gamepad.addEventListener('touchcancel', function(e) {
      e.preventDefault();
      if (activeKey) {
        dispatchKey(activeKey, 'keyup');
        var btn = gamepad.querySelector('[data-key="' + activeKey + '"]');
        if (btn) btn.classList.remove('active');
        activeKey = null;
      }
    }, { passive: false });

    // 자동 활성화
    if (shouldAutoActivate()) activate();

    // 게임패드 활성화 버튼
    var toggleBtn = document.getElementById('btn-gamepad');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function() {
        activate();
        updateUrl();
      });
    }

    // 상단바 접기 버튼
    var collapseBtn = document.getElementById('btn-collapse');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', function() {
        document.body.classList.toggle('chrome-hidden');
        collapseBtn.blur();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
