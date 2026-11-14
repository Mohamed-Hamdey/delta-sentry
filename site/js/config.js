window.DS = window.DS || {};

DS.CONFIG = {

  /* ------------------------------------------------------------------
     GEOREFERENCING
     Keep the north-west corner + pixel size as the source of truth and
     derive south/east from the grid at runtime (main.js). A hand-typed
     box drifts the moment the AOI or the chip size changes, and every
     printed coordinate drifts with it.
     ------------------------------------------------------------------ */
  AOI: {
    name: 'Kafr El-Sheikh North',
    region: 'Kafr El-Sheikh',
    regionAr: 'كفر الشيخ',
    northWest: { lat: 31.30, lon: 30.72 },
    pixelM: 30,
    // Derived at runtime from gx/gy; this is the 128 × 102 fallback.
    bounds: { north: 31.30, south: 31.2725, west: 30.72, east: 30.7603 }
  },

  dataUrl: 'data/dashboard_data.json',
  resultsUrl: 'data/results.json',
  trendUrl: 'data/trend.json',

  /* ------------------------------------------------------------------
     LIVE INFERENCE — Hugging Face Space
     baseUrl: the Space's direct URL, e.g.
       https://<owner>-<space-name>.hf.space
     The Space must expose POST /infer and GET /job/{id} with CORS open
     (see app.py in this folder).
     Set enabled:false to hide the Try Model section entirely.
     ------------------------------------------------------------------ */
  INFERENCE: {
    enabled: true,
    baseUrl: 'https://mohamedhamdey-delta-sentry-v2.hf.space/api',
    pollMs: 1200,
    requestTimeoutMs: 15000,
    maxRunMs: 180000,
    // If the Space sleeps, 503s, or blocks CORS, fall back to the cached
    // pipeline result and label it clearly. A demo must never dead-end.
    demoFallback: true,
    prewarm: true
  },

  credits: [
    'Prithvi-EO-2.0-300M-TL (NASA / IBM)',
    'Harmonized Landsat Sentinel-2 (NASA HLS)',
    'AppEEARS time-series extraction',
    'MODIS MOD13Q1 (2000–2025)',
    '44-patch imagery audit'
  ]
};

DS.CONSTANTS = {
  PIXEL_HA: 0.09,       // 30 m × 30 m = 900 m²
  PIXEL_FEDDAN: 0.2143  // 900 m² / 4200 m²
};

DS.utils = {
  $: s => document.querySelector(s),
  $$: s => document.querySelectorAll(s),
  key: d => d.year + '-' + String(d.month).padStart(2, '0'),
  isFlag: d => d.flag === 'Anomaly',
  f3: v => (v == null || isNaN(v)) ? 'n/a' : Number(v).toFixed(3),
  clamp: (v, a, b) => Math.max(a, Math.min(b, v))
};

DS.state = {
  data: [], months: [], cur: 0, patches: [], selPatch: null, selPixel: null,
  calibration: 'top5', stageState: 'observe', minx: 0, miny: 0, gx: 1, gy: 1,
  layerRange: { min: 0.05, max: 0.65 }, playTimer: null, playing: false
};
