# src/baselines.py
"""Baselines B0 (climatology), B1 (persistence). B2/RF after B0/B1 are stable."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from dataset import (load_composite, ndvi_from_composite,
                         CHIP_SIZE)
from utils import REPO_ROOT, load_yaml


def climatology_per_month(train_years: list[int]) -> dict[int, np.ndarray]:
    by_month: dict[int, list[np.ndarray]] = {m: [] for m in range(1, 13)}
    for year in train_years:
        for month in range(1, 13):
            comp = load_composite(year, month)
            if comp is None:
                continue
            by_month[month].append(ndvi_from_composite(comp))
    clim: dict[int, np.ndarray] = {}
    for month, arrays in by_month.items():
        if not arrays:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clim[month] = np.nanmedian(np.stack(arrays, axis=0), axis=0)
    return clim


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2))) if m.any() else np.nan


def mae(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    return float(np.mean(np.abs(a[m] - b[m]))) if m.any() else np.nan


def evaluate_split(name: str, clim: dict[int, np.ndarray]) -> pd.DataFrame:
    samples = pd.read_parquet(
        REPO_ROOT / "data" / "processed" / "samples" / f"{name}.parquet")
    rows = []
    for _, s in samples.iterrows():
        target = load_composite(int(s["target_year"]), int(s["target_month"]))
        if target is None:
            continue
        y = ndvi_from_composite(target)[
            s["chip_y"]:s["chip_y"]+CHIP_SIZE, s["chip_x"]:s["chip_x"]+CHIP_SIZE]

        # B0: climatology
        b0 = clim[int(s["target_month"])][
            s["chip_y"]:s["chip_y"]+CHIP_SIZE,
            s["chip_x"]:s["chip_x"]+CHIP_SIZE]
        b0 = np.where(np.isfinite(b0), np.clip(b0, -1.0, 1.0), np.nan)

        iy, im = int(s["year"]), int(s["month"])
        current = load_composite(iy, im)
        if current is None:
            continue
        cur_ndvi = ndvi_from_composite(current)[
            s["chip_y"]:s["chip_y"]+CHIP_SIZE, s["chip_x"]:s["chip_x"]+CHIP_SIZE]
        cur_ndvi = np.where(np.isfinite(cur_ndvi), np.clip(cur_ndvi, -1.0, 1.0), np.nan)

        rows.append({"model": "B0_climatology",
                     "rmse": rmse(y, b0), "mae": mae(y, b0),
                     "n": int((~np.isnan(y) & ~np.isnan(b0)).sum())})
        rows.append({"model": "B1_persistence",
                     "rmse": rmse(y, cur_ndvi), "mae": mae(y, cur_ndvi),
                     "n": int((~np.isnan(y) & ~np.isnan(cur_ndvi)).sum())})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby("model").agg(
        {"rmse": "mean", "mae": "mean", "n": "sum"}).reset_index()


def main():
    cfg = load_yaml("config/splits.yaml")
    print(f"Building climatology from training years: {cfg['years']['train']}")
    clim = climatology_per_month(cfg["years"]["train"])

    for split in ("train", "val", "test"):
        try:
            df = evaluate_split(split, clim)
        except FileNotFoundError:
            print(f"skip {split}: sample parquet missing")
            continue
        out = REPO_ROOT / "reports" / f"baselines_{split}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\n=== {split} ===")
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()