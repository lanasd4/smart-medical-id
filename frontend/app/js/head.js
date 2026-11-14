/* Runs before first paint: language/direction, theme stylesheets, PWA tags and the role guard. */
(function () {
  var d = document.documentElement, ls = window.localStorage;
  var lang = ls.getItem('smi_lang') || 'ar';
  var theme = ls.getItem('smi_theme') || 'light';
  var dark = theme === 'dark' || (theme === 'system' && window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
  d.lang = lang;
  d.dir = lang === 'ar' ? 'rtl' : 'ltr';
  d.classList.remove('light-style', 'dark-style');
  d.classList.add(dark ? 'dark-style' : 'light-style');
  d.setAttribute('data-theme', 'theme-default');
  d.setAttribute('data-assets-path', '/assets/');

  var V = '?v=13';
  var css = [
    '/assets/vendor/fonts/tabler-icons.css',
    '/assets/vendor/css/rtl/core' + (dark ? '-dark' : '') + '.css',
    '/assets/vendor/css/rtl/theme-default' + (dark ? '-dark' : '') + '.css',
    '/assets/vendor/libs/perfect-scrollbar/perfect-scrollbar.css',
    '/assets/vendor/libs/node-waves/node-waves.css'
  ];
  (d.getAttribute('data-css') || '').split(',').forEach(function (x) { x = x.trim(); if (x) css.push('/assets/vendor/libs/' + x + '/' + x + '.css'); });
  css.push('/app/css/app.css');
  var html = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Public+Sans:wght@400;500;600;700&display=swap">';
  css.forEach(function (h) { html += '<link rel="stylesheet" href="' + h + V + '">'; });
  html += '<link rel="manifest" href="/manifest.webmanifest">' +
    '<meta name="theme-color" content="' + (dark ? '#25293c' : '#0B7F7B') + '">' +
    '<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes">' +
    '<meta name="apple-mobile-web-app-title" content="الهوية الطبية"><meta name="apple-mobile-web-app-status-bar-style" content="default">' +
    '<link rel="icon" type="image/png" href="/app/icons/icon-192.png"><link rel="apple-touch-icon" href="/app/icons/apple-touch-icon.png">';
  document.write(html);

  window.SMI_BOOT = { lang: lang, theme: theme, dark: dark, v: V };

  // role guard
  var roles = d.getAttribute('data-roles');
  if (!roles) return;
  var user = null;
  try { user = JSON.parse(ls.getItem('smi_user') || 'null'); } catch (e) { user = null; }
  if (!ls.getItem('smi_refresh') || !user) {
    location.replace('/login.html?next=' + encodeURIComponent(location.pathname + location.search));
    return;
  }
  if (roles !== '*' && roles.split(',').indexOf(user.role) < 0) {
    var home = { Patient: '/patient/dashboard.html', Doctor: '/staff/dashboard.html', Nurse: '/staff/dashboard.html',
                 Admin: '/admin/dashboard.html', PendingDoctor: '/pending.html' }[user.role] || '/login.html';
    location.replace(home);
  }
})();
