import xarray as xr
import os

# Update this path if you named the file differently
file_path = "data/raw/appeears/HLS_L30_chunk1.nc" 

if not os.path.exists(file_path):
    print(f"File not found at {file_path}. Please check the path.")
else:
    print("Opening file...")
    ds = xr.open_dataset(file_path)
    
    print("\n=== DIMENSIONS ===")
    print(ds.dims)
    
    print("\n=== DATA VARIABLES (BANDS) ===")
    for var in ds.data_vars:
        print(f"- {var}: {ds[var].attrs.get('long_name', 'No description')}")
        
    print("\n=== TIME RANGE ===")
    print(f"Start: {ds.time.min().values}")
    print(f"End:   {ds.time.max().values}")
    print(f"Total time steps: {len(ds.time)}")