/* Shared staff helpers: appointment request cards + actions (approve / reject / complete / no-show / cancel). */
(function () {
  'use strict';
  var t = App.t, esc = App.esc;

  function act(id, action, body) { return App.post('/appointments/' + id + '/' + action + '/', body || {}); }

  var Staff = {
    approve: function (id) { return act(id, 'approve').then(function (a) { App.toast(t('تم تثبيت الموعد وإشعار المريض', 'Confirmed — patient notified')); return a; }); },
    reject: function (id) {
      return App.confirm(t('رفض طلب الموعد', 'Reject request'), t('اكتب سبباً يصل للمريض (اختياري)', 'Optional reason sent to the patient'),
        { input: 'text', placeholder: t('مثال: الطبيب في إجازة، يرجى اختيار يوم آخر', 'e.g. please choose another day'), danger: true })
        .then(function (note) {
          if (note === false) return null;
          return act(id, 'reject', { note: note }).then(function (a) { App.toast(t('تم رفض الطلب وإشعار المريض', 'Rejected — patient notified'), 'warning'); return a; });
        });
    },
    cancel: function (id) {
      return App.confirm(t('إلغاء الموعد', 'Cancel appointment'), t('سيُبلَّغ المريض بالإلغاء. السبب (اختياري):', 'The patient will be notified. Reason (optional):'), { input: 'text', danger: true })
        .then(function (note) { if (note === false) return null; return act(id, 'cancel', { note: note }).then(function (a) { App.toast(t('تم الإلغاء', 'Cancelled'), 'warning'); return a; }); });
    },
    complete: function (id) { return act(id, 'complete').then(function (a) { App.toast(t('تم تسجيل الموعد كمكتمل', 'Marked as completed')); return a; }); },
    noShow: function (id) { return act(id, 'no-show').then(function (a) { App.toast(t('تم تسجيل عدم الحضور', 'Marked as no-show'), 'warning'); return a; }); },

    triageHtml: function (a) {
      var s = a.triage_summary;
      if (!s) return '';
      var d = s.doctor_summary || {};
      return '<div class="border rounded p-2 mt-2 small bg-lighter"><div class="mb-1"><i class="ti ti-message-chatbot text-info me-1"></i><strong>' + esc(t('ملخص الدليل الصحي', 'Health guide summary')) + '</strong> ' +
        App.urgencyBadge(s.urgency) + '</div>' +
        (d.chief_complaint ? '<div><span class="text-muted">' + esc(t('الشكوى: ', 'Complaint: ')) + '</span>' + esc(d.chief_complaint) + '</div>' : '') +
        (d.answers && d.answers.length ? '<div><span class="text-muted">' + esc(t('الإجابات: ', 'Answers: ')) + '</span>' + esc(d.answers.join(' • ')) + '</div>' : '') +
        (s.possible_conditions && s.possible_conditions.length ? '<div><span class="text-muted">' + esc(t('احتمالات: ', 'Possible: ')) + '</span>' + esc(s.possible_conditions.join('، ')) + '</div>' : '') +
        (s.recommended_tests && s.recommended_tests.length ? '<div><span class="text-muted">' + esc(t('تحاليل مقترحة: ', 'Suggested tests: ')) + '</span>' + esc(s.recommended_tests.join('، ')) + '</div>' : '') + '</div>';
    },

    /** A booking request card with approve / reject buttons. */
    requestCard: function (a, showDoctor) {
      return '<div class="border rounded p-3 mb-3" data-appt="' + a.id + '"><div class="d-flex flex-wrap gap-3 align-items-start">' +
        App.avatar(a.patient_name, 'warning') +
        '<div class="flex-grow-1"><div class="d-flex flex-wrap gap-2 align-items-center"><a class="fw-semibold" href="/staff/patient.html?id=' + a.patient + '">' + esc(a.patient_name) + '</a>' +
        '<span class="badge bg-label-secondary smi-id-number" style="font-size:.7rem">' + esc(a.patient_medical_id || '') + '</span></div>' +
        '<div class="small mt-1"><i class="ti ti-calendar ti-xs me-1 text-primary"></i>' + esc(App.fmtDay(a.start_at)) + ' — <span class="ltr fw-semibold">' + esc(App.fmtTime(a.start_at)) + '</span></div>' +
        (showDoctor ? '<div class="small text-muted"><i class="ti ti-stethoscope ti-xs me-1"></i>' + esc(t('د. ', 'Dr. ') + (a.practitioner_full_name || '')) + '</div>' : '') +
        (a.reason ? '<div class="small mt-1"><span class="text-muted">' + esc(t('السبب: ', 'Reason: ')) + '</span>' + esc(a.reason) + '</div>' : '') +
        '<div class="small text-muted">' + esc(t('طُلب ', 'Requested ') + App.relTime(a.created_at)) + '</div>' + Staff.triageHtml(a) + '</div>' +
        '<div class="d-flex gap-2 align-self-center"><button class="btn btn-success btn-sm" data-act="approve"><i class="ti ti-check me-1"></i>' + esc(t('موافقة', 'Approve')) + '</button>' +
        '<button class="btn btn-label-danger btn-sm" data-act="reject"><i class="ti ti-x me-1"></i>' + esc(t('رفض', 'Reject')) + '</button></div></div></div>';
    },

    /** Bind [data-appt] [data-act] buttons inside a container. */
    bind: function (root, onDone) {
      App.$$('[data-appt] [data-act]', root).forEach(function (b) {
        b.onclick = function () {
          var id = b.closest('[data-appt]').dataset.appt, fn = { approve: Staff.approve, reject: Staff.reject, cancel: Staff.cancel, complete: Staff.complete, 'no-show': Staff.noShow }[b.dataset.act];
          App.busy(b, true);
          fn(id).then(function (r) { if (r && onDone) onDone(r); }).catch(function (e) { App.toast(e.message, 'danger'); }).finally(function () { App.busy(b, false); });
        };
      });
    }
  };
  window.Staff = Staff;
})();
