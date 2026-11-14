/* Client core: API client with token refresh, i18n, formatting, dialogs, PWA/push helpers. */
(function (w) {
  'use strict';
  var ls = w.localStorage;

  var App = {
    version: '1.0.0',
    colors: { primary: '#0B7F7B', navy: '#1E3A5F', success: '#28c76f', warning: '#ff9f43', danger: '#ff4c51', info: '#00bad1', secondary: '#808390' }
  };

  // session
  App.user = function () { try { return JSON.parse(ls.getItem('smi_user') || 'null'); } catch (e) { return null; } };
  App.role = function () { var u = App.user(); return u ? u.role : null; };
  App.setSession = function (data) {
    if (data.access) ls.setItem('smi_access', data.access);
    if (data.refresh) ls.setItem('smi_refresh', data.refresh);
    if (data.user) ls.setItem('smi_user', JSON.stringify(data.user));
  };
  App.clearSession = function () { ['smi_access', 'smi_refresh', 'smi_user'].forEach(function (k) { ls.removeItem(k); }); };
  App.logout = function () {
    App.unsubscribePush().finally(function () { App.clearSession(); location.href = '/login.html'; });
  };
  App.homeFor = function (role) {
    return { Patient: '/patient/dashboard.html', Doctor: '/staff/dashboard.html', Nurse: '/staff/dashboard.html',
             Admin: '/admin/dashboard.html', PendingDoctor: '/pending.html' }[role] || '/login.html';
  };

  // API
  function ApiError(message, status, data) { this.message = message; this.status = status; this.data = data; }
  ApiError.prototype = Object.create(Error.prototype);
  App.ApiError = ApiError;

  var refreshing = null;
  function refreshToken() {
    if (!refreshing) {
      refreshing = fetch('/api/token/refresh/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: ls.getItem('smi_refresh') })
      }).then(function (r) {
        if (!r.ok) throw new Error('refresh failed');
        return r.json();
      }).then(function (d) { ls.setItem('smi_access', d.access); if (d.refresh) ls.setItem('smi_refresh', d.refresh); return d.access; })
        .finally(function () { setTimeout(function () { refreshing = null; }, 0); });
    }
    return refreshing;
  }

  function errorMessage(data, status) {
    if (!data) return status === 0 ? App.t('تعذّر الاتصال بالخادم', 'Cannot reach the server') : App.t('حدث خطأ غير متوقع', 'Unexpected error') + ' (' + status + ')';
    if (typeof data === 'string') return data;
    if (data.detail) return Array.isArray(data.detail) ? data.detail.join('، ') : String(data.detail);
    var parts = [];
    Object.keys(data).forEach(function (k) {
      if (k === 'code') return;
      var v = data[k];
      parts.push(Array.isArray(v) ? v.join('، ') : (typeof v === 'object' ? errorMessage(v) : String(v)));
    });
    return parts.join(' — ') || App.t('حدث خطأ', 'Error');
  }

  /**
   * App.api('/patients/', {method:'POST', body:{...}})  -> parsed JSON
   * options: method, body (object|FormData), params (object), raw (return Response), auth (default true)
   */
  App.api = function (path, opts) {
    opts = opts || {};
    var url = path.indexOf('/api/') === 0 ? path : '/api' + (path[0] === '/' ? '' : '/') + path;
    if (opts.params) {
      var q = Object.keys(opts.params).filter(function (k) { return opts.params[k] !== undefined && opts.params[k] !== null && opts.params[k] !== ''; })
        .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(opts.params[k]); }).join('&');
      if (q) url += (url.indexOf('?') >= 0 ? '&' : '?') + q;
    }
    function doFetch(token) {
      var headers = { 'Accept': 'application/json', 'Accept-Language': App.lang() };
      var body = opts.body;
      if (body && !(body instanceof FormData)) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
      if (token && opts.auth !== false) headers.Authorization = 'Bearer ' + token;
      return fetch(url, { method: opts.method || (body ? 'POST' : 'GET'), headers: headers, body: body });
    }
    return doFetch(ls.getItem('smi_access')).then(function (r) {
      if (r.status === 401 && opts.auth !== false && ls.getItem('smi_refresh')) {
        return refreshToken().then(doFetch, function () {
          App.clearSession();
          location.href = '/login.html?next=' + encodeURIComponent(location.pathname + location.search);
          throw new ApiError(App.t('انتهت الجلسة', 'Session expired'), 401);
        });
      }
      return r;
    }).then(function (r) {
      if (opts.raw) return r;
      if (r.status === 204) return null;
      var ct = r.headers.get('content-type') || '';
      var p = ct.indexOf('json') >= 0 ? r.json() : r.text();
      return p.then(function (data) {
        if (!r.ok) throw new ApiError(errorMessage(data, r.status), r.status, data);
        return data;
      });
    }, function (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(errorMessage(null, 0), 0);
    });
  };
  App.get = function (p, params) { return App.api(p, { params: params }); };
  App.post = function (p, body) { return App.api(p, { method: 'POST', body: body || {} }); };
  App.patch = function (p, body) { return App.api(p, { method: 'PATCH', body: body }); };
  App.put = function (p, body) { return App.api(p, { method: 'PUT', body: body }); };
  App.del = function (p) { return App.api(p, { method: 'DELETE' }); };
  /** fetch every page of a paginated list */
  App.all = function (p, params) {
    params = Object.assign({ page_size: 200 }, params || {});
    return App.get(p, params).then(function (d) { return Array.isArray(d) ? d : d.results; });
  };

  App.meta = function () {
    var cached = sessionStorage.getItem('smi_meta');
    if (cached) return Promise.resolve(JSON.parse(cached));
    return App.api('/meta/', { auth: false }).then(function (m) { sessionStorage.setItem('smi_meta', JSON.stringify(m)); return m; });
  };

  // i18n
  App.lang = function () { return ls.getItem('smi_lang') || 'ar'; };
  App.t = function (ar, en) { return App.lang() === 'en' && en ? en : ar; };
  App.setLang = function (l) { ls.setItem('smi_lang', l); location.reload(); };
  /** Elements with data-en="..." show English when lang=en. Inputs: data-en-ph for placeholder. */
  App.applyI18n = function (root) {
    if (App.lang() !== 'en') return;
    (root || document).querySelectorAll('[data-en]').forEach(function (el) { el.textContent = el.getAttribute('data-en'); });
    (root || document).querySelectorAll('[data-en-ph]').forEach(function (el) { el.placeholder = el.getAttribute('data-en-ph'); });
    (root || document).querySelectorAll('[data-en-title]').forEach(function (el) { el.title = el.getAttribute('data-en-title'); });
  };
  App.setTheme = function (t) { ls.setItem('smi_theme', t); location.reload(); };
  App.isDark = function () { return document.documentElement.classList.contains('dark-style'); };

  // formatting
  var locale = function () { return App.lang() === 'ar' ? 'ar-SY-u-nu-latn' : 'en-GB'; };
  App.fmtDate = function (v, o) { if (!v) return '—'; var d = new Date(v); return isNaN(d) ? v : d.toLocaleDateString(locale(), o || { year: 'numeric', month: 'short', day: 'numeric' }); };
  var BIDI = /[‎‏؜]/g;  // invisible direction marks would flip "09:00 - 09:30" inside LTR spans
  App.fmtTime = function (v) { if (!v) return ''; return new Date(v).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).replace(BIDI, ''); };
  App.fmtDateTime = function (v) { if (!v) return '—'; return App.fmtDate(v, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' }) + ' — ' + App.fmtTime(v); };
  App.fmtDay = function (v) { return new Date(v).toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long' }); };
  App.relTime = function (v) {
    var s = (Date.now() - new Date(v).getTime()) / 1000, rtf = new Intl.RelativeTimeFormat(App.lang(), { numeric: 'auto' });
    if (Math.abs(s) < 60) return rtf.format(-Math.round(s), 'second');
    if (Math.abs(s) < 3600) return rtf.format(-Math.round(s / 60), 'minute');
    if (Math.abs(s) < 86400) return rtf.format(-Math.round(s / 3600), 'hour');
    return rtf.format(-Math.round(s / 86400), 'day');
  };
  App.isoDate = function (d) { d = d || new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  App.WEEKDAYS = function () {  // python weekday order: 0=Monday
    return App.lang() === 'ar' ? ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
      : ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  };
  App.fileSize = function (b) { if (!b && b !== 0) return ''; return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; };
  App.initials = function (name) { return (name || '?').replace(/^د\.\s*/, '').trim().split(/\s+/).slice(0, 2).map(function (p) { return p[0]; }).join(''); };

  // html helpers
  App.esc = function (s) {
    return String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  App.$ = function (sel, root) { return (root || document).querySelector(sel); };
  App.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  App.qs = function (name) { return new URLSearchParams(location.search).get(name); };
  App.debounce = function (fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms || 300); }; };
  App.spinner = function (el) { if (el) el.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div></div>'; };
  App.empty = function (el, msg, icon) {
    if (el) el.innerHTML = '<div class="smi-empty"><i class="ti ' + (icon || 'ti-mood-empty') + '"></i><p class="mb-0">' + App.esc(msg || App.t('لا توجد بيانات', 'Nothing here yet')) + '</p></div>';
  };
  App.errorBox = function (el, err) {
    if (el) el.innerHTML = '<div class="alert alert-danger d-flex align-items-center gap-2 mb-0"><i class="ti ti-alert-triangle"></i><span>' + App.esc(err && err.message || err) + '</span></div>';
  };
  App.formData = function (form) {
    var out = {};
    new FormData(form).forEach(function (v, k) { out[k] = typeof v === 'string' ? v.trim() : v; });
    App.$$('input[type=checkbox][name]', form).forEach(function (c) { out[c.name] = c.checked; });
    return out;
  };
  App.fillForm = function (form, data) {
    Object.keys(data || {}).forEach(function (k) {
      var el = form.elements[k]; if (!el) return;
      if (el.type === 'checkbox') el.checked = !!data[k]; else el.value = data[k] === null || data[k] === undefined ? '' : data[k];
    });
  };
  /** Show field errors returned by DRF under each input. */
  App.formErrors = function (form, err) {
    App.$$('.is-invalid', form).forEach(function (el) { el.classList.remove('is-invalid'); });
    App.$$('.invalid-feedback.smi', form).forEach(function (el) { el.remove(); });
    var data = err && err.data;
    var shown = false;
    if (data && typeof data === 'object') {
      Object.keys(data).forEach(function (k) {
        var el = form.elements[k];
        if (el && el.classList) {
          el.classList.add('is-invalid');
          var fb = document.createElement('div');
          fb.className = 'invalid-feedback smi';
          fb.textContent = [].concat(data[k]).join('، ');
          (el.closest('.input-group') || el).insertAdjacentElement('afterend', fb);
          shown = true;
        }
      });
    }
    if (!shown) App.toast(err && err.message || String(err), 'danger');
  };
  App.busy = function (btn, on) {
    if (!btn) return;
    if (on) { btn.dataset.html = btn.innerHTML; btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
    else { btn.disabled = false; if (btn.dataset.html) btn.innerHTML = btn.dataset.html; }
  };

  // toasts & dialogs
  App.toast = function (msg, type, title) {
    var box = document.getElementById('smi-toasts');
    if (!box) { box = document.createElement('div'); box.id = 'smi-toasts'; box.className = 'toast-container position-fixed top-0 end-0 p-3'; document.body.appendChild(box); }
    var icon = { success: 'ti-circle-check', danger: 'ti-alert-circle', warning: 'ti-alert-triangle', info: 'ti-bell' }[type || 'success'];
    var el = document.createElement('div');
    el.className = 'bs-toast toast fade show smi-toast';
    el.setAttribute('role', 'alert');
    el.innerHTML = '<div class="toast-header"><i class="ti ' + icon + ' text-' + (type || 'success') + ' me-2"></i><div class="me-auto fw-medium">' +
      App.esc(title || App.t('الهوية الطبية', 'Medical ID')) + '</div><button type="button" class="btn-close" data-bs-dismiss="toast"></button></div><div class="toast-body">' + App.esc(msg) + '</div>';
    box.appendChild(el);
    var close = function () { el.classList.remove('show'); setTimeout(function () { el.remove(); }, 300); };
    el.querySelector('.btn-close').onclick = close;
    setTimeout(close, type === 'danger' ? 7000 : 4500);
  };
  var swalBase = function () {
    return { customClass: { confirmButton: 'btn btn-primary me-2', cancelButton: 'btn btn-label-secondary', denyButton: 'btn btn-label-danger me-2' },
             buttonsStyling: false, confirmButtonText: App.t('تأكيد', 'Confirm'), cancelButtonText: App.t('إلغاء', 'Cancel') };
  };
  /** App.confirm(title, text, {danger, input:'text', placeholder}) -> Promise<false | true | inputValue> */
  App.confirm = function (title, text, o) {
    o = o || {};
    if (w.Swal) {
      return Swal.fire(Object.assign(swalBase(), {
        title: title, text: text, icon: o.icon || (o.danger ? 'warning' : 'question'), showCancelButton: true,
        input: o.input, inputPlaceholder: o.placeholder, inputValue: o.value || '',
        customClass: { confirmButton: 'btn ' + (o.danger ? 'btn-danger' : 'btn-primary') + ' me-2', cancelButton: 'btn btn-label-secondary' }
      })).then(function (r) { return r.isConfirmed ? (o.input ? (r.value || '') : true) : false; });
    }
    if (o.input) { var v = w.prompt(title + '\n' + (text || ''), o.value || ''); return Promise.resolve(v === null ? false : v); }
    return Promise.resolve(w.confirm(title + '\n' + (text || '')));
  };
  App.alert = function (title, text, icon) {
    if (w.Swal) return Swal.fire(Object.assign(swalBase(), { title: title, text: text, icon: icon || 'success' }));
    w.alert(title + '\n' + (text || '')); return Promise.resolve();
  };

  // domain helpers
  var STATUS = {
    PENDING: ['warning', 'بانتظار الموافقة', 'Pending approval', 'ti-hourglass'],
    CONFIRMED: ['success', 'مؤكد', 'Confirmed', 'ti-circle-check'],
    REJECTED: ['danger', 'مرفوض', 'Rejected', 'ti-circle-x'],
    CANCELLED: ['secondary', 'ملغى', 'Cancelled', 'ti-ban'],
    COMPLETED: ['info', 'مكتمل', 'Completed', 'ti-checks'],
    NO_SHOW: ['dark', 'لم يحضر', 'No show', 'ti-user-off']
  };
  App.statusColor = function (s) { return (STATUS[s] || ['secondary'])[0]; };
  App.statusLabel = function (s) { var x = STATUS[s]; return x ? App.t(x[1], x[2]) : s; };
  App.statusBadge = function (s) {
    var x = STATUS[s] || ['secondary', s, s, 'ti-point'];
    return '<span class="badge bg-label-' + x[0] + '"><i class="ti ' + x[3] + ' ti-xs me-1"></i>' + App.esc(App.t(x[1], x[2])) + '</span>';
  };
  var URG = { er: ['danger', 'طارئ — إسعاف فوراً', 'Emergency'], urgent: ['warning', 'عاجل خلال 24 ساعة', 'Urgent (24h)'],
              soon: ['info', 'خلال أيام', 'Within days'], routine: ['success', 'موعد عادي', 'Routine'] };
  App.urgencyBadge = function (u) { var x = URG[u] || URG.soon; return '<span class="badge bg-' + x[0] + '">' + App.esc(App.t(x[1], x[2])) + '</span>'; };
  App.avatar = function (name, color, size) {
    return '<div class="avatar ' + (size || '') + '"><span class="avatar-initial rounded-circle bg-label-' + (color || 'primary') + '">' + App.esc(App.initials(name)) + '</span></div>';
  };

  /** Open a medical document with the auth header (documents are never public URLs). */
  App.openDocument = function (doc) {
    var win = w.open('', '_blank');
    if (win) win.document.write('<p style="font-family:sans-serif;padding:2rem">' + App.t('جارٍ فتح الملف…', 'Opening…') + '</p>');
    return App.api(doc.view_url, { raw: true }).then(function (r) {
      if (!r.ok) throw new ApiError(App.t('تعذّر فتح الملف', 'Could not open file'), r.status);
      return r.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      if (win) win.location.href = url; else w.location.href = url;
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }).catch(function (e) { if (win) win.close(); App.toast(e.message, 'danger'); });
  };

  // PWA: service worker + push
  App.registerSW = function () {
    if (!('serviceWorker' in navigator)) return Promise.resolve(null);
    return navigator.serviceWorker.register('/sw.js').catch(function () { return null; });
  };
  function urlB64ToUint8Array(base64) {
    var padding = '='.repeat((4 - base64.length % 4) % 4);
    var raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from(Array.prototype.map.call(raw, function (c) { return c.charCodeAt(0); }));
  }
  App.pushSupported = function () { return 'serviceWorker' in navigator && 'PushManager' in w && 'Notification' in w; };
  App.pushState = function () {
    if (!App.pushSupported()) return Promise.resolve('unsupported');
    if (Notification.permission === 'denied') return Promise.resolve('denied');
    return navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); })
      .then(function (s) { return s ? 'on' : 'off'; });
  };
  App.enablePush = function () {
    if (!App.pushSupported()) return Promise.reject(new ApiError(App.t('المتصفح لا يدعم الإشعارات', 'Notifications not supported'), 0));
    return Notification.requestPermission().then(function (perm) {
      if (perm !== 'granted') throw new ApiError(App.t('لم يتم السماح بالإشعارات من المتصفح', 'Permission denied'), 0);
      return Promise.all([navigator.serviceWorker.ready, App.api('/push/public-key/', { auth: false })]);
    }).then(function (res) {
      var reg = res[0], key = res[1].public_key;
      return reg.pushManager.getSubscription().then(function (s) {
        return s || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(key) });
      });
    }).then(function (sub) { return App.post('/push/subscribe/', sub.toJSON()); });
  };
  App.unsubscribePush = function () {
    if (!App.pushSupported() || !navigator.serviceWorker.controller) return Promise.resolve();
    return navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (s) {
      if (!s) return;
      return App.api('/push/subscribe/', { method: 'DELETE', body: { endpoint: s.endpoint } }).catch(function () {}).then(function () { return s.unsubscribe(); });
    }).catch(function () {});
  };

  // install prompt (Android / desktop Chrome)
  App.installPrompt = null;
  w.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); App.installPrompt = e;
    document.dispatchEvent(new CustomEvent('smi:installable'));
  });

  w.App = App;
  App.registerSW();
})(window);
