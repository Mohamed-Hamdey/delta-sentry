(function () {
  'use strict';

  const AR = {
    title:      'أمر التفتيش الميداني',
    orderNo:    'رقم الأمر',
    date:       'التاريخ',
    priority:   'الأولوية',
    location:   'الموقع',
    sector:     'القطاع',
    governorate:'المحافظة',
    coordinates:'الإحداثيات',
    area:       'المساحة',
    signal:     'الإشارة',
    observed:   'القيمة الملاحظة',
    forecast:   'القيمة المتوقعة',
    gap:        'الفارق',
    action:     'الإجراء المطلوب',
    actionBody: 'تفتيش ميداني. تأكيد حالة المحصول، توفر المياه، وأي علامات إجهاد مرئية.',
    urgent:     'زيارة عاجلة',
    monitor:    'مراقبة',
    fieldObs:   'الملاحظة الميدانية'
  };

  const EN = {
    title:      'FIELD INSPECTION ORDER',
    orderNo:    'Order №',
    date:       'Date',
    priority:   'Priority',
    location:   'LOCATION',
    sector:     'Sector',
    governorate:'Governorate',
    coordinates:'Coordinates',
    area:       'Area',
    signal:     'SIGNAL',
    observed:   'Observed NDVI',
    forecast:   'Forecast NDVI',
    gap:        'Gap',
    action:     'ACTION REQUIRED',
    actionBody: 'Ground inspection. Confirm crop status, water availability, and visible stress symptoms.',
    fieldObs:   'FIELD OBSERVATION'
  };

  function pad(n) { return String(n).padStart(2, '0'); }
  function todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function buildSheetHTML(p) {
    const priorityEn = p.priority === 'Urgent Visit' ? 'Urgent Visit' : 'Monitor';
    const priorityAr = p.priority === 'Urgent Visit' ? AR.urgent : AR.monitor;
    const gapPct = p.meanObs < 0.05 ? 'bare soil / water' : (p.meanGap < 0 ? `−${Math.min(100, p.dropPct)}%` : `+${Math.min(100, p.dropPct)}%`);

    const date = todayStr();

    return `
      <div class="fo-sheet">

        <!-- Header: bilingual title -->
        <header class="fo-header">
          <div class="fo-header-en">
            <div class="fo-logo">DELTA SENTRY</div>
            <div class="fo-title">${EN.title}</div>
          </div>
          <div class="fo-header-ar" dir="rtl">
            <div class="fo-logo-ar">دلتا سنتري</div>
            <div class="fo-title-ar">${AR.title}</div>
          </div>
        </header>

        <!-- Meta strip: ID + date + priority -->
        <div class="fo-meta">
          <div class="fo-meta-cell">
            <span class="fo-meta-label">${EN.orderNo} · ${AR.orderNo}</span>
            <b>${p.id}</b>
          </div>
          <div class="fo-meta-cell">
            <span class="fo-meta-label">${EN.date} · ${AR.date}</span>
            <b>${date}</b>
          </div>
          <div class="fo-meta-cell fo-priority-${priorityEn === 'Urgent Visit' ? 'urgent' : 'monitor'}">
            <span class="fo-meta-label">${EN.priority} · ${AR.priority}</span>
            <b>${priorityEn} · ${priorityAr}</b>
          </div>
        </div>

        <!-- Bilingual rows: Location -->
        <div class="fo-section">
          <div class="fo-section-title">
            <span>${EN.location}</span>
            <span dir="rtl">${AR.location}</span>
          </div>
          <div class="fo-row-grid">
            <div class="fo-row">
              <span class="fo-label">${EN.sector} · ${AR.sector}</span>
              <b>${p.label}</b>
            </div>
            <div class="fo-row">
              <span class="fo-label">${EN.governorate} · ${AR.governorate}</span>
              <b>${p.gov} · ${p.govAr || ''}</b>
            </div>
            <div class="fo-row">
              <span class="fo-label">${EN.coordinates} · ${AR.coordinates}</span>
              <b>${p.lat != null ? `${p.lat}°N, ${p.lon}°E` : 'Not configured'}</b>
            </div>
            <div class="fo-row">
              <span class="fo-label">${EN.area} · ${AR.area}</span>
              <b>${p.feddans} feddan (${p.hectares} ha · ${p.pixelCount} pixels)</b>
            </div>
          </div>
        </div>

        <!-- Bilingual rows: Signal -->
        <div class="fo-section">
          <div class="fo-section-title">
            <span>${EN.signal}</span>
            <span dir="rtl">${AR.signal}</span>
          </div>
          <div class="fo-row-grid fo-row-grid-3">
            <div class="fo-row fo-row-num">
              <span class="fo-label">${EN.observed} · ${AR.observed}</span>
              <b>${p.meanObs.toFixed(3)}</b>
            </div>
            <div class="fo-row fo-row-num">
              <span class="fo-label">${EN.forecast} · ${AR.forecast}</span>
              <b>${p.meanFcst.toFixed(3)}</b>
            </div>
            <div class="fo-row fo-row-num fo-row-gap">
              <span class="fo-label">${EN.gap} · ${AR.gap}</span>
              <b>${p.meanGap.toFixed(3)} (${gapPct})</b>
            </div>
          </div>
        </div>

        <!-- Bilingual: Action -->
        <div class="fo-section fo-action">
          <div class="fo-section-title">
            <span>${EN.action}</span>
            <span dir="rtl">${AR.action}</span>
          </div>
          <p class="fo-action-en">${EN.actionBody}</p>
          <p class="fo-action-ar" dir="rtl">${AR.actionBody}</p>
        </div>

        <!-- NEW: Field Observation Checkboxes -->
        <div class="fo-section">
          <div class="fo-section-title">
            <span>${EN.fieldObs}</span>
            <span dir="rtl">${AR.fieldObs}</span>
          </div>
          <div class="fo-checks">
            <label>☐ Irrigated normally · ريّ طبيعي</label>
            <label>☐ Water shortage · نقص مياه</label>
            <label>☐ Pest / disease · آفة أو مرض</label>
            <label>☐ Harvest residue · بقايا حصاد</label>
            <label>☐ Salinity · ملوحة</label>
            <label>☐ Other · أخرى</label>
          </div>
        </div>

        <!-- Footer: signature + timestamp -->
        <footer class="fo-footer">
          <div class="fo-sign">
            <span>Inspector signature · توقيع المفتش</span>
            <div class="fo-sign-line"></div>
          </div>
          <div class="fo-stamp">
            <span>Generated by Delta Sentry</span>
            <b>${new Date().toISOString().slice(0, 19).replace('T', ' ')}</b>
          </div>
        </footer>

      </div>`;
  }

  function openFieldOrder(patch) {
    if (!patch) {
      const note = document.createElement('div');
      note.className = 'fo-inline-note';
      note.textContent = 'Select a field patch from the map or worklist first.';
      document.body.appendChild(note);
      setTimeout(() => note.remove(), 2400);
      return;
    }
    const modal = document.getElementById('printModal');
    const sheet = document.getElementById('printSheet');
    if (!modal || !sheet) {
      console.warn('[Delta Sentry] #printModal or #printSheet missing — cannot open field order.');
      return;
    }
    sheet.innerHTML = buildSheetHTML(patch);
    modal.hidden = false;
    const closeBtn = document.getElementById('closePrintBtn');
    if (closeBtn) closeBtn.focus();
  }

  function initFieldOrderModal() {
    const modal = document.getElementById('printModal');
    if (!modal) {
      console.warn('[Delta Sentry] #printModal not found — print feature disabled.');
      return;
    }

    const close = () => { modal.hidden = true; };
    const closeBtn = document.getElementById('closePrintBtn');
    if (closeBtn) closeBtn.addEventListener('click', close);

    const backdrop = document.getElementById('closePrintBackdrop');
    if (backdrop) backdrop.addEventListener('click', close);

    const printBtn = document.getElementById('triggerPrintBtn');
    if (printBtn) printBtn.addEventListener('click', () => {
      modal.classList.add('printing');
      window.print();
      setTimeout(() => modal.classList.remove('printing'), 300);
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !modal.hidden) close();
    });
  }

  DS.fieldOrder = { openFieldOrder, initFieldOrderModal };
})();