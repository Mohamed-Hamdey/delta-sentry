# DELTA SENTRY

An early-warning "trend detective" for Nile Delta vegetation. We fine-tune NASA/IBM
Prithvi-EO to forecast next-month vegetation from recent HLS imagery, then flag where
reality falls well below both the forecast and the seasonal norm — with a range,
associated signals, and stated limitations.

**Challenge:** Be An Earth System Trend Detective — NASA Space Apps 2026 (Cairo).
**Status:** pre-event preparation. No results yet; every number in this repo will
trace to a saved output and a manifest.

## Layout
- `config/` — AOI, time split, model and threshold settings (frozen settings are logged)
- `src/` — pipeline: acquire -> composite -> dataset -> baselines -> train -> detect -> context -> export
- `docs/` — environment, decision log, data catalog, AI-use log, claims register
- `site/` — static offline dashboard reading precomputed files
- `reports/` — metrics tables, audit, results.md

## Data & attribution
HLS, NASA POWER, SMAP (optional), Prithvi-EO-2.0 (NASA/IBM and partners), TerraTorch.
Full citations and licences in `docs/data-catalog.md` and the dashboard Methods page.
No NASA endorsement is implied.