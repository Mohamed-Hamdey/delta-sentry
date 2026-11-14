# src/dataset.py
"""Build 4-frame -> t+1 sample index from monthly composites."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from utils import REPO_ROOT, load_yaml

PRITHVI_BANDS = ["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"]
N_FRAMES = 4
CHIP_SIZE = 224
STRIDE = 64
CLIP_MIN, CLIP_MAX = 0.0, 10000.0
MIN_VALID_PIXELS = 1
MIN_VALID_TARGET_PIXELS = 100


def load_composite(year: int, month: int) -> np.ndarray | None:
    path = REPO_ROOT / "data" / "processed" / "composites" / f"{year}{month:02d}.tif"
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        return src.read().astype(np.float32)


def clip_reflectance(arr: np.ndarray) -> np.ndarray:
    arr = np.nan_to_num(arr, nan=0.0, posinf=CLIP_MAX, neginf=CLIP_MIN)
    return np.clip(arr, CLIP_MIN, CLIP_MAX) / CLIP_MAX

def ndvi_from_composite(comp: np.ndarray) -> np.ndarray:
    red = np.clip(comp[2], CLIP_MIN, CLIP_MAX)
    nir = np.clip(comp[3], CLIP_MIN, CLIP_MAX)
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / (nir + red)
    ndvi = np.clip(ndvi, -1.0, 1.0).astype(np.float32)
    ndvi[~np.isfinite(ndvi)] = np.nan
    return ndvi


def valid_frame(comp: np.ndarray) -> bool:
    return int(np.sum(~np.isnan(comp[0]))) >= MIN_VALID_PIXELS


def build_sample_index(years: list[int]) -> pd.DataFrame:
    rows = []
    for year in years:
        for month in range(1, 13):
            ty, tm = (year, month + 1) if month < 12 else (year + 1, 1)
            target = load_composite(ty, tm)
            if target is None:
                continue
            ndvi = ndvi_from_composite(target)
            # Inputs: t-3, t-2, t-1, t
            inputs, ok = [], True
            for k in (3, 2, 1, 0):
                iy, im = year, month - k
                while im < 1:
                    im += 12
                    iy -= 1
                comp = load_composite(iy, im)
                if comp is None or not valid_frame(comp):
                    ok = False
                    break
                inputs.append(comp)
            if not ok:
                continue
            h, w = ndvi.shape
            for cy in range(0, h - CHIP_SIZE + 1, STRIDE):
                for cx in range(0, w - CHIP_SIZE + 1, STRIDE):
                    tc = ndvi[cy:cy+CHIP_SIZE, cx:cx+CHIP_SIZE]
                    if int(np.sum(~np.isnan(tc))) < MIN_VALID_TARGET_PIXELS:
                        continue
                    rows.append({
                        "year": year, "month": month,
                        "target_year": ty, "target_month": tm,
                        "chip_y": cy, "chip_x": cx,
                    })
    return pd.DataFrame(rows)


def load_chip(inputs: list[np.ndarray], target_ndvi: np.ndarray,
              cy: int, cx: int) -> tuple[np.ndarray, np.ndarray]:
    """(6, N_FRAMES, CHIP, CHIP) float32 inputs; (CHIP, CHIP) float32 target."""
    x = np.stack(
        [clip_reflectance(c[:, cy:cy+CHIP_SIZE, cx:cx+CHIP_SIZE]) for c in inputs],
        axis=1,
    )
    y = target_ndvi[cy:cy+CHIP_SIZE, cx:cx+CHIP_SIZE]
    return x, y


def main():
    cfg = load_yaml("config/splits.yaml")
    splits = {
        "train": cfg["years"]["train"],
        "val": cfg["years"]["validation"],
        "test": cfg["years"]["test"],
    }
    out_dir = REPO_ROOT / "data" / "processed" / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, years in splits.items():
        df = build_sample_index(years)
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        print(f"{name}: {len(df)} samples -> {path}")


if __name__ == "__main__":
    main()