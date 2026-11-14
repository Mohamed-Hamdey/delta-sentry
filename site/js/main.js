(function () {
  const { $, $$, key, f3 } = DS.utils;
  const {
    getJSON, generateFallbackData, generateFallbackResults, generateFallbackTrend,
    monthData, clusterPatchesCached, clearPatchCache
  } = DS.data;
  const { drawUnified, triggerSweep } = DS.map;

  let cachedResults = null;
  let resizeTimer = null;

  /* ---------------------------------------------------------------- utils */
  function setText(sel, txt) {
    const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (el) el.textContent = txt;
  }
  function safeOn(sel, evt, fn) {
    const el = document.querySelector(sel);
    if (el) el.addEventListener(evt, fn);
  }

  /* -------------------------------------------------- georeferencing
     Derive south/east from the grid rather than trusting a hand-typed box.
     Every printed coordinate depends on this being consistent. */
  function deriveAoiBounds() {
    const aoi = DS.CONFIG.AOI;
    if (!aoi.northWest) return;
    const st = DS.state;
    const dLat = aoi.pixelM / 111320;
    const dLon = aoi.pixelM / (111320 * Math.cos(aoi.northWest.lat * Math.PI / 180));
    aoi.bounds = {
      north: aoi.northWest.lat,
      south: +(aoi.northWest.lat - st.gy * dLat).toFixed(5),
      west: aoi.northWest.lon,
      east: +(aoi.northWest.lon + st.gx * dLon).toFixed(5)
    };
    const cellM = ((aoi.bounds.east - aoi.bounds.west) * 111320 * Math.cos(aoi.northWest.lat * Math.PI / 180)) / st.gx;
    if (Math.abs(cellM - aoi.pixelM) > 2) {
      console.warn(`[DS] cell size ${cellM.toFixed(1)} m does not match declared ${aoi.pixelM} m`);
    }
  }

  /* ------------------------------------------------------------------ nav */
  function initNav() {
    const sections = ['hero', 'stage', 'trymodel', 'deepdive'];
    const buttons = $$('.mb-steps button');
    if ('IntersectionObserver' in window && buttons.length) {
      const obs = new IntersectionObserver(entries => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            buttons.forEach(b => b.classList.toggle('on', b.dataset.jump === e.target.id));
          }
        });
      }, { rootMargin: '-42% 0px -50% 0px', threshold: 0 });
      sections.forEach(id => { const el = document.getElementById(id); if (el) obs.observe(el); });
    }
    $$('[data-jump]').forEach(b => {
      b.addEventListener('click', () => {
        const el = document.getElementById(b.dataset.jump);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  /* ------------------------------------------------------ hero backdrop
     The hero texture is the actual NDVI tile, not a starfield. */
  function drawHeroField() {
    const cv = $('#heroField');
    if (!cv || !DS.state.data.length) return;
    const { gx, gy, minx, miny } = DS.state;
    if (!gx || !gy) return;

    // Draw at 1 bitmap pixel per 30 m cell and let the browser interpolate on
    // upscale. Drawing at display resolution produced visible mosaic blocks.
    cv.width = gx;
    cv.height = gy;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, gx, gy);

    const md = monthData(DS.state.cur);
    const range = DS.state.layerRange || { min: 0.05, max: 0.65 };
    const span = Math.max(0.01, range.max - range.min);

    md.forEach(d => {
      const v = Math.max(0, Math.min(1, (d.observed_ndvi - range.min) / span));
      const r = Math.round(92 + 143 * v), g = Math.round(52 + 143 * v), b = Math.round(28 + 66 * v);
      ctx.fillStyle = `rgba(${r},${g},${b},${(0.35 + v * 0.65).toFixed(3)})`;
      ctx.fillRect(d.x - minx, d.y - miny, 1, 1);
    });
  }

  /* ---------------------------------------------------------------- bars */
  function buildBars() {
    const counts = DS.state.months.map((_, i) =>
      clusterPatchesCached(monthData(i), DS.state.calibration, i).patches.length);
    const mx = Math.max(1, ...counts);
    const box = $('#bars');
    if (!box) return;
    box.innerHTML = '';
    const MN = ['J','F','M','A','M','J','J','A','S','O','N','D'];
    counts.forEach((c, i) => {
      const wrap = document.createElement('div');
      wrap.className = 'bar-wrap';
      wrap.title = `${DS.state.months[i]} — ${c} patches`;
      const bar = document.createElement('i');
      bar.style.height = Math.max(10, (c / mx) * 76) + '%';
      const label = document.createElement('span');
      label.className = 'bar-label';
      const mIdx = parseInt(DS.state.months[i].split('-')[1], 10) - 1;
      label.textContent = MN[mIdx] || '?';
      wrap.appendChild(bar);
      wrap.appendChild(label);
      wrap.addEventListener('click', () => { stopPlay(); setMonth(i); triggerSweep(); });
      box.appendChild(wrap);
    });
  }

  /* ------------------------------------------------------------- locator */
  function updateLocator(patch) {
    if (!patch) return;
    const pin = $('#aoiPin');
    if (pin) {
      pin.setAttribute('transform', `translate(${(142 + patch.normX * 80).toFixed(1)}, ${(70 + patch.normY * 50).toFixed(1)})`);
    }
    setText('#locatorCoords', patch.lat != null ? `${patch.lat}°N, ${patch.lon}°E` : '—');
    setText('#locatorPatchLabel', `Active: ${patch.id} · ${patch.gov}`);
    setText('#activePlaceBadge', `${patch.label}`);
  }

  /* ------------------------------------------------------------ worklist */
  function renderWorklist() {
    const list = $('#patchList');
    const { patches, selPatch } = DS.state;
    if (!list) return;
    list.innerHTML = '';
    setText('#patchCountBadge', `${patches.length} patches`);

    if (!patches.length) {
      list.innerHTML = `<p class="note" style="padding:12px;border:1px dashed var(--line);border-radius:6px;text-align:center">
        No contiguous deficit patches at this threshold. Widen it — or take that as the good news it is.</p>`;
      return;
    }
    patches.forEach(p => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'patch-item' + (selPatch && selPatch.id === p.id ? ' on' : '');
      btn.setAttribute('role', 'option');
      btn.setAttribute('aria-selected', selPatch && selPatch.id === p.id ? 'true' : 'false');
      btn.innerHTML = `
        <div>
          <span class="patch-item-title">${p.id} · Block ${p.label.split('Block ')[1] || p.label}</span>
          <span class="patch-item-sub">${p.gov} · ${p.priority} · ${p.meanObs < 0.05 ? 'bare soil' : '−' + Math.min(100, p.dropPct) + '% NDVI'}</span>
        <div class="patch-item-area">
          <b>${p.feddans} feddan</b>
          <span>${p.hectares} ha</span>
        </div>`;
      btn.addEventListener('click', () => selectPatch(p));
      list.appendChild(btn);
    });
  }

  function showSelectedPatch() {
    const box = $('#unitBody');
    const p = DS.state.selPatch;
    if (!box) return;
    if (!p) {
      box.innerHTML = `<p class="note">${DS.state.patches.length
        ? 'Select a patch on the map or in the worklist.'
        : 'No patch to inspect at this threshold.'}</p>`;
      return;
    }
    setText('#selPatchTitle', `${p.id} · ${p.gov}`);
    box.innerHTML =
      `<div class="row"><span>Location</span><b>${p.label}</b></div>` +
      `<div class="row"><span>Flagged area</span><b style="color:var(--alert)">${p.feddans} feddan · ${p.hectares} ha</b></div>` +
      `<div class="row"><span>Observed NDVI</span><b>${f3(p.meanObs)} ${p.meanObs < 0.05 ? '(bare soil)' : ''}</b></div>` +
      `<div class="row"><span>Prithvi forecast</span><b style="color:var(--blue)">${f3(p.meanFcst)}</b></div>` +
      `<div class="row"><span>Deficit gap</span><b style="color:var(--alert)">${f3(p.meanGap)} ${p.meanObs < 0.05 ? '' : '· −' + Math.min(100, p.dropPct) + '%'}</b></div>`;
  }

  function selectPatch(patch, pixel) {
    DS.state.selPatch = patch;
    DS.state.selPixel = pixel || (patch ? patch.cells[0] : null);
    updateLocator(patch);
    renderWorklist();
    showSelectedPatch();
    DS.charts.drawChart();
    drawUnified();
    if (DS.tryModel && DS.tryModel.syncSelection) DS.tryModel.syncSelection(patch);
  }

  /* --------------------------------------------------------------- month */
  function setMonth(i) {
    const st = DS.state;
    st.cur = Math.max(0, Math.min(st.months.length - 1, i));
    const sl = $('#timeSlider');
    if (sl) sl.value = st.cur;
    setText('#timeLabel', st.months[st.cur]);

    const md = monthData(st.cur);
    const { patches, activeSet, rawFlagCount } = clusterPatchesCached(md, st.calibration, st.cur);
    st.patches = patches;
    st.activeSet = activeSet;

    const fed = Math.round(patches.reduce((s, p) => s + p.feddans, 0));
    const ha = Math.round(patches.reduce((s, p) => s + p.hectares, 0));
    const urgent = patches.filter(p => p.priority === 'Urgent Visit').length;
    const aoi = DS.CONFIG.AOI;

    setText('#verdictDate', `${st.months[st.cur]} · ${aoi.region.toUpperCase()}`);
    if (!patches.length) {
      setText('#verdictHeadline', 'No active anomaly patches — the tile is inside Prithvi’s forecast bounds this month');
      setText('#verdictSub', `${md.length.toLocaleString()} 30 m cells scanned · nothing crossed the operating threshold.`);
    } else {
      setText('#verdictHeadline', `${patches.length} deficit patches · ${fed.toLocaleString()} feddan (${ha.toLocaleString()} ha) · ${urgent} to inspect first`);
      const basis = st.calibration === 'raw'
        ? 'all cells below the −0.10 flag threshold'
        : `the ${st.calibration === 'top10' ? '10%' : '5%'} of cells with the largest deficit — a workload cap, not a fixed threshold`;
      setText('#verdictSub', `Clustered from ${activeSet.size.toLocaleString()} cells: ${basis}. ${rawFlagCount.toLocaleString()} raw flags across ${md.length.toLocaleString()} 30 m cells.`);
    }

    const wraps = $('#bars') ? [...$('#bars').children] : [];
    wraps.forEach((w, j) => w.classList.toggle('on', j === st.cur));

    // keep the same physical patch selected across months when possible
    const prev = st.selPatch ? new Set(st.selPatch.cells.map(c => `${c.x},${c.y}`)) : null;
    let next = null;
    if (prev && prev.size) {
      let best = 0;
      patches.forEach(p => {
        const score = p.cells.filter(c => prev.has(`${c.x},${c.y}`)).length;
        if (score > best) { best = score; next = p; }
      });
    }
    if (!next) next = patches[0] || null;
    selectPatch(next);

    drawHeroField();

    if (cachedResults) {
      const vp = $('#p-validation');
      if (vp && !vp.hidden) vp.innerHTML = DS.charts.renderValidation(cachedResults);
    }
  }

  /* ---------------------------------------------------------------- play */
  function stopPlay() {
    clearInterval(DS.state.playTimer);
    DS.state.playTimer = null;
    DS.state.playing = false;
    setText('#playBtn', '▶ Play season');
  }
  function togglePlay() {
    const st = DS.state;
    if (st.playing) return stopPlay();
    if (st.months.length <= 1) return;
    st.playing = true;
    setText('#playBtn', '⏸ Pause');
    if (st.cur >= st.months.length - 1) setMonth(0);
    st.playTimer = setInterval(() => {
      if (st.cur >= st.months.length - 1) return stopPlay();
      setMonth(st.cur + 1);
      triggerSweep();
    }, 1250);
  }

  /* ------------------------------------------------------------ evidence */
  async function loadEvidence() {
    let results;
    try { results = await getJSON(DS.CONFIG.resultsUrl); }
    catch (e) { results = generateFallbackResults(); }
    cachedResults = results;

    const audit = $('#p-audit');
    if (audit) audit.innerHTML = DS.charts.renderAudit(results.audit || generateFallbackResults().audit);

    const val = $('#p-validation');
    if (val) val.innerHTML = DS.charts.renderValidation(results);

    let trend;
    try { trend = await getJSON(DS.CONFIG.trendUrl); }
    catch (e) { trend = generateFallbackTrend(); }
    const tr = $('#p-trend');
    if (tr) tr.innerHTML = DS.charts.renderTrend(trend);

    const dt = $('#p-data');
    if (dt) dt.innerHTML = DS.charts.renderData();
  }

  /* --------------------------------------------------------------- init */
  async function init() {
    const st = DS.state;
    if (DS.stars && DS.stars.initStars) DS.stars.initStars();
    try { st.data = await getJSON(DS.CONFIG.dataUrl); }
    catch (e) {
      const b = $('#banner'); if (b) b.classList.add('on');
      st.data = generateFallbackData();
      console.warn('[Delta Sentry] embedded fallback data in use');
    }
    if (!st.data || !st.data.length) st.data = generateFallbackData();

    st.months = [...new Set(st.data.map(key))].sort();
    st.cur = Math.max(0, st.months.length - 1);   // open on the latest month, not January

    // fold rather than spread: Math.min(...156k items) overflows the stack
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < st.data.length; i++) {
      const d = st.data[i];
      if (d.x < x0) x0 = d.x; if (d.x > x1) x1 = d.x;
      if (d.y < y0) y0 = d.y; if (d.y > y1) y1 = d.y;
    }
    st.minx = x0; st.miny = y0;
    st.gx = x1 - x0 + 1;
    st.gy = y1 - y0 + 1;

    deriveAoiBounds();

    const sl = $('#timeSlider');
    if (sl) {
      sl.min = 0;
      sl.max = Math.max(0, st.months.length - 1);
      sl.value = Math.max(0, st.months.length - 1);
      sl.disabled = st.months.length <= 1;
      sl.addEventListener('input', e => setMonth(parseInt(e.target.value, 10)));
    }

    buildBars();
    initNav();

    safeOn('#calibrationSelect', 'change', e => {
      st.calibration = e.target.value;
      clearPatchCache();
      buildBars();
      setMonth(st.cur);
    });
    safeOn('#playBtn', 'click', togglePlay);

    // stage tabs
    $$('[data-stage]').forEach(btn => btn.addEventListener('click', () => {
      st.stageState = btn.dataset.stage;
      $$('[data-stage]').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
      drawUnified();
    }));

    // map interactions
    const cv = $('#cvUnified');
    if (cv) {
      cv.addEventListener('mousemove', DS.map.handleHover);
      cv.addEventListener('mouseleave', () => { const t = $('#map-tooltip'); if (t) t.style.display = 'none'; });
      cv.addEventListener('click', DS.map.handleClick);
    }

    // evidence tabs
    $$('.tabbar button').forEach(b => b.addEventListener('click', () => {
      $$('.tabbar button').forEach(o => o.setAttribute('aria-selected', String(o === b)));
      $$('.ev-panel').forEach(p => { p.hidden = p.id !== 'p-' + b.dataset.tab; });
    }));

    // field order
    if (DS.fieldOrder) {
      DS.fieldOrder.initFieldOrderModal();
      safeOn('#fieldOrderBtn', 'click', () => DS.fieldOrder.openFieldOrder(st.selPatch));
    }

    // try model
    if (DS.tryModel) DS.tryModel.init();

    setMonth(st.cur);
    await loadEvidence();

    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (!st.data.length) return;
        drawUnified();
        drawHeroField();
        DS.charts.drawChart();
        if (window.matchMedia('(min-width:721px)').matches) buildBars();
        const wraps = $('#bars') ? [...$('#bars').children] : [];
        wraps.forEach((w, j) => w.classList.toggle('on', j === st.cur));
      }, 160);
    });
  }

  DS.onSelectPatch = (patch, pixel) => selectPatch(patch, pixel);
  DS.onSelectPixel = pixel => { DS.state.selPixel = pixel; DS.charts.drawChart(); };
  DS.setMonth = setMonth;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
