// 사이트 통합 버전 (단일 소스). 릴리스 시 이 값만 변경.
// 외부 footer.js가 그리는 푸터 마지막 줄(.footer-credits)에 이어 붙인다.
(function () {
  var VERSION = 'v0.7.0';

  function inject() {
    if (document.querySelector('.site-version')) return true;
    var credits = document.querySelector('#footer .footer-credits');
    if (!credits) return false;
    var sep = document.createElement('span');
    sep.className = 'footer-sep';
    sep.textContent = ' · ';
    var v = document.createElement('span');
    v.className = 'site-version';
    v.textContent = VERSION;
    credits.appendChild(sep);
    credits.appendChild(v);
    return true;
  }

  // footer.js가 비동기로 푸터를 그리므로 잠깐 재시도
  var tries = 0;
  var timer = setInterval(function () {
    if (inject() || ++tries > 40) clearInterval(timer);
  }, 100);
})();
