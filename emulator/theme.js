// 라이트/다크 테마. <head>에서 동기 로드해 첫 페인트 전에 <html data-theme>을 정한다(깜빡임 방지).
// 주소에 ?theme=light / ?theme=dark 가 있으면 그 값을, 없으면 시스템 설정(prefers-color-scheme)을 따른다.
(function () {
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  var match = /[?&]theme=(light|dark)\b/.exec(location.search);
  var forced = match ? match[1] : null;

  function apply() {
    root.setAttribute('data-theme', forced || (media && media.matches ? 'light' : 'dark'));
  }

  apply();

  if (media && !forced) {
    if (media.addEventListener) media.addEventListener('change', apply);
    else if (media.addListener) media.addListener(apply);
  }
})();
