# src/utils.py
"""Shared utilities: GDAL config, AOI grid, manifest helpers."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COOKIE_FILE = str(REPO_ROOT / "cookies.txt")

# Netrc path — on Windows GDAL looks for _netrc (underscore)
NETRC_FILE = os.path.expanduser("~/_netrc")

GDAL_CONFIG = {
    "GDAL_HTTP_COOKIEFILE": COOKIE_FILE,
    "GDAL_HTTP_COOKIEJAR": COOKIE_FILE,
    "GDAL_HTTP_NETRC": "YES",
    "GDAL_HTTP_NETRC_FILE": NETRC_FILE,
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": "TIF",
    "CPL_VSIL_CURL_USE_HEAD": "FALSE",      # NEW — from working gdal-dev config
    "GDAL_HTTP_UNSAFESSL": "YES",
    "GDAL_HTTP_TIMEOUT": "120",             # NEW
    "GDAL_HTTP_CONNECTTIMEOUT": "30",       # NEW
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "FALSE",
}


def load_yaml(rel_path: str) -> dict:
    with open(REPO_ROOT / rel_path) as f:
        return yaml.safe_load(f)


def aoI_extent_utm() -> tuple:
    from pyproj import Transformer
    aoi = load_yaml("config/aoi.yaml")
    if aoi["selected"] is None:
        raise RuntimeError("AOI not frozen — fill config/aoi.yaml first")
    min_lon, min_lat, max_lon, max_lat = aoi["bbox_wgs84"]
    tr = Transformer.from_crs("EPSG:4326", aoi["crs_utm"], always_xy=True)
    x0, y0 = tr.transform(min_lon, min_lat)
    x1, y1 = tr.transform(max_lon, max_lat)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(product_path: Path, inputs: list, config_used: dict, extra: dict = None):
    manifest = {
        "product": str(product_path.relative_to(REPO_ROOT)),
        "sha256": file_sha256(product_path),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": [str(i) for i in inputs],
        "config": config_used,
        "extra": extra or {},
    }
    out = product_path.with_suffix(product_path.suffix + ".manifest.json")
    out.write_text(json.dumps(manifest, indent=2))
    return out