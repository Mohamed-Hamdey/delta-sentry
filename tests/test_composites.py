# tests/test_composites.py
"""Unit tests for the composite product. Run: pytest tests/test_composites.py -v"""
import numpy as np
import rasterio
from pathlib import Path

COMP = Path("data/processed/composites/202406.tif")
COUNT = Path("data/processed/valid_count/202406.tif")


def test_file_exists():
    assert COMP.exists(), "Run src/composite.py 2024-06 first"
    assert COUNT.exists()


def test_shape_and_crs():
    with rasterio.open(COMP) as src:
        assert src.count == 6, f"expected 6 bands, got {src.count}"
        assert src.crs.to_epsg() == 32636, f"expected EPSG:32636, got {src.crs}"
        assert src.height > 200 and src.width > 200, "AOI unexpectedly small"


def test_band_order_nir_gt_red():
    """Cropland in June: NIR median must exceed RED median."""
    with rasterio.open(COMP) as src:
        bands = {name: src.read(i + 1) for i, name in
                 enumerate(["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"])}
    nir_p50 = float(np.nanmedian(bands["NIR"]))
    red_p50 = float(np.nanmedian(bands["RED"]))
    assert nir_p50 > red_p50, f"NIR ({nir_p50:.0f}) ≤ RED ({red_p50:.0f}) — band order suspect"


def test_reflectance_range():
    """HLS DN should be mostly in [0, 20000].
    Small negatives (down to -1000 DN, i.e. -0.1 reflectance) are documented
    artifacts of atmospheric correction and are clipped in the P2 dataset builder.
    """
    with rasterio.open(COMP) as src:
        a = src.read()
    valid = a[~np.isnan(a)]
    assert valid.min() >= -1000, f"unexpected negative reflectance: {valid.min():.0f}"
    assert valid.max() <= 20000, f"unexpectedly high DN: {valid.max():.0f}"

    # Document how widespread the artifact is — printed, not asserted
    n_neg = int((valid < 0).sum())
    frac_neg = n_neg / valid.size
    print(f"  negatives: {n_neg} pixels ({frac_neg:.4%}), min={valid.min():.0f}")


def test_valid_count_matches_composite():
    """Pixels with valid_count=0 must be NaN in every band."""
    with rasterio.open(COMP) as src:
        comp = src.read()
    with rasterio.open(COUNT) as src:
        vc = src.read(1)
    nodata_mask = vc == 0
    if nodata_mask.any():
        for band in range(comp.shape[0]):
            assert np.all(np.isnan(comp[band][nodata_mask])), \
                f"Band {band} has data where valid_count=0"