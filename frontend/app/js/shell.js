/* Builds the shared layout (sidebar, navbar, notifications, bottom nav) around <main id="page">. */
(function () {
  'use strict';
  var page = document.getElementById('page');
  var user = App.user();
  if (!page || !user) return;
  var t = App.t, esc = App.esc, role = user.role;

  var MENUS = {
    Patient: [
      { h: ['هويتي', 'My identity'] },
      { href: '/patient/dashboard.html', icon: 'ti-id-badge-2', t: ['الهوية الطبية', 'Medical ID'], nav: 1 },
      { href: '/patient/record.html', icon: 'ti-clipboard-heart', t: ['سجلي الطبي', 'My record'], nav: 1 },
      { h: ['المواعيد', 'Appointments'] },
      { href: '/patient/doctors.html', icon: 'ti-stethoscope', t: ['دليل الأطباء', 'Find a doctor'], nav: 1 },
      { href: '/patient/appointments.html', icon: 'ti-calendar-event', t: ['مواعيدي', 'My appointments'], nav: 1 },
      { h: ['المساعد الذكي', 'Smart assistant'] },
      { href: '/patient/assistant.html', icon: 'ti-message-chatbot', t: ['الدليل الصحي', 'Health guide'], nav: 1 }
    ],
    Doctor: [
      { href: '/staff/dashboard.html', icon: 'ti-smart-home', t: ['لوحة التحكم', 'Dashboard'], nav: 1 },
      { h: ['المواعيد', 'Appointments'] },
      { href: '/staff/requests.html', icon: 'ti-inbox', t: ['طلبات الحجز', 'Booking requests'], badge: 'pending', nav: 1 },
      { href: '/staff/calendar.html', icon: 'ti-calendar', t: ['التقويم', 'Calendar'], nav: 1 },
      { href: '/staff/availability.html', icon: 'ti-clock-cog', t: ['أوقات الدوام والإعدادات', 'Working hours'] },
      { h: ['المرضى', 'Patients'] },
      { href: '/staff/patients.html', icon: 'ti-users', t: ['المرضى', 'Patients'], nav: 1 }
    ],
    Nurse: [
      { href: '/staff/dashboard.html', icon: 'ti-smart-home', t: ['لوحة التحكم', 'Dashboard'], nav: 1 },
      { h: ['المواعيد', 'Appointments'] },
      { href: '/staff/requests.html', icon: 'ti-inbox', t: ['طلبات الحجز', 'Booking requests'], badge: 'pending', nav: 1 },
      { href: '/staff/calendar.html', icon: 'ti-calendar', t: ['التقويم', 'Calendar'], nav: 1 },
      { h: ['المرضى', 'Patients'] },
      { href: '/staff/patients.html', icon: 'ti-users', t: ['المرضى', 'Patients'], nav: 1 }
    ],
    Admin: [
      { href: '/admin/dashboard.html', icon: 'ti-chart-pie', t: ['لوحة الإدارة', 'Admin dashboard'], nav: 1 },
      { h: ['الإدارة', 'Management'] },
      { href: '/admin/users.html', icon: 'ti-user-cog', t: ['المستخدمون', 'Users'], nav: 1 },
      { href: '/admin/doctors.html', icon: 'ti-stethoscope', t: ['دليل الأطباء', 'Doctors directory'], badge: 'unverified', nav: 1 },
      { href: '/admin/audit.html', icon: 'ti-history', t: ['سجل العمليات', 'Audit log'] },
      { h: ['العمل الطبي', 'Clinical'] },
      { href: '/staff/patients.html', icon: 'ti-users', t: ['المرضى', 'Patients'], nav: 1 },
      { href: '/staff/requests.html', icon: 'ti-inbox', t: ['طلبات الحجز', 'Booking requests'], badge: 'pending' },
      { href: '/staff/calendar.html', icon: 'ti-calendar', t: ['التقويم', 'Calendar'] }
    ]
  };
  var COMMON = [
    { h: ['الحساب', 'Account'] },
    { href: '/notifications.html', icon: 'ti-bell', t: ['الإشعارات', 'Notifications'], badge: 'notif' },
    { href: '/profile.html', icon: 'ti-user-circle', t: ['حسابي والإعدادات', 'Account & settings'] }
  ];
  var items = (MENUS[role] || []).concat(COMMON);
  var here = location.pathname;
  var lbl = function (pair) { return t(pair[0], pair[1]); };

  var menuHtml = items.map(function (it) {
    if (it.h) return '<li class="menu-header small"><span class="menu-header-text">' + esc(lbl(it.h)) + '</span></li>';
    var active = here === it.href ? ' active' : '';
    return '<li class="menu-item' + active + '"><a href="' + it.href + '" class="menu-link"><i class="menu-icon tf-icons ti ' + it.icon + '"></i><div>' +
      esc(lbl(it.t)) + '</div>' + (it.badge ? '<div class="badge bg-danger rounded-pill ms-auto d-none" data-badge="' + it.badge + '"></div>' : '') + '</a></li>';
  }).join('');

  var navItems = items.filter(function (i) { return i.nav; }).slice(0, 4);
  var bottomNav = '<nav class="smi-bottom-nav d-xl-none">' + navItems.map(function (it) {
    return '<a href="' + it.href + '" class="' + (here === it.href ? 'active' : '') + '"><i class="ti ' + it.icon + '"></i><span>' + esc(lbl(it.t)) +
      '</span>' + (it.badge ? '<b class="d-none" data-badge="' + it.badge + '"></b>' : '') + '</a>';
  }).join('') + '<a href="javascript:void(0)" class="layout-menu-toggle"><i class="ti ti-menu-2"></i><span>' + esc(t('المزيد', 'More')) + '</span></a></nav>';

  var title = App.lang() === 'en' && page.dataset.enTitle ? page.dataset.enTitle : (page.dataset.title || '');
  document.title = (title ? title + ' — ' : '') + t('الهوية الطبية الذكية', 'Smart Medical ID');
  var roleLabel = { Patient: t('مريض', 'Patient'), Doctor: t('طبيب', 'Doctor'), Nurse: t('ممرض/ة', 'Nurse'), Admin: t('مشرف', 'Admin') }[role] || '';
  var avatarColor = { Patient: 'primary', Doctor: 'info', Nurse: 'success', Admin: 'warning' }[role] || 'primary';

  var layout = document.createElement('div');
  layout.className = 'layout-wrapper layout-content-navbar';
  layout.innerHTML =
    '<div class="layout-container">' +
    '<aside id="layout-menu" class="layout-menu menu-vertical menu bg-menu-theme">' +
      '<div class="app-brand demo"><a href="' + App.homeFor(role) + '" class="app-brand-link">' +
        '<span class="app-brand-logo demo"><img src="/assets/img/logo.png" alt="" width="34" height="34"></span>' +
        '<span class="app-brand-text demo menu-text fw-bold ms-2">' + esc(t('الهوية الطبية', 'Medical ID')) + '</span></a>' +
        '<a href="javascript:void(0);" class="layout-menu-toggle menu-link text-large ms-auto"><i class="ti menu-toggle-icon d-none d-xl-block align-middle"></i><i class="ti ti-x d-block d-xl-none ti-md align-middle"></i></a></div>' +
      '<div class="menu-inner-shadow"></div><ul class="menu-inner py-1">' + menuHtml + '</ul>' +
    '</aside>' +
    '<div class="layout-page">' +
      '<nav class="layout-navbar container-xxl navbar navbar-expand-xl navbar-detached align-items-center bg-navbar-theme" id="layout-navbar">' +
        '<div class="layout-menu-toggle navbar-nav align-items-xl-center me-3 me-xl-0 d-xl-none"><a class="nav-item nav-link px-0 me-xl-4" href="javascript:void(0)"><i class="ti ti-menu-2 ti-md"></i></a></div>' +
        '<div class="navbar-nav-right d-flex align-items-center" id="navbar-collapse">' +
          '<div class="navbar-nav align-items-center"><h5 class="mb-0 smi-page-title text-truncate">' + esc(title) + '</h5></div>' +
          '<ul class="navbar-nav flex-row align-items-center ms-auto">' +
            '<li class="nav-item me-1"><a class="nav-link btn btn-text-secondary btn-icon rounded-pill" href="javascript:void(0)" id="smi-lang" title="Language"><span class="fw-semibold">' + (App.lang() === 'ar' ? 'EN' : 'ع') + '</span></a></li>' +
            '<li class="nav-item me-1"><a class="nav-link btn btn-text-secondary btn-icon rounded-pill" href="javascript:void(0)" id="smi-theme" title="Theme"><i class="ti ' + (App.isDark() ? 'ti-sun' : 'ti-moon-stars') + ' ti-md"></i></a></li>' +
            '<li class="nav-item dropdown-notifications navbar-dropdown dropdown me-2">' +
              '<a class="nav-link btn btn-text-secondary btn-icon rounded-pill dropdown-toggle hide-arrow" href="javascript:void(0)" data-bs-toggle="dropdown" data-bs-auto-close="outside" id="smi-bell">' +
              '<span class="position-relative"><i class="ti ti-bell ti-md"></i><span class="badge rounded-pill bg-danger badge-dot badge-notifications border d-none" id="smi-bell-dot"></span></span></a>' +
              '<ul class="dropdown-menu dropdown-menu-end p-0 smi-notif-menu">' +
                '<li class="dropdown-menu-header border-bottom"><div class="dropdown-header d-flex align-items-center py-3"><h6 class="mb-0 me-auto">' + esc(t('الإشعارات', 'Notifications')) + '</h6>' +
                '<a href="javascript:void(0)" class="btn btn-text-secondary btn-sm" id="smi-read-all">' + esc(t('تعليم الكل كمقروء', 'Mark all read')) + '</a></div></li>' +
                '<li class="dropdown-notifications-list scrollable-container"><ul class="list-group list-group-flush" id="smi-notif-list"></ul></li>' +
                '<li class="border-top"><div class="d-grid p-3 gap-2"><button class="btn btn-sm btn-label-primary d-none" id="smi-enable-push"><i class="ti ti-bell-ringing me-1"></i>' +
                esc(t('تفعيل الإشعارات على هذا الجهاز', 'Enable notifications on this device')) + '</button>' +
                '<a class="btn btn-primary btn-sm" href="/notifications.html">' + esc(t('عرض كل الإشعارات', 'View all')) + '</a></div></li>' +
              '</ul></li>' +
            '<li class="nav-item navbar-dropdown dropdown-user dropdown">' +
              '<a class="nav-link dropdown-toggle hide-arrow p-0" href="javascript:void(0)" data-bs-toggle="dropdown">' + App.avatar(user.full_name, avatarColor) + '</a>' +
              '<ul class="dropdown-menu dropdown-menu-end">' +
                '<li><div class="dropdown-item mt-0"><div class="d-flex align-items-center"><div class="flex-shrink-0 me-2">' + App.avatar(user.full_name, avatarColor) +
                '</div><div class="flex-grow-1"><h6 class="mb-0">' + esc(user.full_name) + '</h6><small class="text-muted">' + esc(roleLabel) + '</small></div></div></div></li>' +
                '<li><div class="dropdown-divider my-1"></div></li>' +
                '<li><a class="dropdown-item" href="/profile.html"><i class="ti ti-user-circle me-3 ti-md"></i>' + esc(t('حسابي والإعدادات', 'Account & settings')) + '</a></li>' +
                '<li class="d-none" id="smi-install-li"><a class="dropdown-item" href="javascript:void(0)" id="smi-install"><i class="ti ti-device-mobile-down me-3 ti-md"></i>' + esc(t('تثبيت التطبيق', 'Install app')) + '</a></li>' +
                '<li><div class="dropdown-divider my-1"></div></li>' +
                '<li><a class="dropdown-item text-danger" href="javascript:void(0)" id="smi-logout"><i class="ti ti-logout me-3 ti-md"></i>' + esc(t('تسجيل الخروج', 'Log out')) + '</a></li>' +
              '</ul></li>' +
          '</ul></div></nav>' +
      '<div class="content-wrapper"><div class="container-xxl flex-grow-1 container-p-y" id="smi-content"></div>' +
        '<footer class="content-footer footer bg-footer-theme"><div class="container-xxl"><div class="footer-container d-flex align-items-center justify-content-between py-3 flex-md-row flex-column">' +
        '<div class="text-body small">© ' + new Date().getFullYear() + ' ' + esc(t('الهوية الطبية الذكية', 'Smart Medical ID')) + '</div>' +
        '<div class="small text-muted">' + esc(t('بياناتك الطبية محمية', 'Your medical data is protected')) + ' <i class="ti ti-shield-lock ti-xs"></i></div></div></div></footer>' +
        '<div class="content-backdrop fade"></div></div>' +
    '</div></div>' +
    '<div class="layout-overlay layout-menu-toggle"></div><div class="drag-target"></div>' + bottomNav;

  page.parentNode.insertBefore(layout, page);
  layout.querySelector('#smi-content').appendChild(page);
  page.classList.add('smi-page');
  App.applyI18n(page);

  // Vuexy boot
  var menuEl = document.getElementById('layout-menu');
  if (window.Menu) {
    window.Helpers.mainMenu = new Menu(menuEl, { orientation: 'vertical', closeChildren: false });
    window.Helpers.scrollToActive(false);
  }
  App.$$('.layout-menu-toggle').forEach(function (el) {
    el.addEventListener('click', function (e) { e.preventDefault(); window.Helpers.toggleCollapsed(); });
  });
  if (window.Hammer) {
    window.Helpers.swipeIn('.drag-target', function () { window.Helpers.setCollapsed(false); });
    window.Helpers.swipeOut('#layout-menu', function () { if (window.Helpers.isSmallScreen()) window.Helpers.setCollapsed(true); });
  }
  if (window.Waves) { Waves.init(); Waves.attach(".btn[class*='btn-']:not([class*='btn-outline-']):not([class*='btn-label-'])", ['waves-light']); Waves.attach("[class*='btn-outline-'],[class*='btn-label-']"); }
  window.Helpers.setAutoUpdate(true);
  window.Helpers.initPasswordToggle && window.Helpers.initPasswordToggle();
  window.Helpers.initNavbarDropdownScrollbar && window.Helpers.initNavbarDropdownScrollbar();
  App.$$('[data-bs-toggle="tooltip"]').forEach(function (el) { new bootstrap.Tooltip(el); });

  // navbar actions
  App.$('#smi-lang').onclick = function () { App.setLang(App.lang() === 'ar' ? 'en' : 'ar'); };
  App.$('#smi-theme').onclick = function () { App.setTheme(App.isDark() ? 'light' : 'dark'); };
  App.$('#smi-logout').onclick = function () { App.logout(); };
  var showInstall = function () { App.$('#smi-install-li').classList.remove('d-none'); };
  if (App.installPrompt) showInstall();
  document.addEventListener('smi:installable', showInstall);
  App.$('#smi-install').onclick = function () { if (App.installPrompt) { App.installPrompt.prompt(); App.installPrompt = null; App.$('#smi-install-li').classList.add('d-none'); } };

  // notifications
  var ICON = { APPOINTMENT_REQUEST: ['ti-calendar-plus', 'warning'], APPOINTMENT_CONFIRMED: ['ti-calendar-check', 'success'],
    APPOINTMENT_REJECTED: ['ti-calendar-x', 'danger'], APPOINTMENT_CANCELLED: ['ti-calendar-minus', 'secondary'],
    APPOINTMENT_REMINDER: ['ti-alarm', 'info'], DOCTOR_VERIFICATION: ['ti-rosette-discount-check', 'primary'], SYSTEM: ['ti-bell', 'primary'] };
  App.notifIcon = function (kind) { return ICON[kind] || ICON.SYSTEM; };
  var lastId = Number(sessionStorage.getItem('smi_last_notif') || 0);

  function setBadges(count, extra) {
    App.$$('[data-badge="notif"]').forEach(function (b) { b.textContent = count; b.classList.toggle('d-none', !count); });
    App.$('#smi-bell-dot').classList.toggle('d-none', !count);
    Object.keys(extra || {}).forEach(function (k) {
      App.$$('[data-badge="' + k + '"]').forEach(function (b) { b.textContent = extra[k]; b.classList.toggle('d-none', !extra[k]); });
    });
  }
  App.setMenuBadge = function (key, n) { var o = {}; o[key] = n; setBadges(Number(App.$('[data-badge="notif"]') && App.$('[data-badge="notif"]').textContent || 0), o); };

  function poll(first) {
    if (document.hidden && !first) return;
    App.get('/notifications/unread-count/').then(function (r) {
      setBadges(r.count);
      if (!first && r.latest_id > lastId && r.count) {
        App.get('/notifications/', { unread: 1, page_size: 1 }).then(function (d) {
          var n = d.results[0]; if (!n) return;
          App.toast(n.body, 'info', n.title);
          document.dispatchEvent(new CustomEvent('smi:notification', { detail: n }));
        });
      }
      lastId = r.latest_id; sessionStorage.setItem('smi_last_notif', lastId);
    }).catch(function () {});
  }
  poll(true);
  setInterval(poll, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('message', function (e) { if (e.data && e.data.type === 'push') poll(); });

  App.$('#smi-bell').addEventListener('show.bs.dropdown', function () {
    var list = App.$('#smi-notif-list');
    list.innerHTML = '<li class="list-group-item text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></li>';
    App.get('/notifications/', { page_size: 8 }).then(function (d) {
      if (!d.results.length) { list.innerHTML = '<li class="list-group-item text-center text-muted py-4">' + esc(t('لا توجد إشعارات', 'No notifications')) + '</li>'; return; }
      list.innerHTML = d.results.map(function (n) {
        var ic = App.notifIcon(n.kind);
        return '<li class="list-group-item list-group-item-action dropdown-notifications-item ' + (n.is_read ? 'marked-as-read' : '') + '" data-id="' + n.id + '" data-link="' + esc(n.link) + '">' +
          '<div class="d-flex"><div class="flex-shrink-0 me-3"><div class="avatar"><span class="avatar-initial rounded-circle bg-label-' + ic[1] + '"><i class="ti ' + ic[0] + '"></i></span></div></div>' +
          '<div class="flex-grow-1"><h6 class="mb-1 small">' + esc(n.title) + '</h6><small class="mb-1 d-block text-body">' + esc(n.body) + '</small><small class="text-muted">' + esc(App.relTime(n.created_at)) + '</small></div>' +
          (n.is_read ? '' : '<div class="flex-shrink-0"><span class="badge badge-dot bg-primary"></span></div>') + '</div></li>';
      }).join('');
      App.$$('li[data-id]', list).forEach(function (li) {
        li.onclick = function () { App.post('/notifications/' + li.dataset.id + '/read/').finally(function () { if (li.dataset.link) location.href = li.dataset.link; else poll(true); }); };
      });
    });
    App.pushState().then(function (s) { App.$('#smi-enable-push').classList.toggle('d-none', s !== 'off'); });
  });
  App.$('#smi-read-all').onclick = function () { App.post('/notifications/read-all/').then(function () { poll(true); App.$$('#smi-notif-list .badge-dot').forEach(function (b) { b.remove(); }); }); };
  App.$('#smi-enable-push').onclick = function () {
    var b = this; App.busy(b, true);
    App.enablePush().then(function () { App.toast(t('تم تفعيل الإشعارات على هذا الجهاز', 'Notifications enabled')); b.classList.add('d-none'); })
      .catch(function (e) { App.toast(e.message, 'danger'); }).finally(function () { App.busy(b, false); });
  };

  // menu counters (pending requests / unverified doctors)
  if (role === 'Doctor' || role === 'Nurse' || role === 'Admin') {
    App.get('/appointments/', { status: 'PENDING', when: 'upcoming', page_size: 1 }).then(function (d) { App.setMenuBadge('pending', d.count); }).catch(function () {});
  }
  if (role === 'Admin') {
    App.get('/doctors/', { all: 1, verified: 0, page_size: 1 }).then(function (d) { App.setMenuBadge('unverified', d.count); }).catch(function () {});
  }
  // keep identity fresh (e.g. a doctor just got verified)
  App.get('/whoami/').then(function (me) {
    var old = App.user();
    App.setSession({ user: me });
    if (old && old.role !== me.role) location.replace(App.homeFor(me.role));
  }).catch(function () {});
})();
