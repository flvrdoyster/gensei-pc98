(function () {
  'use strict';

  var MILESTONES = [5, 15, 30, 60, 120];
  var TICK_MS = 60000;
  var started = false;
  var minutes = 0;
  var sent = 0;
  var lastInput = 0;
  var lastTick = 0;

  function mark() { lastInput = Date.now(); }

  function pollPads() {
    var pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (var i = 0; i < pads.length; i++) {
      var p = pads[i];
      if (!p) continue;
      for (var b = 0; b < p.buttons.length; b++) if (p.buttons[b].pressed) return mark();
      for (var a = 0; a < p.axes.length; a++) if (Math.abs(p.axes[a]) > 0.5) return mark();
    }
  }

  function tick() {
    var now = Date.now();
    if (document.visibilityState === 'visible' && lastInput > lastTick) minutes++;
    lastTick = now;
    while (sent < MILESTONES.length && minutes >= MILESTONES[sent]) {
      (window.dataLayer = window.dataLayer || []).push({
        event: 'play_milestone', game: window.GAME, minutes: MILESTONES[sent]
      });
      sent++;
    }
  }

  function start() {
    if (started) return;
    started = true;
    lastTick = Date.now();
    ['keydown', 'pointerdown', 'touchstart'].forEach(function (type) {
      window.addEventListener(type, mark, { capture: true, passive: true });
    });
    setInterval(pollPads, 1000);
    setInterval(tick, TICK_MS);
  }

  window.PlayTime = { start: start };
})();
