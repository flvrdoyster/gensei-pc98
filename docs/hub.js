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

    // 문서 전체에 달아서, Tab으로 메뉴에 들어오기 전에도(포커스가 body에 있어도) 화살표가
    // 바로 먹게 한다. 메뉴·body가 아닌 다른 데 초점이 있으면(사이트 링크 아이콘 등) 손대지
    // 않는다. 모바일은 스크롤로 선택을 넘기므로 여기서는 다루지 않는다.
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (narrow.matches) return;
      var i = items.indexOf(document.activeElement);
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

    // footer.js가 푸터를 비동기로 그리므로, 나타날 때까지 잠깐 재시도해서 안의 링크를
    // Tab 순서에서 뺀다. 메뉴를 화살표로 훑고 나서 Tab 몇 번에 저작권 표기까지 밀려나지
    // 않게 하려는 것 — 마우스 클릭은 tabindex와 무관하게 그대로 된다.
    var footerTries = 0;
    var footerTimer = setInterval(function () {
      var footer = document.getElementById('footer');
      if (footer) {
        [].forEach.call(footer.querySelectorAll('a'), function (a) { a.tabIndex = -1; });
      }
      if (footer || ++footerTries > 40) clearInterval(footerTimer);
    }, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
