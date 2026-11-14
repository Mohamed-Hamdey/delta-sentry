# src/appeears_to_composite.py
import xarray as xr
import numpy as np
import rioxarray
from pathlib import Path
import pandas as pd
import rasterio
import warnings
from collections import defaultdict
from utils import REPO_ROOT

RAW_DIR = REPO_ROOT / "data" / "raw" / "appeears"
OUT_DIR = REPO_ROOT / "data" / "processed" / "composites"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Standardized bands expected by Prithvi
STD_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07"] 

def get_standard_band(ds, std_band):
    """Maps L30 and S30 naming conventions to standard names."""
    if std_band == "B05":  # NIR
        return "B8A" if "B8A" in ds else "B05"
    if std_band == "B06":  # SWIR1
        return "B11" if "B11" in ds else "B06"
    if std_band == "B07":  # SWIR2
        return "B12" if "B12" in ds else "B07"
    return std_band

def process_all_nc_files():
    nc_files = sorted(list(RAW_DIR.glob("*.nc")))
    if not nc_files:
        print("No .nc files found in data/raw/appeears/")
        return

    monthly_data = defaultdict(list)
    spatial_ref = None

    print(f"Found {len(nc_files)} NetCDF files. Processing...")
    
    for nc_path in nc_files:
        print(f"  Reading {nc_path.name}...")
        
        try:
            ds = xr.open_dataset(nc_path)
        except Exception as e:
            print(f"    ERROR: Could not open {nc_path.name}: {e}")
            continue
        
        # --- VALIDATION CHECK ---
        # Check if the file actually contains all the bands we need
        required_vars = ["Fmask"]
        for b in STD_BANDS:
            required_vars.append(get_standard_band(ds, b))
            
        missing_vars = [v for v in required_vars if v not in ds]
        if missing_vars:
            print(f"    ⚠️ WARNING: Skipping {nc_path.name}. Missing bands: {missing_vars}")
            print(f"    Available bands in this file: {list(ds.data_vars)}")
            continue # Skip this broken file and move to the next one
        # ------------------------

        # Capture spatial reference from the first valid file
        if spatial_ref is None:
            spatial_ref = {
                "crs": ds.rio.crs,
                "transform": ds.rio.transform(),
                "shape": (ds.rio.height, ds.rio.width) 
            }
        
        # Apply Fmask (bit 6 = clear land)
        fmask = ds["Fmask"].fillna(0).astype(np.uint16)
        clear_mask = (fmask & 0b01000000) != 0
        
        # Extract time dimension
        time_dim = "time" if "time" in ds.dims else "Date"
        
        for i in range(len(ds[time_dim])):
            # Robustly extract the date (handles cftime strings)
            time_val = ds[time_dim].values[i]
            while isinstance(time_val, np.ndarray) and time_val.size > 0:
                time_val = time_val[0]
            date = pd.to_datetime(str(time_val))
            month_key = f"{date.year}{date.month:02d}"
            
            day_bands = []
            for std_band in STD_BANDS:
                actual_band = get_standard_band(ds, std_band)
                # Ensure band is float32 so we can insert NaNs
                band_data = ds[actual_band].isel({time_dim: i}).values.astype(np.float32)
                # Mask out clouds
                band_data = np.where(clear_mask.isel({time_dim: i}).values, band_data, np.nan)
                day_bands.append(band_data)
                
            monthly_data[month_key].append(np.stack(day_bands))

    if not monthly_data:
        print("\nNo valid data found to composite.")
        return

    print(f"\nFound data for {len(monthly_data)} unique months. Building composites...")
    
    for month_key, daily_stacks in sorted(monthly_data.items()):
        # Stack all days in this month: shape becomes (num_days, 6, y, x)
        stack = np.stack(daily_stacks, axis=0)
        
        # Take the median across the days for each band
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            comp = np.nanmedian(stack, axis=0)
        
        if np.all(np.isnan(comp)):
            print(f"  {month_key}: 100% clouds, skipping.")
            continue
            
        out_path = OUT_DIR / f"{month_key}.tif"
        
        profile = {
            "driver": "GTiff", "height": spatial_ref["shape"][0], "width": spatial_ref["shape"][1],
            "count": 6, "dtype": "float32", "crs": spatial_ref["crs"],
            "transform": spatial_ref["transform"], "nodata": np.nan, "compress": "deflate"
        }
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(comp)
            
        print(f"  {month_key}: Successfully merged {len(daily_stacks)} observations.")

if __name__ == "__main__":
    process_all_nc_files()