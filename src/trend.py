# src/trend.py
import xarray as xr
import numpy as np
import pandas as pd
import pymannkendall as mk
from statsmodels.stats.multitest import multipletests
import json
from pathlib import Path
from utils import REPO_ROOT

RAW_DIR = REPO_ROOT / "data" / "raw" / "appeears"
OUT_JSON = REPO_ROOT / "site" / "data" / "trend.json"
ALPHA = 0.05

def process_modis_trend():
    print("Processing MODIS 25-Year Trend...")
    modis_files = list(RAW_DIR.glob("MOD13Q*.nc"))
    
    if not modis_files:
        print("No MODIS files found in data/raw/appeears/")
        return
        
    # Load all MODIS chunks into one dataset
    ds = xr.open_mfdataset(modis_files)
    
    # Select NDVI and Quality
    ndvi = ds["_250m_16_days_NDVI"].values
    quality = ds["_250m_16_days_pixel_reliability"].values
    
    # Mask low quality (0 = Good data, 1 = Marginal, 2 = Snow/Ice, 3 = Cloudy)
    ndvi = np.where(quality == 0, ndvi, np.nan)
    
    # Apply scale factor (MODIS NDVI is scaled by 10000)
    ndvi = ndvi * 0.0001
    
    # Get dimensions
    time_steps, height, width = ndvi.shape
    print(f"Found {time_steps} time steps, {height}x{width} grid.")
    
    # Flatten spatial dimensions to 1D for looping
    ndvi_flat = ndvi.reshape(time_steps, -1)
    n_pixels = ndvi_flat.shape[1]
    
    slopes = np.full(n_pixels, np.nan)
    p_values = np.full(n_pixels, np.nan)
    
    # Run Mann-Kendall per pixel
    for i in range(n_pixels):
        series = ndvi_flat[:, i]
        # Drop NaNs to handle missing months
        series = series[~np.isnan(series)]
        
        if len(series) < 100: # Require at least 10 years of data
            continue
            
        try:
            # Seasonal test assumes monthly data with a 12-month cycle
            res = mk.seasonal_test(series, period=12)
            slopes[i] = res.slope * 12 # Convert to per-year slope
            p_values[i] = res.p
        except Exception:
            pass

    # FDR Correction
    valid = ~np.isnan(p_values)
    sig = np.zeros(n_pixels, dtype=bool)
    if valid.any():
        _, p_fdr, _, _ = multipletests(p_values[valid], alpha=ALPHA, method='fdr_bh')
        sig[valid] = p_fdr < ALPHA

    # Classify pixels
    decline = np.sum((slopes < 0) & sig)
    increase = np.sum((slopes > 0) & sig)
    none = np.sum(~sig)

    total_valid = decline + increase + none
    
    results = {
        "method": "Seasonal Mann-Kendall + FDR",
        "alpha": ALPHA,
        "decline_pct": round((decline / total_valid) * 100, 2),
        "increase_pct": round((increase / total_valid) * 100, 2),
        "none_pct": round((none / total_valid) * 100, 2)
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"Trend Analysis Complete: {results}")

if __name__ == "__main__":
    process_modis_trend()