## Prithvi-EO-2.0-300M-TL — verified fields

- Band order: BLUE, GREEN, RED, NIR_NARROW, SWIR_1, SWIR_2
  (confirmed by smoke-test weight-loading log, P0.5)
- HLS band mapping:
  - BLUE = B02, GREEN = B03, RED = B04, NIR_NARROW = B8A, SWIR_1 = B11, SWIR_2 = B12
- Normalization (per-band mean, reflectance 0–10000):
  [1087, 1342, 1433, 2734, 1958, 1363]
  Source: Prithvi-EO-2.0 model card (verify against the exact checkpoint card before P2)
- Patch size: 16
- Input size: 224 × 224, up to 4 frames
- TL embeddings: temporal (year + Julian day) and location (lat/lon)
- License: Apache-2.0
- TerraTorch handles normalization when pretrained=True; manual normalization
  only needed when building raw arrays in P2.


# Prithvi-EO-2.0 notes

## Checkpoint
- Name: `terratorch_prithvi_eo_v2_300_tl` (transfer‑learning variant, uses temporal + location embeddings)
- Weights: `ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL` on Hugging Face
- License: Apache-2.0
- Loaded by TerraTorch `BACKBONE_REGISTRY` (confirmed P0.5)

## Bands (positions confirmed by smoke-test log)
1. BLUE  (B02)
2. GREEN (B03)
3. RED   (B04)
4. NIR_NARROW (B05 in HLSL30, B8A in HLSS30)
5. SWIR_1 (B06 in HLSL30, B11 in HLSS30)
6. SWIR_2 (B07 in HLSL30, B12 in HLSS30)

## Normalization
Per-band mean (reflectance DN 0–10000), order BLUE→SWIR_2:
`[1087, 1342, 1433, 2734, 1958, 1363]`
Standard deviation: <fill from model card — verify against checkpoint card before P2>

## Input
- Patch: 16×16, 224×224 chips, up to 4 frames
- Temporal embedding: year + Julian day (optional)
- Location embedding: lat/lon (optional)
- Output: list of intermediate feature maps — decoder required (P3)

## TerraTorch
- Version: 1.1.1
- Task type for pixel‑wise regression: <fill in P3>
- Config format: <fill in P3>
- Python 3.12.7 on Windows: works (confirmed P0.5)