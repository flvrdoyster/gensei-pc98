// 라이트/다크 테마. <head>에서 동기 로드해 첫 페인트 전에 data-theme을 정한다(깜빡임 방지).
// 사용자가 고른 값은 localStorage에 남기고, 없으면 시스템 설정(prefers-color-scheme)을 따른다.
(function () {
  var LS_KEY = 'gensei-theme';
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function saved() {
    try { return localStorage.getItem(LS_KEY); } catch (e) { return null; }
  }

  function system() {
    return media && media.matches ? 'light' : 'dark';
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    var btn = document.getElementById('btn-theme');
    if (!btn) return;
    // 아이콘·라벨은 누르면 바뀔 테마를 보여준다
    var next = theme === 'light' ? 'dark' : 'light';
    var label = next === 'light' ? '라이트 모드' : '다크 모드';
    btn.setAttribute('data-icon', next === 'light' ? 'themeLight' : 'themeDark');
    btn.title = label;
    btn.setAttribute('aria-label', label);
    if (window.ICONS) btn.innerHTML = window.ICONS[btn.getAttribute('data-icon')];
  }

  apply(saved() || system());

  if (media) {
    var onChange = function () { if (!saved()) apply(system()); };
    if (media.addEventListener) media.addEventListener('change', onChange);
    else if (media.addListener) media.addListener(onChange);
  }

  // icons.js보다 먼저 등록되므로 data-icon을 정해 두면 icons.js가 그대로 그린다
  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('btn-theme');
    if (!btn) return;
    apply(root.getAttribute('data-theme'));
    btn.addEventListener('click', function () {
      var theme = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      try { localStorage.setItem(LS_KEY, theme); } catch (e) {}
      apply(theme);
    });
  });
})();
