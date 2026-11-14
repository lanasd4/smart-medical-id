/* Medical record view shared by the patient and staff pages. */
(function () {
  'use strict';
  var t = App.t, esc = App.esc;

  function section(id, icon, title, count, body, addBtn) {
    return '<div class="card mb-4" id="sec-' + id + '"><div class="card-header d-flex align-items-center justify-content-between">' +
      '<h5 class="card-title mb-0 smi-section-title"><i class="ti ' + icon + '"></i>' + esc(title) +
      ' <span class="badge bg-label-secondary rounded-pill">' + count + '</span></h5>' + (addBtn || '') + '</div>' +
      '<div class="card-body pt-0">' + body + '</div></div>';
  }
  function addBtn(o, kind) {
    return o.editable ? '<button class="btn btn-sm btn-label-primary" data-add="' + kind + '"><i class="ti ti-plus me-1"></i>' + esc(t('إضافة', 'Add')) + '</button>' : '';
  }
  function delBtn(o, kind, id) {
    return o.editable && o.canDelete && o.canDelete(kind) ? '<button class="btn btn-sm btn-icon btn-text-danger" data-del="' + kind + '" data-id="' + id + '" title="' + esc(t('حذف', 'Delete')) + '"><i class="ti ti-trash"></i></button>' : '';
  }
  function by(name) { return name ? '<small class="text-muted d-block">' + esc(t('بواسطة ', 'by ') + name) + '</small>' : ''; }
  function none(msg) { return '<p class="text-muted mb-0">' + esc(msg) + '</p>'; }

  var DOC_TYPES = { LAB: ['تحليل مخبري', 'Lab result', 'ti-microscope', 'info'], RADIOLOGY: ['صورة أشعة', 'Imaging', 'ti-radioactive', 'warning'],
    REPORT: ['تقرير طبي', 'Medical report', 'ti-report-medical', 'primary'], PRESCRIPTION: ['وصفة', 'Prescription', 'ti-prescription', 'success'],
    OTHER: ['ملف', 'File', 'ti-file', 'secondary'] };
  function docType(code) { return DOC_TYPES[(code || 'OTHER').toUpperCase()] || DOC_TYPES.OTHER; }

  window.RecordView = {
    DOC_TYPES: DOC_TYPES,
    render: function (el, r, o) {
      o = o || {};
      var p = r.patient, html = '';

      // identity
      html += '<div class="card mb-4"><div class="card-body"><div class="d-flex flex-wrap align-items-center gap-3">' +
        App.avatar(p.name, 'primary', 'avatar-lg') +
        '<div class="flex-grow-1"><h5 class="mb-1">' + esc(p.name) + '</h5><span class="badge bg-label-primary smi-id-number" style="font-size:.85rem">' + esc(p.medical_id || '') + '</span></div>' +
        '<div class="text-center px-3"><div class="smi-blood mx-auto" style="width:52px;height:52px;font-size:1.1rem;box-shadow:none;border:2px solid #f3c1c7">' + esc(p.blood_type || '?') + '</div><small class="text-muted">' + esc(t('زمرة الدم', 'Blood type')) + '</small></div>' +
        (o.headerActions || '') + '</div>' +
        '<dl class="row smi-kv mt-4 mb-0">' +
        [['العمر', 'Age', p.age !== null && p.age !== undefined ? p.age + ' ' + t('سنة', 'years') : '—'], ['تاريخ الميلاد', 'Date of birth', App.fmtDate(p.date_of_birth)],
         ['الجنس', 'Gender', p.gender || '—'], ['الطول', 'Height', p.height_cm ? Math.round(p.height_cm) + ' cm' : '—', 1],
         ['الوزن', 'Weight', p.weight_kg ? Math.round(p.weight_kg) + ' kg' : '—', 1], ['الهاتف', 'Phone', p.phone || '—', 1],
         ['البريد', 'Email', p.email || '—', 1], ['العنوان', 'Address', p.address || '—'],
         ['جهة اتصال الطوارئ', 'Emergency contact', p.emergency_contact_name || p.emergency_contact_phone ? null : '—']]
          .map(function (x) {
            var v = x[2] === null ? esc(p.emergency_contact_name || '') + (p.emergency_contact_phone ? '<br><span class="ltr">' + esc(p.emergency_contact_phone) + '</span>' : '')
              : x[3] ? '<span class="ltr text-break">' + esc(x[2]) + '</span>' : esc(x[2]);
            return '<div class="col-6 col-md-4 col-xl-3"><dt>' + esc(t(x[0], x[1])) + '</dt><dd>' + v + '</dd></div>';
          }).join('') +
        '</dl></div></div>';

      // allergies (shown first: safety)
      var al = r.allergies;
      html += section('allergies', 'ti-alert-triangle', t('التحسسات', 'Allergies'), al.length, al.length ?
        '<div class="d-flex flex-wrap gap-2">' + al.map(function (a) {
          var sev = (a.severity || '').toLowerCase();
          var color = sev.indexOf('sev') === 0 || a.severity === 'شديد' ? 'danger' : (sev.indexOf('mod') === 0 || a.severity === 'متوسط' ? 'warning' : 'secondary');
          return '<div class="border rounded p-2 pe-3 d-flex align-items-center gap-2"><span class="badge bg-' + color + '">' + esc(a.severity || t('غير محدد', 'n/a')) + '</span><div><strong>' +
            esc(a.substance) + '</strong>' + (a.reaction ? '<small class="d-block text-muted">' + esc(a.reaction) + '</small>' : '') + '</div>' + delBtn(o, 'allergies', a.id) + '</div>';
        }).join('') + '</div>' : none(t('لا توجد تحسسات مسجّلة', 'No allergies recorded')), addBtn(o, 'allergies'));

      // conditions
      var cs = r.conditions;
      html += section('conditions', 'ti-heartbeat', t('الأمراض', 'Conditions'), cs.length, cs.length ?
        '<ul class="list-group list-group-flush smi-list">' + cs.map(function (c) {
          return '<li class="list-group-item px-0 d-flex align-items-center gap-2"><div class="flex-grow-1"><strong>' + esc(c.display_name || c.code_name) + '</strong> ' +
            (c.is_chronic ? '<span class="badge bg-label-danger">' + esc(t('مزمن', 'Chronic')) + '</span> ' : '') +
            (c.status ? '<span class="badge bg-label-secondary">' + esc(c.status) + '</span>' : '') +
            '<small class="d-block text-muted">' + (c.onset_date ? esc(t('منذ ', 'since ') + App.fmtDate(c.onset_date)) : '') + (c.notes ? ' — ' + esc(c.notes) : '') + '</small>' +
            by(c.added_by_name) + '</div>' + delBtn(o, 'conditions', c.id) + '</li>';
        }).join('') + '</ul>' : none(t('لا توجد أمراض مسجّلة', 'No conditions recorded')), addBtn(o, 'conditions'));

      // medications
      var ms = r.medications;
      html += section('medications', 'ti-pill', t('الأدوية', 'Medications'), ms.length, ms.length ?
        '<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>' + esc(t('الدواء', 'Medication')) + '</th><th>' + esc(t('الجرعة', 'Dose')) + '</th><th>' +
        esc(t('التكرار', 'Frequency')) + '</th><th>' + esc(t('الحالة', 'Status')) + '</th><th>' + esc(t('من', 'From')) + '</th><th></th></tr></thead><tbody>' +
        ms.map(function (m) {
          var st = { ACTIVE: ['success', 'مستمر', 'Active'], STOPPED: ['secondary', 'متوقف', 'Stopped'], COMPLETED: ['info', 'منتهي', 'Completed'] }[m.status] || ['secondary', m.status || '—', m.status || '—'];
          return '<tr><td><strong>' + esc(m.medication_name) + '</strong>' + by(m.added_by_name) + '</td><td>' + esc(m.dose || '—') + '</td><td>' + esc(m.frequency || '—') +
            '</td><td><span class="badge bg-label-' + st[0] + '">' + esc(t(st[1], st[2])) + '</span></td><td class="text-nowrap">' + esc(App.fmtDate(m.start_date)) + '</td><td>' + delBtn(o, 'medications', m.id) + '</td></tr>';
        }).join('') + '</tbody></table></div>' : none(t('لا توجد أدوية مسجّلة', 'No medications recorded')), addBtn(o, 'medications'));

      // procedures (surgeries)
      var ps = r.procedures;
      html += section('procedures', 'ti-first-aid-kit', t('العمليات الجراحية السابقة', 'Previous surgeries'), ps.length, ps.length ?
        '<ul class="timeline mb-0 mt-2">' + ps.map(function (x) {
          return '<li class="timeline-item timeline-item-transparent"><span class="timeline-point timeline-point-primary"></span><div class="timeline-event">' +
            '<div class="timeline-header mb-1"><h6 class="mb-0">' + esc(x.name) + '</h6><small class="text-muted">' + esc(App.fmtDate(x.performed_on)) + '</small></div>' +
            '<p class="mb-0 small">' + esc([x.hospital, x.surgeon].filter(Boolean).join(' — ')) + '</p>' + (x.notes ? '<p class="mb-0 small text-muted">' + esc(x.notes) + '</p>' : '') +
            '<div class="d-flex justify-content-between">' + by(x.added_by_name) + delBtn(o, 'procedures', x.id) + '</div></div></li>';
        }).join('') + '</ul>' : none(t('لا توجد عمليات سابقة مسجّلة', 'No surgeries recorded')), addBtn(o, 'procedures'));

      // documents
      var ds = r.documents;
      html += section('documents', 'ti-files', t('التقارير الطبية وصور الأشعة', 'Reports & imaging'), ds.length, ds.length ?
        '<div class="row g-3">' + ds.map(function (d) {
          var ty = docType(d.doc_type);
          return '<div class="col-md-6 col-xl-4"><div class="border rounded p-3 h-100 d-flex gap-3">' +
            '<div class="avatar flex-shrink-0"><span class="avatar-initial rounded bg-label-' + ty[3] + '"><i class="ti ' + ty[2] + '"></i></span></div>' +
            '<div class="flex-grow-1 overflow-hidden"><h6 class="mb-1 text-truncate">' + esc(d.title) + '</h6><small class="text-muted d-block">' + esc(t(ty[0], ty[1])) + ' — ' + esc(App.fmtDate(d.uploaded_at)) +
            (d.file_size ? ' — <span class="ltr">' + esc(App.fileSize(d.file_size)) + '</span>' : '') + '</small>' + by(d.added_by_name) +
            '<div class="mt-2 d-flex gap-1"><button class="btn btn-sm btn-label-primary" data-open-doc="' + d.id + '"><i class="ti ti-eye me-1"></i>' + esc(t('عرض', 'View')) + '</button>' + delBtn(o, 'documents', d.id) + '</div></div></div></div>';
        }).join('') + '</div>' : none(t('لا توجد ملفات مرفوعة', 'No files uploaded')), addBtn(o, 'documents'));

      // observations / vitals
      var ob = r.observations;
      html += section('observations', 'ti-activity-heartbeat', t('القياسات والتحاليل', 'Vitals & results'), ob.length, ob.length ?
        '<div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>' + esc(t('القياس', 'Measure')) + '</th><th>' + esc(t('القيمة', 'Value')) + '</th><th>' + esc(t('التاريخ', 'Date')) + '</th></tr></thead><tbody>' +
        ob.slice(0, 30).map(function (x) { return '<tr><td>' + esc(x.code_name || '—') + '</td><td><strong class="ltr">' + esc(x.value) + ' ' + esc(x.unit || '') + '</strong></td><td class="text-nowrap">' + esc(App.fmtDateTime(x.observed_at)) + '</td></tr>'; }).join('') +
        '</tbody></table></div>' : none(t('لا توجد قياسات', 'No results')), addBtn(o, 'observations'));

      // visits
      var en = r.encounters;
      if (en.length || o.editable) html += section('encounters', 'ti-building-hospital', t('الزيارات', 'Visits'), en.length, en.length ?
        '<ul class="list-group list-group-flush smi-list">' + en.map(function (e) {
          var ty = { OUTPATIENT: t('عيادة خارجية', 'Outpatient'), INPATIENT: t('قبول في المشفى', 'Inpatient'), ER: t('إسعاف', 'Emergency') }[e.type] || e.type || '';
          return '<li class="list-group-item px-0"><strong>' + esc(e.reason || t('زيارة', 'Visit')) + '</strong> <span class="badge bg-label-info">' + esc(ty) + '</span><small class="d-block text-muted">' + esc(App.fmtDateTime(e.start_at)) + '</small></li>';
        }).join('') + '</ul>' : none(t('لا توجد زيارات', 'No visits')), addBtn(o, 'encounters'));

      el.innerHTML = html;
      App.$$('[data-open-doc]', el).forEach(function (b) {
        b.onclick = function () { var d = ds.find(function (x) { return String(x.id) === b.dataset.openDoc; }); App.openDocument(d); };
      });
      App.$$('[data-add]', el).forEach(function (b) { b.onclick = function () { o.onAdd && o.onAdd(b.dataset.add); }; });
      App.$$('[data-del]', el).forEach(function (b) { b.onclick = function () { o.onDelete && o.onDelete(b.dataset.del, b.dataset.id); }; });
    }
  };
})();
