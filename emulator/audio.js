(function() {
  'use strict';

  var muted = false;
  var needsResume = false;

  function getAudioContext() {
    return (typeof Module !== 'undefined' && Module.SDL2)
      ? Module.SDL2.audioContext : null;
  }

  var muteShown = false;
  function showMuteButton() {
    if (muteShown) return;
    var btn = document.getElementById('btn-mute');
    if (btn) { btn.style.display = ''; muteShown = true; }
  }

  window.resumeAudio = function() {
    if (getAudioContext()) showMuteButton();
    if (muted) return;
    var ctx = getAudioContext();
    if (ctx) ctx.resume();
    needsResume = false;
  };

  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
      needsResume = true;
      resumeAudio();
    }
  });

  function onUserInteraction() {
    if (getAudioContext()) showMuteButton();
    if (needsResume) resumeAudio();
  }

  document.addEventListener('click', onUserInteraction);
  document.addEventListener('keydown', onUserInteraction);

  function initMute() {
    var btn = document.getElementById('btn-mute');
    if (!btn) return;
    btn.addEventListener('click', function() {
      muted = !muted;
      btn.innerHTML = window.ICONS[muted ? 'muteOff' : 'mute'];
      btn.setAttribute('aria-pressed', String(muted));
      var ctx = getAudioContext();
      if (ctx) (muted ? ctx.suspend() : ctx.resume()).catch(function(){});
      btn.blur();
    });
  }

  document.addEventListener('DOMContentLoaded', initMute);
})();
