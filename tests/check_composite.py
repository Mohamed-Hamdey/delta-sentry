import rasterio, numpy as np
d = rasterio.open("data/processed/composites/202406.tif")
a = d.read()
print("shape:", a.shape, "| crs:", d.crs)
for i, name in enumerate(["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]):
    p5, p50, p95 = np.nanpercentile(a[i], [5, 50, 95])
    n_nan = int(np.isnan(a[i]).sum())
    print(f"{name:6s}: p5={p5:7.0f} p50={p50:7.0f} p95={p95:7.0f} NaN={n_nan}")