(function () {
  'use strict';

  function withEuro(name) {
    var c = name.charCodeAt(name.length - 1) - 0xac00;
    var batchim = c >= 0 && c <= 11171 ? c % 28 : 0;
    return name + (batchim && batchim !== 8 ? '으로' : '로');
  }

  function init() {
    var track = document.querySelector('.hub-select');
    if (!track) return;
    var pin = track.querySelector('.hub-pin');
    var menu = track.querySelector('.hub-menu');
    var items = [].slice.call(menu.querySelectorAll('a'));
    var stage = track.querySelector('.hub-stage');
    var strip = track.querySelector('.hub-strip');
    var go = track.querySelector('.hub-go');
    var sub = track.querySelector('.hub-sub');
    var hint = track.querySelector('.hub-hint');
    var n = items.length;
    var cur = -1;
    var ticking = false;

    function scrollSelects() { return getComputedStyle(pin).position === 'sticky'; }
    function tapSelects() { return getComputedStyle(go).display !== 'none'; }

    track.style.setProperty('--hub-count', n);
    items.forEach(function (a) {
      var art = document.createElement('i');
      art.style.backgroundImage = "url('" + a.getAttribute('data-art') + "')";
      strip.appendChild(art);
    });

    function place(k, force) {
      if (k === cur && !force) return;
      cur = k;
      var a = items[k];
      var li = a.parentNode;
      menu.style.setProperty('--sel-top', li.offsetTop + 'px');
      menu.style.setProperty('--sel-h', li.offsetHeight + 'px');
      strip.style.transform = 'translateY(' + (-100 * k / n) + '%)';
      items.forEach(function (x, i) {
        x.classList.toggle('on', i === k);
        if (i === k) x.setAttribute('aria-current', 'true');
        else x.removeAttribute('aria-current');
      });
      stage.href = go.href = a.getAttribute('href');
      go.setAttribute('aria-label', withEuro(a.querySelector('img').alt) + ' 이동');
      sub.innerHTML = a.querySelector('span').innerHTML;
    }

    function syncRole() {
      var tap = tapSelects();
      items.forEach(function (a) {
        if (tap) a.setAttribute('role', 'button');
        else a.removeAttribute('role');
      });
    }

    function segmentTop(i) {
      var top = track.getBoundingClientRect().top + window.scrollY;
      var range = track.offsetHeight - window.innerHeight;
      return top + range * (i + 0.5) / n;
    }

    items.forEach(function (a, i) {
      a.addEventListener('pointerenter', function (e) {
        if (e.pointerType === 'mouse' && !scrollSelects()) place(i);
      });
      a.addEventListener('focus', function () {
        if (!tapSelects()) place(i);
      });
      a.addEventListener('click', function (e) {
        if (!tapSelects()) return;
        e.preventDefault();
        if (scrollSelects()) window.scrollTo({ top: segmentTop(i), behavior: 'instant' });
        place(i);
      });
    });

    document.addEventListener('keydown', function (e) {
      var i = items.indexOf(document.activeElement);
      if (e.key === ' ' && i !== -1 && tapSelects()) {
        e.preventDefault();
        items[i].click();
        return;
      }
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (tapSelects()) return;
      if (i === -1) {
        if (document.activeElement !== document.body) return;
        i = cur;
      }
      e.preventDefault();
      items[(i + (e.key === 'ArrowDown' ? 1 : n - 1)) % n].focus();
    });

    function onScroll() {
      ticking = false;
      if (hint) hint.classList.toggle('gone', window.scrollY > 8);
      if (!scrollSelects()) return;
      var top = track.getBoundingClientRect().top + window.scrollY;
      var range = track.offsetHeight - window.innerHeight;
      var p = range > 0 ? (window.scrollY - top) / range : 0;
      place(Math.max(0, Math.min(n - 1, Math.floor(p * n))));
    }

    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
    }, { passive: true });
    window.addEventListener('resize', function () { syncRole(); place(cur, true); onScroll(); });
    syncRole();
    place(0, true);
    onScroll();

    function hideFooterLinks() {
      var footer = document.getElementById('footer');
      if (!footer) return;
      [].forEach.call(footer.querySelectorAll('a'), function (a) { a.tabIndex = -1; });
    }
    hideFooterLinks();
    new MutationObserver(hideFooterLinks).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
