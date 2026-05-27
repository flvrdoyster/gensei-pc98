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

  var needsResume = false;

  function resumeAudio() {
    var ctx = (typeof Module !== 'undefined' && Module.SDL2)
      ? Module.SDL2.audioContext : null;
    if (ctx) ctx.resume();
    needsResume = false;
  }

  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) needsResume = true;
  });

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

  function isMobile() {
    if (new URLSearchParams(location.search).has('gamepad')) return true;
    return ('ontouchstart' in window) && window.innerWidth <= 680;
  }

  function init() {
    if (!isMobile()) return;

    document.body.classList.add('mobile-active');

    var fsBtn = document.getElementById('btn-fullscreen');
    if (fsBtn) fsBtn.style.display = 'none';

    canvas = document.getElementById('canvas');
    canvas.addEventListener('touchstart', function() {
      if (needsResume) resumeAudio();
    });

    var gamepad = document.getElementById('virtual-gamepad');
    if (!gamepad) return;

    gamepad.querySelectorAll('button').forEach(function(btn) {
      btn.setAttribute('tabindex', '-1');
    });

    var activeKey = null;

    gamepad.addEventListener('touchstart', function(e) {
      e.preventDefault();
      resumeAudio();
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
  }

  function initMute() {
    var btn = document.getElementById('btn-mute');
    if (!btn) return;
    var SVG_ON  = '<svg viewBox="0 0 49.13 70.14" height="22"><path fill="currentColor" d="M7.43,68.29c-2.31-1.26-4.13-3.01-5.45-5.25s-1.98-4.77-1.98-7.58.65-5.41,1.96-7.62c1.3-2.21,3.12-3.93,5.45-5.14,2.33-1.22,4.96-1.82,7.89-1.82s5.45.59,7.73,1.76l-.09-42.63h26.19v14.77h-18.72v40.69c0,2.81-.65,5.34-1.96,7.58-1.3,2.24-3.1,3.99-5.38,5.25s-4.88,1.87-7.78,1.85c-2.93.03-5.55-.59-7.87-1.85Z"/></svg>';
    var SVG_OFF = '<svg viewBox="0 0 56.02 70.14" height="22"><rect fill="currentColor" x="26.51" y="-3.04" width="3" height="76.23" transform="translate(-16.59 30.08) rotate(-45)"/><polygon fill="currentColor" points="33.86 35.68 33.86 14.77 52.58 14.77 52.58 0 26.38 0 26.44 28.27 33.86 35.68"/><path fill="currentColor" d="M26.47,42.63c-2.29-1.17-4.86-1.76-7.73-1.76s-5.56.61-7.89,1.82c-2.33,1.22-4.15,2.93-5.45,5.14-1.3,2.21-1.96,4.75-1.96,7.62s.66,5.34,1.98,7.58,3.13,3.99,5.45,5.25c2.31,1.26,4.94,1.87,7.87,1.85,2.9.03,5.49-.59,7.78-1.85s4.08-3.01,5.38-5.25c1.3-2.24,1.96-4.77,1.96-7.58v-9.12l-7.39-7.39v3.68Z"/></svg>';
    var muted = false;
    btn.addEventListener('click', function() {
      muted = !muted;
      btn.innerHTML = muted ? SVG_OFF : SVG_ON;
      var ctx = (typeof Module !== 'undefined' && Module.SDL2) ? Module.SDL2.audioContext : null;
      if (ctx) (muted ? ctx.suspend() : ctx.resume()).catch(function(){});
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    init();
    initMute();
  });
})();
