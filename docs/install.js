(function () {
    const link = document.getElementById('install-link');
    const hint = document.getElementById('install-hint');
    if (!link || !hint) return;

    const standalone = window.matchMedia('(display-mode: standalone)').matches
        || navigator.standalone === true;
    if (standalone) return;

    const ua = navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(ua)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const inApp = /KAKAOTALK|NAVER\(inapp|DaumApps|Instagram|FBAN|FBAV|FB_IAB|Line\/|Twitter|Threads|everytimeApp/i.test(ua);

    let deferred = null;

    function setVisible(on) {
        link.hidden = !on;
        if (!on) hint.hidden = true;
    }

    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferred = e;
        setVisible(true);
    });

    window.addEventListener('appinstalled', () => {
        deferred = null;
        setVisible(false);
    });

    if (isIOS && !inApp) setVisible(true);

    link.addEventListener('click', (e) => {
        e.preventDefault();
        if (deferred) {
            const prompt = deferred;
            deferred = null;
            setVisible(false);
            prompt.prompt();
        } else if (isIOS) {
            hint.hidden = !hint.hidden;
        }
    });
})();
