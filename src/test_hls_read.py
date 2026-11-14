import os
import earthaccess
import rioxarray
import rasterio

earthaccess.login(strategy="interactive", persist=True)

bbox = (30.378, 30.565, 30.482, 30.655)  # min_lon, min_lat, max_lon, max_lat
granules = earthaccess.search_data(
    short_name="HLSL30",
    bounding_box=bbox,
    temporal=("2024-06-01", "2024-06-30"),
)
print(f"granules found: {len(granules)}")
assert len(granules) > 0

granule = granules[0]
data_urls = [item["URL"] for item in granule["umm"]["RelatedUrls"]]
nir_url = next(u for u in data_urls if u.endswith("B05.tif") and u.startswith("https"))
print("NIR asset:", nir_url[:90], "...")

# Absolute cookie path — critical on Windows
cookie_file = os.path.abspath("cookies.txt")

gdal_config = {
    "GDAL_HTTP_COOKIEFILE": cookie_file,
    "GDAL_HTTP_COOKIEJAR": cookie_file,
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "TIF",
    "GDAL_HTTP_UNSAFESSL": "YES",
    "GDAL_HTTP_MAX_RETRY": "10",
    "GDAL_HTTP_RETRY_DELAY": "0.5",
    "VSI_CACHE": "FALSE",
}

with rasterio.Env(**gdal_config):
    with rioxarray.open_rasterio(nir_url, chunks=True, lock=False) as da:
        print("shape:", da.shape, "| CRS:", da.rio.crs, "| nodata:", da.rio.nodata)
        window = da.isel(x=slice(0, 100), y=slice(0, 100)).compute()
        print("window shape:", window.shape)
        print("window stats: min=", float(window.min()), "max=", float(window.max()))