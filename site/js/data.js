(function () {
  const { key, isFlag } = DS.utils;
  const { PIXEL_HA, PIXEL_FEDDAN } = DS.CONSTANTS;

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url);
    return r.json();
  }

  function generateFallbackData() {
    const rows = [];
    // FIX #10: Match trend period (2000–2025) — fallback must not jump to 2026
    const sampleMonths = [
      [2025,1],[2025,2],[2025,3],[2025,4],[2025,5],[2025,6],
      [2025,7],[2025,8],[2025,9],[2025,10],[2025,11],[2025,12]
    ];
    const hotspots = [
      { cx: 10, cy: 7,  r: 3.6, amp: 0.24 },
      { cx: 23, cy: 14, r: 4.1, amp: 0.21 },
      { cx: 16, cy: 18, r: 2.8, amp: 0.18 },
      { cx: 27, cy: 6,  r: 2.5, amp: 0.16 }
    ];
    for (const [year, month] of sampleMonths) {
      const seasonal = 0.44 + 0.21 * Math.sin(((month - 1) / 12) * Math.PI * 2);
      for (let y = 0; y < 24; y++) {
        for (let x = 0; x < 32; x++) {
          const spatial = 0.09 * Math.sin(x * 0.24) * Math.cos(y * 0.28);
          const forecast = Math.max(0.10, Math.min(0.84, seasonal + spatial));
          let drop = Math.sin(x * 11 + y * 7 + month) * 0.018;
          hotspots.forEach((h, idx) => {
            const dist = Math.hypot(x - h.cx, y - h.cy);
            if (dist < h.r && (month >= 5 || idx % 2 === 0)) {
              drop += h.amp * (1 - dist / (h.r + 0.8));
            }
          });
          const observed = Math.max(0.03, forecast - drop);
          rows.push({
            year, month, x, y,
            forecast_ndvi: +forecast.toFixed(4),
            observed_ndvi: +observed.toFixed(4),
            flag: (observed - forecast) < -0.10 ? 'Anomaly' : 'Normal'
          });
        }
      }
    }
    return rows;
  }

  function generateFallbackResults() {
    // FIX #6: Fallback baselines match REAL magnitude (not 3× better)
    return {
      coverage: 0.85,
      audit: { n: 44, real: 18, harvest: 12, artifact: 9, unclear: 5 },
      baselines: [
        { name: 'Seasonal Climatology (12-yr)', rmse: 0.1767, mae: 0.1393 },
        { name: 'Prithvi-EO-2.0 B3 (30m)',      rmse: 0.1823, mae: 0.1505 },
        { name: 'Persistence (Carry-Forward)',  rmse: 0.1858, mae: 0.1320 }
      ],
      _fallback: true
    };
  }

  function generateFallbackTrend() {
    return {
      alpha: 0.05,
      method: 'Seasonal Mann-Kendall + Benjamini-Hochberg FDR (2000–2025)',
      decline_pct: 8.4,
      none_pct: 54.2,
      increase_pct: 37.4,
      _fallback: true
    };
  }

  function monthData(i) {
    const k = DS.state.months[i];
    return DS.state.data.filter(d => key(d) === k);
  }

  function computeRange(md) {
    const vals = md
      .flatMap(d => [d.observed_ndvi, d.forecast_ndvi])
      .filter(v => v != null && !isNaN(v))
      .sort((a, b) => a - b);
    if (!vals.length) return { min: 0.05, max: 0.65 };
    const lo = vals[Math.floor(vals.length * 0.02)];
    const hi = vals[Math.floor(vals.length * 0.98)];
    return (hi - lo > 0.01) ? { min: lo, max: hi } : { min: 0.05, max: 0.65 };
  }

  /* 8-Connected Component Clustering */
  function clusterPatches(md, calibration) {
    if (!md.length) return { patches: [], activeSet: new Set(), rawFlagCount: 0, thresholdGap: -0.10 };

    const rawFlagCount = md.filter(isFlag).length;
    const deficits = md
      .map(d => ({ d, gap: d.observed_ndvi - d.forecast_ndvi }))
      .filter(item => item.gap < 0)
      .sort((a, b) => a.gap - b.gap);

    let thresholdGap = -0.10;
    let selectedItems = [];

    if (calibration === 'raw') {
      selectedItems = md.filter(isFlag).map(d => ({ d, gap: d.observed_ndvi - d.forecast_ndvi }));
      thresholdGap = selectedItems.length ? Math.max(...selectedItems.map(i => i.gap)) : -0.10;
    } else {
      const frac = calibration === 'top10' ? 0.10 : 0.05;
      const k = Math.max(4, Math.floor(md.length * frac));
      selectedItems = deficits.slice(0, k);
      thresholdGap = selectedItems.length ? selectedItems[selectedItems.length - 1].gap : -0.10;
    }

    const activeMap = new Map();
    selectedItems.forEach(({ d }) => activeMap.set(`${d.x},${d.y}`, d));

    const visited = new Set();
    const rawPatches = [];
    const dirs = [[-1,-1],[0,-1],[1,-1],[-1,0],[1,0],[-1,1],[0,1],[1,1]];

    activeMap.forEach((startCell, startKey) => {
      if (visited.has(startKey)) return;
      const queue = [startCell];
      const cluster = [];
      visited.add(startKey);

      while (queue.length) {
        const curr = queue.shift();
        cluster.push(curr);
        for (const [dx, dy] of dirs) {
          const nk = `${curr.x + dx},${curr.y + dy}`;
          if (!visited.has(nk) && activeMap.has(nk)) {
            visited.add(nk);
            queue.push(activeMap.get(nk));
          }
        }
      }
      rawPatches.push(cluster);
    });

    // FIX #9: Keep singletons only if their deficit is severe (≥ 0.18, ~2× the 0.10 flag threshold)
    // Instead of dropping all singletons whenever *any* multi-pixel patch exists.
    let finalClusters = rawPatches.filter(cluster => {
      if (cluster.length >= 2) return true;
      const c = cluster[0];
      const gap = Math.abs(c.observed_ndvi - c.forecast_ndvi);
      return gap >= 0.18;
    });
    // Safety: if the filter removed everything, fall back to all raw patches
    if (!finalClusters.length) finalClusters = rawPatches;

    finalClusters.sort((a, b) => b.length - a.length);

    const { minx, miny, gx, gy } = DS.state;
    const patches = finalClusters.map((cells, idx) => {
      const cx = cells.reduce((s, c) => s + c.x, 0) / cells.length;
      const cy = cells.reduce((s, c) => s + c.y, 0) / cells.length;
      const normX = (cx - minx) / Math.max(1, gx);
      const normY = (cy - miny) / Math.max(1, gy);

      const aoi = DS.CONFIG.AOI;
      const row = Math.round(cy - miny) + 1;
      const col = Math.round(cx - minx) + 1;
      const sector = {
        name: (aoi && aoi.name) || 'Study area',
        gov: (aoi && aoi.region) || 'Study area',
        govAr: (aoi && aoi.regionAr) || ''
      };
      const blockNum = `R${row}·C${col}`;

      const meanObs = cells.reduce((s, c) => s + c.observed_ndvi, 0) / cells.length;
      const meanFcst = cells.reduce((s, c) => s + c.forecast_ndvi, 0) / cells.length;
      const meanGap = meanObs - meanFcst;
      const dropPct = meanFcst > 0.01 ? Math.round(Math.abs(meanGap / meanFcst) * 100) : 0;

      // Real coordinates only when the AOI bounds are configured (linear map of the grid onto the box)
      let lat = null, lon = null;
      if (aoi && aoi.bounds) {
        const b = aoi.bounds;
        lat = +(b.north - ((cy - miny + 0.5) / gy) * (b.north - b.south)).toFixed(5);
        lon = +(b.west + ((cx - minx + 0.5) / gx) * (b.east - b.west)).toFixed(5);
      }

      return {
        id: 'P-' + String(idx + 1).padStart(2, '0'),
        rank: idx + 1,
        label: `${sector.name} · Block ${blockNum}`,
        gov: sector.gov,
        govAr: sector.govAr,
        cells,
        pixelCount: cells.length,
        feddans: +(cells.length * PIXEL_FEDDAN).toFixed(1),
        hectares: +(cells.length * PIXEL_HA).toFixed(1),
        cx, cy, normX, normY, lat, lon,
        meanObs, meanFcst, meanGap, dropPct,
        priority: idx < Math.max(3, Math.ceil(finalClusters.length * 0.2)) ? 'Urgent Visit' : 'Monitor'
      };
    });

    const activeSet = new Set();
    patches.forEach(p => p.cells.forEach(c => activeSet.add(`${c.x},${c.y}`)));

    return { patches, activeSet, rawFlagCount, thresholdGap };
  }

  function findPixelAtEvent(e) {
    // FIX: walk up the DOM to find the canvas — robust to future child overlays,
    // tooltips, or canvas wrapper divs placed inside the map container.
    let cv = e.target;
    while (cv && cv.tagName !== 'CANVAS') cv = cv.parentElement;
    if (!cv || !cv._g) return null;
    const g = cv._g;
    const r = cv.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left - g.ox) / g.cs) + DS.state.minx;
    const y = Math.floor((e.clientY - r.top - g.oy) / g.cs) + DS.state.miny;
    return monthData(DS.state.cur).find(d => d.x === x && d.y === y) || null;
  }

  DS.data = {
    getJSON,
    generateFallbackData,
    generateFallbackResults,
    generateFallbackTrend,
    monthData,
    computeRange,
    clusterPatches,
    clusterPatchesCached,
    clearPatchCache,
    findPixelAtEvent
  };
    /* ---------- Memoization cache for clusterPatches ---------- */
  const _patchCache = new Map();

  function clusterPatchesCached(md, calibration, monthIdx) {
    const key = `${calibration}|${monthIdx}`;
    if (_patchCache.has(key)) return _patchCache.get(key);
    const res = clusterPatches(md, calibration);
    _patchCache.set(key, res);
    return res;
  }

  function clearPatchCache() {
    _patchCache.clear();
  }
})();