(function () {
  const { $, f3 } = DS.utils;
  const { monthData, computeRange, findPixelAtEvent } = DS.data;

  function ndviColor(raw, min, max, grayscale = false) {
    if (raw == null || isNaN(raw)) return null;
    const v = Math.max(0, Math.min(1, (raw - min) / (max - min)));
    if (grayscale) {
      const g = Math.round(28 + v * 110);
      return `rgb(${g},${g + 3},${g + 8})`;
    }
    if (v < 0.5) {
      const t = v * 2;
      return `rgb(${Math.round(92 + (235 - 92) * t)},${Math.round(52 + (195 - 52) * t)},${Math.round(28 + (42 - 28) * t)})`;
    }
    const t = (v - 0.5) * 2;
    return `rgb(${Math.round(235 - (235 - 34) * t)},${Math.round(195 - (195 - 197) * t)},${Math.round(42 + (94 - 42) * t)})`;
  }

  function drawUnified() {
    const cv = $('#cvUnified');
    if (!cv) return;
    const ctx = cv.getContext('2d');
    const dpr = devicePixelRatio || 1;
    const w = cv.clientWidth;
    const h = cv.clientHeight;
    if (!w || !h) return;

    cv.width = w * dpr;
    cv.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const md = monthData(DS.state.cur);
    DS.state.layerRange = computeRange(md);
    const { min, max } = DS.state.layerRange;
    const { gx, gy, minx, miny, stageState, activeSet, selPatch } = DS.state;

    const cs = Math.min(w / gx, h / gy);
    const ox = (w - cs * gx) / 2;
    const oy = (h - cs * gy) / 2;
    cv._g = { cs, ox, oy };

    // State 1: Observed HLS | State 2: Forecast Ghost Overlay | State 3: Grayscale + Ignited Patches
    md.forEach(d => {
      const px = ox + (d.x - minx) * cs;
      const py = oy + (d.y - miny) * cs;
      const cellKey = `${d.x},${d.y}`;

      if (stageState === 'observe') {
        ctx.fillStyle = ndviColor(d.observed_ndvi, min, max, false);
        ctx.fillRect(px, py, Math.ceil(cs), Math.ceil(cs));
      } else if (stageState === 'forecast') {
        // Base observed at 45%, blended with Prithvi forecast at 65%
        ctx.fillStyle = ndviColor(d.observed_ndvi, min, max, false);
        ctx.fillRect(px, py, Math.ceil(cs), Math.ceil(cs));
        ctx.save();
        ctx.globalAlpha = 0.65;
        ctx.fillStyle = ndviColor(d.forecast_ndvi, min, max, false);
        ctx.fillRect(px, py, Math.ceil(cs), Math.ceil(cs));
        ctx.restore();
      } else {
        // Alert state: grayscale background, red ignited patches
        const isAlertCell = activeSet && activeSet.has(cellKey);
        if (isAlertCell) {
          const gap = Math.abs(d.observed_ndvi - d.forecast_ndvi);
          const intensity = Math.min(1, 0.55 + gap * 2.4);
          ctx.fillStyle = `rgba(252, 61, 33, ${intensity.toFixed(2)})`;
        } else {
          ctx.fillStyle = ndviColor(d.observed_ndvi, min, max, true);
        }
        ctx.fillRect(px, py, Math.ceil(cs), Math.ceil(cs));
      }
    });

    // State 2 subtle isoline grid so smooth modeled forecast reads as a spatial field
    if (stageState === 'forecast') {
      ctx.strokeStyle = 'rgba(79, 141, 255, 0.28)';
      ctx.lineWidth = 1;
      md.forEach(d => {
        if (Math.abs(d.forecast_ndvi - 0.45) < 0.015 || Math.abs(d.forecast_ndvi - 0.55) < 0.015) {
          ctx.strokeRect(ox + (d.x - minx) * cs, oy + (d.y - miny) * cs, cs, cs);
        }
      });
    }

    // Outline the selected patch: only the outer edges, not every cell
    if (selPatch && selPatch.cells && selPatch.cells.length) {
      const inPatch = new Set(selPatch.cells.map(c => c.x + ',' + c.y));
      ctx.strokeStyle = 'rgba(255,255,255,.95)';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      selPatch.cells.forEach(c => {
        const px = ox + (c.x - minx) * cs;
        const py = oy + (c.y - miny) * cs;
        if (!inPatch.has(c.x + ',' + (c.y - 1))) { ctx.moveTo(px, py); ctx.lineTo(px + cs, py); }
        if (!inPatch.has(c.x + ',' + (c.y + 1))) { ctx.moveTo(px, py + cs); ctx.lineTo(px + cs, py + cs); }
        if (!inPatch.has((c.x - 1) + ',' + c.y)) { ctx.moveTo(px, py); ctx.lineTo(px, py + cs); }
        if (!inPatch.has((c.x + 1) + ',' + c.y)) { ctx.moveTo(px + cs, py); ctx.lineTo(px + cs, py + cs); }
      });
      ctx.stroke();
    }

    updateStateChrome();
  }

  function updateStateChrome() {
    const { stageState, layerRange } = DS.state;
    const badge = $('#stateBadge');
    const legend = $('#unifiedLegend');
    if (!badge || !legend) return;

    if (stageState === 'observe') {
      badge.textContent = 'STATE 01 · HLS SATELLITE OBSERVED';
      legend.innerHTML = `<span>Low (${layerRange.min.toFixed(2)})</span><div class="ramp"></div><span>Dense Crop (${layerRange.max.toFixed(2)})</span>`;
    } else if (stageState === 'forecast') {
      badge.textContent = 'STATE 02 · PRITHVI-EO FORECAST OVERLAY';
      legend.innerHTML = `<span>Modeled Low (${layerRange.min.toFixed(2)})</span><div class="ramp"></div><span>Expected Peak (${layerRange.max.toFixed(2)})</span>`;
    } else {
      badge.textContent = 'STATE 03 · DEFICIT PATCHES IGNITED';
      legend.innerHTML = `<span>Ignited Deficit Patch</span><div class="ramp gap-ramp"></div><span>Baseline Observed (Grayscale)</span>`;
    }
  }

  function triggerSweep() {
    const s = $('#scanUnified');
    if (!s) return;
    s.classList.remove('go');
    void s.offsetWidth;
    s.classList.add('go');
  }

  function handleHover(e) {
    const u = findPixelAtEvent(e);
    const tip = $('#map-tooltip');
    if (!u || !tip) {
      if (tip) tip.style.display = 'none';
      return;
    }
    const patch = DS.state.patches.find(p => p.cells.some(c => c.x === u.x && c.y === u.y));
    const gap = u.observed_ndvi - u.forecast_ndvi;
    const locLabel = patch ? `${patch.id} (${patch.gov})` : `Cell R${u.y},C${u.x}`;
    tip.innerHTML =
      `<b style="color:var(--teal)">${locLabel}</b> &nbsp;` +
      `<b>Obs:</b> ${f3(u.observed_ndvi)} &nbsp;` +
      `<b>Fcst:</b> ${f3(u.forecast_ndvi)} &nbsp;` +
      `<b style="color:${gap < 0 ? 'var(--red)' : 'var(--teal)'}">Δ ${gap >= 0 ? '+' : ''}${f3(gap)}</b>`;
    tip.style.display = 'block';

    const tipW = tip.offsetWidth || 260;
    const left = Math.max(10, Math.min(window.innerWidth - tipW - 12, e.clientX + 14));
    const top = Math.max(54, e.clientY - 36);
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }

  function handleClick(e) {
    const u = findPixelAtEvent(e);
    if (!u) return;
    const matchingPatch = DS.state.patches.find(p => p.cells.some(c => c.x === u.x && c.y === u.y));
    if (matchingPatch && DS.onSelectPatch) {
      DS.onSelectPatch(matchingPatch, u);
    } else if (DS.onSelectPixel) {
      DS.onSelectPixel(u);
    }
  }

  DS.map = {
    drawUnified,
    triggerSweep,
    handleHover,
    handleClick
  };
})();