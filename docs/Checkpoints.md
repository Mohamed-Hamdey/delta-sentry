CHECKPOINT P0
- Hours used / remaining:           ~2.5 h / ~7.5 h (pre-event budget)
- Earthdata:                        verified and reading protected LP DAAC assets
- HLS read test:                    PASS — windowed 100x100 read, 8 granules, EPSG:32636
- Prithvi forward pass:             PASS — peak VRAM 1862 MiB / 6144 MiB
- TerraTorch:                       1.1.1, all v2 backbones registered incl. eo_v2_300_tl
- Band order confirmed:             BLUE, GREEN, RED, NIR_NARROW, SWIR_1, SWIR_2
- AOI decision:                     D-001 = Beheira (A), frozen
- Official challenge page:          pending 09:00
- Environment fixes logged:         numpy 1.26.4, pyarrow 20.0.0, numexpr 2.10.2,
                                    torch 2.6.0+cu124, affine 2.3.1
- Files created:                    config/aoi.yaml, config/splits.yaml, constraints.txt,
                                    docs/environment.md, docs/decision-log.md,
                                    src/acquire.py, src/test_hls_read.py
- Problems or surprises:            resolved (see environment.md)
- Questions:                        none