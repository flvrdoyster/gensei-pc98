// 라이트/다크 테마. <head>에서 동기 로드해 첫 페인트 전에 <html data-theme>을 정한다(깜빡임 방지).
// 우선순위: 주소의 ?theme=light|dark (또는 ?light, ?dark) → 푸터 아래 전환 버튼으로 고른 값(localStorage) → 시스템 설정.
(function () {
  var LS_KEY = 'gensei-theme';
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  var match = /[?&]theme=(light|dark)\b/.exec(location.search) || /[?&](light|dark)(?:[&#=]|$)/.exec(location.search);
  var forced = match ? match[1] : null;

  function saved() {
    try { return localStorage.getItem(LS_KEY); } catch (e) { return null; }
  }

  function current() {
    return forced || saved() || (media && media.matches ? 'light' : 'dark');
  }

  function apply() {
    var theme = current();
    root.setAttribute('data-theme', theme);
    var btn = document.getElementById('btn-theme');
    if (!btn) return;
    // 아이콘은 하나(반쪽 원)로 고정, 라벨만 누르면 바뀔 테마를 알려준다
    var label = theme === 'light' ? '다크 모드' : '라이트 모드';
    btn.title = label;
    btn.setAttribute('aria-label', label);
  }

  apply();

  if (media) {
    var onChange = function () { if (!forced && !saved()) apply(); };
    if (media.addEventListener) media.addEventListener('change', onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('btn-theme');
    if (!btn) return;
    apply();
    btn.addEventListener('click', function () {
      var next = current() === 'light' ? 'dark' : 'light';
      try { localStorage.setItem(LS_KEY, next); } catch (e) {}
      forced = null;
      apply();
    });
  });
})();
