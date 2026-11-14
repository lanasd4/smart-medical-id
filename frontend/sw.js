/* Service worker: network-first pages, cached static assets, API never cached, Web Push. Bump VERSION on deploy. */
const VERSION = 'smi-v14';
const SHELL = [
  '/offline.html',
  '/login.html',
  '/manifest.webmanifest',
  '/app/css/app.css?v=13',
  '/app/js/head.js',
  '/app/js/core.js',
  '/app/js/shell.js',
  '/assets/vendor/js/helpers.js',
  '/assets/vendor/core.bundle.js',
  '/assets/vendor/fonts/tabler-icons.css?v=13',
  '/assets/vendor/css/rtl/core.css?v=13',
  '/assets/vendor/css/rtl/theme-default.css?v=13',
  '/assets/vendor/libs/perfect-scrollbar/perfect-scrollbar.css?v=13',
  '/assets/vendor/libs/node-waves/node-waves.css?v=13',
  '/assets/img/logo.png',
  '/app/icons/icon-192.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === location.origin && (url.pathname.startsWith('/api/') || url.pathname.startsWith('/django-admin/'))) {
    return; // network only, never cached
  }

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then(res => {
        const copy = res.clone();
        caches.open(VERSION).then(c => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('/offline.html')))
    );
    return;
  }

  const cacheable = (url.origin === location.origin && (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/app/')))
    || url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (!cacheable) return;

  event.respondWith(
    caches.open(VERSION).then(cache => cache.match(req).then(hit => {
      const network = fetch(req).then(res => {
        if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
        return res;
      }).catch(() => hit);
      return hit || network;
    }))
  );
});

// web push
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: 'الهوية الطبية', body: event.data && event.data.text() }; }
  const title = data.title || 'الهوية الطبية الذكية';
  event.waitUntil(Promise.all([
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/app/icons/icon-192.png',
      badge: '/app/icons/badge-96.png',
      dir: 'rtl',
      lang: 'ar',
      tag: data.kind || 'smi',
      renotify: true,
      data: { url: data.url || '/' },
    }),
    self.clients.matchAll({ type: 'window' }).then(list => list.forEach(c => c.postMessage({ type: 'push', data }))),
  ]));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data && event.notification.data.url || '/', location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) {
      if (c.url === target && 'focus' in c) return c.focus();
    }
    if (list.length && 'navigate' in list[0]) return list[0].navigate(target).then(c => c && c.focus());
    return self.clients.openWindow(target);
  }));
});
