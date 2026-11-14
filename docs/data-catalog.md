## HLS L30 coverage notes (2026-11-13)
- Thin months flagged for composite QA: 2020-10 (2 granules),
  2021-01 (1), 2021-07 (2), 2021-08 (2)
- Validation (2024) and test (2025) are healthy (≥4 granules every month)
- Decision: proceed L30-only; add HLSS30 fill only if composite shows <20%
  valid coverage in any training month (D-002b trigger)

## MGRS tile notes
- AOI straddles T36RTV and T36RTU.
- Composite pipeline uses T36RTV only (D-001c).
- T36RTU granules cover only the southern ~128 rows of the AOI.
- Southern ~3.8 km of AOI will appear as NaN ("no data") in the composite.

## Known data characteristics
- HLS L30 v2.0 surface reflectance can contain **small negative values**
  (approximately -1000 to 0 DN, i.e. -0.1 to 0 reflectance). Source:
  atmospheric correction at high aerosol loading, over dark water, and in
  partial shadow.
- The Fmask "clear" bit does not exclude these pixels — atmospheric correction
  happens downstream of cloud masking.
- **Composite pipeline leaves them unclipped** so the record is honest.
- **P2 dataset builder** clamps reflectance to [0, 10000] before Prithvi
  normalization (see decision N-009).

## MGRS tile and coverage
- AOI straddles T36RTV and T36RTU. Composite pipeline uses **T36RTU** (217/417 granules; full 326×341 AOI coverage).
- T36RTV provides only a 128-row southern strip — excluded.
- Thin months in T36RTU: 2020-10, 2021-07, 2021-08 (1 granule each) — check full-run `valid_frac` before deciding D-002b.
- Composite CRS: EPSG:32636. Reflectance DN 0–10000, with small negatives down to -1000 from atmospheric correction (D-009).