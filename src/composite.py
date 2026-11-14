"""
Build monthly median composites + valid-count layers for the frozen AOI.
Output:
  data/processed/composites/{YYYYMM}.tif  — 6-band float32, NaN = nodata
  data/processed/valid_count/{YYYYMM}.tif — 1-band uint16, count of clear obs

Usage:
  python src/composite.py             # all months
  python src/composite.py 2024-06     # one month (for QA)
"""
import sys
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import earthaccess
import numpy as np
import pandas as pd
import rasterio
import rioxarray

from utils import REPO_ROOT, aoI_extent_utm, load_yaml, GDAL_CONFIG

import time

MAX_WORKERS = 2                # was 8 — this is the single most important change
READ_RETRIES = 3
RETRY_DELAYS = (3, 10, 25)     # seconds between attempts

PRITHVI_BANDS = ["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"]
MAX_WORKERS = 8
MIN_CLEAR_FRACTION = 0.02


def clear_aws_env():
    """Remove any stale AWS env vars so GDAL does not use invalid keys."""
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION"):
        os.environ.pop(var, None)


def get_raster_env(edl_token: str) -> dict:
    """HTTPS-only Earthdata auth using Bearer token (no netrc parsing)."""
    env = dict(GDAL_CONFIG)
    env["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {edl_token}"
    # Bearer token replaces netrc/cookie auth — remove the broken paths
    env.pop("GDAL_HTTP_NETRC", None)
    env.pop("GDAL_HTTP_NETRC_FILE", None)
    env.pop("GDAL_HTTP_COOKIEFILE", None)
    env.pop("GDAL_HTTP_COOKIEJAR", None)
    return env


def sanitize_url(url: str) -> str:
    """Normalize any HLS URL to LP DAAC HTTPS.
    s3://lp-prod-protected/PATH -> https://data.lpdaac.../lp-prod-protected/PATH
    """
    if url.startswith("s3://"):
        path = url.replace("s3://", "", 1)  # keep bucket name in path
        return f"https://data.lpdaac.earthdatacloud.nasa.gov/{path}"
    return url


def read_window(url: str, aoi_bounds: tuple, env_kwargs: dict) -> np.ndarray:
    """Read AOI window with retries. LP DAAC throttles parallel HTTPS reads;
    GDAL caches the resulting 'not supported file format' error, so we must
    retry with backoff rather than trusting the first failure."""
    final_url = sanitize_url(url)
    last_err = None

    for attempt in range(READ_RETRIES):
        if attempt > 0:
            time.sleep(RETRY_DELAYS[attempt - 1])
        try:
            with rasterio.Env(**env_kwargs):
                with rioxarray.open_rasterio(final_url, chunks={}, lock=False) as da:
                    epsg = da.rio.crs.to_epsg(confidence_threshold=60) if da.rio.crs else None
                    if epsg != 32636:
                        raise ValueError(f"Unexpected CRS (EPSG {epsg}) in {final_url}")
                    minx, miny, maxx, maxy = aoi_bounds
                    clipped = da.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy)
                    data = clipped.isel(band=0).values.astype(np.float32)
                    if da.rio.nodata is not None:
                        data = np.where(data == da.rio.nodata, np.nan, data)
                    return data
        except Exception as e:
            last_err = e

    raise RuntimeError(f"read failed after {READ_RETRIES} attempts: {final_url}") from last_err

def clear_mask(fmask: np.ndarray) -> np.ndarray:
    """HLS Fmask: bit 6 = clear land."""
    if np.isnan(fmask).all():
        return np.zeros(fmask.shape, dtype=bool)
    fmask_u8 = np.nan_to_num(fmask, nan=0).astype(np.uint8)
    return (fmask_u8 & 0b01000000) != 0


def month_composite(year: int, month: int, manifest: pd.DataFrame,
                    aoi_bounds: tuple, env_kwargs: dict):
    """Build (6-band median, valid_count) for one month."""
    rows = manifest[(manifest["year"] == year) & (manifest["month"] == month)]
    if len(rows) == 0:
        return None, None

    fmask_futures = {}
    band_futures = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for i, (_, row) in enumerate(rows.iterrows()):
            if i > 0:
                time.sleep(1.5)          # NEW — pace the submissions
            gid = row["granule_id"]
            if row["QA_url"]:
                fmask_futures[ex.submit(read_window, row["QA_url"],
                                        aoi_bounds, env_kwargs)] = gid
            for b in PRITHVI_BANDS:
                url = row[f"{b}_url"]
                if url:
                    band_futures[ex.submit(read_window, url,
                                           aoi_bounds, env_kwargs)] = (gid, b)

    clear_by_granule = {}
    for f in as_completed(fmask_futures):
        gid = fmask_futures[f]
        try:
            clear_by_granule[gid] = clear_mask(f.result())
        except Exception as e:
            print(f"  warn: Fmask read failed for {gid}: {e}")
            clear_by_granule[gid] = None

    grid_shape = None
    for m in clear_by_granule.values():
        if m is not None:
            grid_shape = m.shape
            break
    if grid_shape is None:
        return None, None

    band_stacks = {b: [] for b in PRITHVI_BANDS}
    for f in as_completed(band_futures):
        gid, band = band_futures[f]
        try:
            arr = f.result()
        except Exception as e:
            print(f"  warn: {band} read failed for {gid}: {e}")
            continue
        if arr.shape != grid_shape:
            print(f"  warn: {band} shape {arr.shape} != {grid_shape} for {gid}")
            continue
        cm = clear_by_granule.get(gid)
        if cm is not None:
            arr = np.where(cm, arr, np.nan)
        band_stacks[band].append(arr)

    comp = np.full((len(PRITHVI_BANDS),) + grid_shape, np.nan, dtype=np.float32)
    valid_count = np.zeros(grid_shape, dtype=np.uint16)
    for i, b in enumerate(PRITHVI_BANDS):
        if not band_stacks[b]:
            continue
        stack = np.stack(band_stacks[b], axis=0)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            comp[i] = np.nanmedian(stack, axis=0)
        if i == 0:
            valid_count = np.sum(~np.isnan(stack), axis=0).astype(np.uint16)

    return comp, valid_count


