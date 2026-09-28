(function () {
  'use strict';

  function init() {
    var track = document.querySelector('.hub-select');
    if (!track) return;
    var menu = track.querySelector('.hub-menu');
    var items = [].slice.call(menu.querySelectorAll('a'));
    var stage = track.querySelector('.hub-stage');
    var strip = track.querySelector('.hub-strip');
    var dotsBox = track.querySelector('.hub-dots');
    var hint = track.querySelector('.hub-hint');
    var narrow = window.matchMedia('(max-width: 680px)');
    var n = items.length;
    var cur = -1;
    var ticking = false;

    track.style.setProperty('--hub-count', n);
    var dots = items.map(function (a) {
      var art = document.createElement('i');
      art.style.backgroundImage = "url('" + a.getAttribute('data-art') + "')";
      strip.appendChild(art);
      var dot = document.createElement('b');
      dotsBox.appendChild(dot);
      return dot;
    });

    function place(k, force) {
      if (k === cur && !force) return;
      cur = k;
      var li = items[k].parentNode;
      menu.style.setProperty('--sel-top', li.offsetTop + 'px');
      menu.style.setProperty('--sel-h', li.offsetHeight + 'px');
      strip.style.transform = 'translateY(' + (-100 * k / n) + '%)';
      items.forEach(function (a, i) { a.classList.toggle('on', i === k); });
      dots.forEach(function (d, i) { d.classList.toggle('on', i === k); });
      stage.href = items[k].getAttribute('href');
    }

    items.forEach(function (a, i) {
      a.addEventListener('pointerenter', function (e) {
        if (e.pointerType === 'mouse' && !narrow.matches) place(i);
      });
      a.addEventListener('focus', function () { place(i); });
    });

    function onScroll() {
      ticking = false;
      if (hint) hint.classList.toggle('gone', window.scrollY > 8);
      if (!narrow.matches) return;
      var top = track.getBoundingClientRect().top + window.scrollY;
      var range = track.offsetHeight - window.innerHeight;
      var p = range > 0 ? (window.scrollY - top) / range : 0;
      place(Math.max(0, Math.min(n - 1, Math.floor(p * n))));
    }

    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
    }, { passive: true });
    window.addEventListener('resize', function () { place(cur, true); onScroll(); });
    place(0, true);
    onScroll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