def write_cog(path: Path, data: np.ndarray, transform, crs: str, nodata, dtype: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "tiled": True, "compress": "deflate",
        "width": data.shape[-1], "height": data.shape[-2],
        "count": 1 if data.ndim == 2 else data.shape[0],
        "dtype": dtype, "crs": crs, "transform": transform, "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        if data.ndim == 2:
            dst.write(data, 1)
        else:
            dst.write(data)


def main():
    clear_aws_env()
    import os
    os.environ["EARTHDATA_USERNAME"] = "hamdey14112"
    os.environ["EARTHDATA_PASSWORD"] = "Space_Challenge_2026_Mohamed_hamdey@#1298"
    auth = earthaccess.login(strategy="environment", persist=False)
    edl_token = auth.token["access_token"]
    print(f"EDL token acquired (expires {auth.token.get('expires_at', 'unknown')})")
    print("Read mode: HTTPS via vsicurl (Earthdata cookie auth)")

    env_kwargs = get_raster_env(edl_token)
    manifest = pd.read_csv(REPO_ROOT / "data" / "interim" / "granule_manifest.csv")
    aoi_bounds = aoI_extent_utm()

    # Filter to the dominant MGRS tile — the AOI straddles T36RTV/T36RTU
    tiles = manifest["granule_id"].str.extract(r"\.(T\d{2}[A-Z]{3})\.")[0]
    dominant = tiles.value_counts().idxmax()
    n_before = len(manifest)
    manifest = manifest[tiles == dominant].reset_index(drop=True)
    print(f"Filtered to dominant tile {dominant}: {len(manifest)}/{n_before} granules")

    # Guard: every month needs at least 2 granules for a meaningful median
    per_month = manifest.groupby(["year", "month"]).size()
    thin = per_month[per_month < 2]
    if len(thin) > 0:
        print("WARNING — months with <2 granules in dominant tile:")
        print(thin.to_string())

    qa_urls = manifest["QA_url"].dropna().astype(str)
    qa_urls = qa_urls[qa_urls.str.len() > 0]
    if len(qa_urls) == 0:
        raise RuntimeError("QA_url column empty — run acquire.py first")

    first_url = sanitize_url(qa_urls.iloc[0])

    with rasterio.Env(**env_kwargs):
        with rioxarray.open_rasterio(first_url, chunks={}, lock=False) as da:
            epsg = da.rio.crs.to_epsg(confidence_threshold=60) if da.rio.crs else None
            if epsg != 32636:
                raise RuntimeError(f"Unexpected CRS (EPSG {epsg}) for {first_url}")
            minx, miny, maxx, maxy = aoi_bounds
            clipped = da.rio.clip_box(minx=minx, miny=miny, maxx=maxx, maxy=maxy)
            transform = clipped.rio.transform()
            out_crs = "EPSG:32636"

  

    # Month filter — supports "YYYY-MM" or "YYYY-MM YYYY-MM" range
    if len(sys.argv) > 1:
        start = sys.argv[1]
        end = sys.argv[2] if len(sys.argv) > 2 else start
        sy, sm = map(int, start.split("-"))
        ey, em = map(int, end.split("-"))
        months = [(y, m) for (y, m) in sorted(manifest.groupby(["year", "month"]).groups.keys())
                  if (sy, sm) <= (y, m) <= (ey, em)]
    else:
        months = sorted(manifest.groupby(["year", "month"]).groups.keys())

    comp_dir = REPO_ROOT / "data" / "processed" / "composites"
    count_dir = REPO_ROOT / "data" / "processed" / "valid_count"
    summary = []

    for year, month in months:
        comp_path = comp_dir / f"{year}{month:02d}.tif"
        if comp_path.exists():
            print(f"{year}-{month:02d}: already exists, skipping")
            summary.append({"year": year, "month": month, "valid_frac": -1.0})
            continue
        comp, vcount = month_composite(year, month, manifest, aoi_bounds, env_kwargs)
        if comp is None:
            print(f"{year}-{month:02d}: NO DATA")
            summary.append({"year": year, "month": month, "valid_frac": 0.0})
            continue
        frac = float((vcount > 0).mean())
        n_clear = int((vcount > 0).sum())
        print(f"{year}-{month:02d}: valid_frac={frac:.3f} ({n_clear} px)")
        if frac < MIN_CLEAR_FRACTION:
            print(f"  skip: below MIN_CLEAR_FRACTION={MIN_CLEAR_FRACTION}")
            summary.append({"year": year, "month": month, "valid_frac": frac})
            continue
        write_cog(comp_dir / f"{year}{month:02d}.tif", comp, transform, out_crs, np.nan, "float32")
        write_cog(count_dir / f"{year}{month:02d}.tif", vcount, transform, out_crs, 65535, "uint16")
        summary.append({"year": year, "month": month, "valid_frac": frac})

    summary_path = REPO_ROOT / "reports" / "composite_summary.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary).to_csv(summary_path, index=False)
    print(f"\nWrote {len(summary)} months to {comp_dir}")


if __name__ == "__main__":
    main()