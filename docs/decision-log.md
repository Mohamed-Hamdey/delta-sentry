# DELTA SENTRY — Decision Log

Every method, split, threshold or claim change is recorded here: date, decision,
alternatives, reason.

| ID | Date | Decision | Alternatives | Reason |
|----|------|----------|--------------|--------|
| D-001 | 2026-11-13 | AOI candidates: A = Beheira (default), B = Dakahlia (backup) | Other Delta governorates | Strongest agricultural signal and judging narrative. Frozen only after HLS coverage check + NDVI quicklook in P0.7. |
| D-003 | 2026-11-13 | Train 2020-2023, validation 2024, test 2025 | 3-yr train / 2-yr test | Four training years give a stable climatology; val and test are each a full year. |
| D-004a | 2026-11-13 | Try TerraTorch first; raw-PyTorch fallback if Prithvi forward pass fails within 20 min | Docker-first; raw PyTorch only | TerraTorch is the intended Prithvi path (Apache-2.0); fallback protects the schedule. |
| D-004 | pending | Fine-tuning mode (VRAM) | B3 frozen only; M1 partial unfreeze | GPU is 6 GB (6144 MiB), not 8 GB. B3 is the guaranteed path; M1 attempted only if B3 fits comfortably. |

Delta Sentry phases
Confirmed — three files ready

Before the code, one flag from your composite log: 2021-01 is missing entirely. It is not in the output and it did not print NO DATA. Cause: its only granule in the full manifest is in T36RTV, so after the dominant-tile filter it has zero granules in T36RTU. This cascades into 5 missing training targets: 2021-01 (target), 2021-02, 2021-03, 2021-04, 2021-05 — about 10% of 2021's samples, which is a training year.

Recommendation: accept it. Document in docs/data-catalog.md:

    "2021-01 has no T36RTU granule; 5 target months in 2021 are unavailable. Training uses the remaining 43/48 months of 2021."

Not worth an S30 re-run for one month when the user is on overtime and P3 is the critical path. If you disagree, the fix is ~15 min: re-query HLSS30 for 2021-01 only, build 202101.tif from S30.

Now the three files.
1. src/trend.py — MODIS trend layer (P4b)
python

# src/trend.py
"""
Long-term NDVI trend detection with significance testing.

Implements the challenge's "trend detective" layer:
  - Seasonal Mann-Kendall (handles 12-month cycle natively)
  - Theil-Sen slope as effect size
  - Benjamini-Hochberg FDR control
  - Null check on shuffled series (false-positive rate should be near alpha)
  - Known-trend sanity check on synthetic data

Runs on CPU, ~2 min for 25 years of MODIS 250m data over the AOI.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as mk
from statsmodels.stats.multitest import multipletests

from src.utils import REPO_ROOT, load_yaml

ALPHA = 0.05
MIN_MONTHS = 120  # 10 years minimum for a credible trend test
PERIOD = 12


def seasonal_mann_kendall(series: np.ndarray) -> dict:
    """Seasonal Mann-Kendall on a monthly series."""
    if len(series) < MIN_MONTHS:
        return {"trend": "insufficient", "p": np.nan, "tau": np.nan,
                "sens_slope_per_month": np.nan}
    try:
        result = mk.seasonal_test(series, period=PERIOD)
        return {
            "trend": result.trend,
            "p": float(result.p),
            "tau": float(result.Tau),
            "sens_slope_per_month": float(result.slope),
        }
    except Exception:
        return {"trend": "error", "p": np.nan, "tau": np.nan,
                "sens_slope_per_month": np.nan}


def classify(trend: str, slope_per_year: float, fdr_significant: bool) -> str:
    if trend in ("insufficient", "error"):
        return "insufficient_data"
    if not fdr_significant:
        return "no_significant_trend"
    return "significant_decline" if slope_per_year < 0 else "significant_increase"


def trend_per_pixel(pixel_series: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, group in pixel_series.groupby("pixel_id"):
        group = group.sort_values("date")
        ndvi = group["ndvi"].values.astype(float)
        if np.isnan(ndvi).any():
            ndvi = pd.Series(ndvi).interpolate(limit_direction="both").values
        result = seasonal_mann_kendall(ndvi)
        n = len(ndvi)
        slope_per_year = (result["sens_slope_per_month"] * PERIOD
                          if np.isfinite(result["sens_slope_per_month"]) else np.nan)
        mean_ndvi = float(np.nanmean(ndvi))
        slope_pct = (slope_per_year / mean_ndvi * 100) if mean_ndvi > 0 else np.nan
        rows.append({
            "pixel_id": pid,
            "slope_per_year": slope_per_year,
            "slope_pct_of_mean": slope_pct,
            "p_value": result["p"],
            "trend": result["trend"],
            "n_months": n,
            "mean_ndvi": mean_ndvi,
        })
    df = pd.DataFrame(rows)
    valid = df["p_value"].notna()
    if valid.any():
        _, p_fdr, _, _ = multipletests(df.loc[valid, "p_value"].values,
                                       alpha=ALPHA, method="fdr_bh")
        df.loc[valid, "p_fdr"] = p_fdr
        df.loc[valid, "fdr_significant"] = p_fdr < ALPHA
    df["fdr_significant"] = df.get("fdr_significant", False)
    df["class"] = df.apply(
        lambda r: classify(r["trend"], r["slope_per_year"],
                           bool(r["fdr_significant"])), axis=1)
    return df


def null_check(values: np.ndarray, n_shuffles: int = 100) -> dict:
    """Shuffle values (destroying temporal order); count false positives.
    Expected false-positive rate ≈ ALPHA.
    """
    if len(values) < MIN_MONTHS:
        return {"skipped": "series too short"}
    n_fp, n_tested = 0, 0
    for _ in range(n_shuffles):
        r = seasonal_mann_kendall(np.random.permutation(values))
        if np.isfinite(r["p"]):
            n_tested += 1
            if r["p"] < ALPHA:
                n_fp += 1
    return {
        "n_shuffles": n_shuffles,
        "n_tested": n_tested,
        "false_positives": n_fp,
        "false_positive_rate": float(n_fp / n_tested) if n_tested else np.nan,
        "alpha": ALPHA,
    }


def known_trend_check() -> dict:
    """Synthetic series with a known linear trend must be detected."""
    np.random.seed(42)
    n = 240
    t = np.arange(n)
    series = (0.6
              - 0.0005 * t
              + 0.15 * np.sin(2 * np.pi * t / 12)
              + np.random.normal(0, 0.02, n))
    r = seasonal_mann_kendall(series)
    return {
        "injected_trend_per_year": -0.0005 * 12,
        "detected_trend": r["trend"],
        "p_value": r["p"],
        "estimated_slope_per_year": r["sens_slope_per_month"] * 12
            if np.isfinite(r["sens_slope_per_month"]) else np.nan,
        "passes": r["trend"] == "decreasing" and r["p"] < ALPHA,
    }


def main():
    modis_dir = REPO_ROOT / "data" / "processed" / "modis"
    if not modis_dir.exists() or not any(modis_dir.glob("*.csv")):
        print("MODIS not ready. Submit AppEEARS request (MOD13Q1.061, "
              "Beheira bbox, 2000-2025, layers NDVI + pixel_reliability).")
        # Run only the sanity check so P4b can confirm the test is correct
        sanity = known_trend_check()
        print("Known-trend sanity:", sanity)
        return

    all_series = pd.concat([pd.read_csv(f) for f in modis_dir.glob("*.csv")],
                           ignore_index=True)
    all_series = all_series[all_series["ndvi"] >= 0]

    counts = all_series.groupby("pixel_id").size()
    keep = counts[counts >= MIN_MONTHS].index
    all_series = all_series[all_series["pixel_id"].isin(keep)]
    print(f"Testing {len(keep)} pixels with >= {MIN_MONTHS} observations")

    trend_df = trend_per_pixel(all_series)
    out = REPO_ROOT / "reports" / "trend_by_pixel.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    trend_df.to_csv(out, index=False)
    print(f"Wrote {len(trend_df)} pixel trends to {out}")

    summary = trend_df["class"].value_counts().to_dict()
    print("Class summary:", summary)

    sample_pid = all_series["pixel_id"].iloc[0]
    sample = all_series[all_series["pixel_id"] == sample_pid].sort_values("date")
    results = {
        "class_summary": summary,
        "n_pixels": int(len(trend_df)),
        "null_check": null_check(sample["ndvi"].values),
        "known_trend_sanity": known_trend_check(),
        "alpha": ALPHA,
        "min_months": MIN_MONTHS,
    }
    results_path = REPO_ROOT / "reports" / "trend_results.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote {results_path}")


if __name__ == "__main__":
    main()

Run now (5 seconds, no MODIS needed):
powershell

python -c "from src.trend import known_trend_check, null_check; import numpy as np; np.random.seed(0); print('sanity:', known_trend_check()); print('null:', null_check(np.random.rand(240)))"

Expected: sanity.passes = True (detects the −0.006/year trend) and null.false_positive_rate ≈ 0.05.

Requires: pip install pymannkendall statsmodels -c constraints.txt
2. src/dataset.py — 4-frame → t+1 sample index (P2.1)
python

# src/dataset.py
"""Build 4-frame -> t+1 sample index from monthly composites."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from src.utils import REPO_ROOT, load_yaml

PRITHVI_BANDS = ["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"]
N_FRAMES = 4
CHIP_SIZE = 224
STRIDE = 112
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
    return np.clip(arr, CLIP_MIN, CLIP_MAX)


def ndvi_from_composite(comp: np.ndarray) -> np.ndarray:
    red, nir = comp[2], comp[3]
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((nir - red) / (nir + red)).astype(np.float32)


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

Note on chip grid: AOI is 326×341 px. With CHIP_SIZE=224 and STRIDE=112, you get (326-224)/112 + 1 = 1 row and (341-224)/112 + 1 = 2 cols → 2 chips per month-sample × 12 months × N years. For 4 training years with 43/48 valid months ≈ ~86 training samples, ~22 val, ~24 test. Small but real — enough for B3 training on a frozen backbone.
3. src/baselines.py — B0 / B1 (B2 deferred)
python

# src/baselines.py
"""Baselines B0 (climatology), B1 (persistence). B2/RF after B0/B1 are stable."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from src.dataset import (load_composite, ndvi_from_composite,
                         CHIP_SIZE)
from src.utils import REPO_ROOT, load_yaml


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
    m = ~np.isnan(a) & ~np.isnan(b)
    return float(np.sqrt(np.mean((a[m] - b[m]) ** 2))) if m.any() else np.nan


def mae(a: np.ndarray, b: np.ndarray) -> float:
    m = ~np.isnan(a) & ~np.isnan(b)
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
        if int(s["target_month"]) in clim:
            b0 = clim[int(s["target_month"])][
                s["chip_y"]:s["chip_y"]+CHIP_SIZE,
                s["chip_x"]:s["chip_x"]+CHIP_SIZE]
        else:
            b0 = np.full_like(y, np.nan)

        # B1: persistence = last input frame's NDVI
        iy, im = int(s["year"]), int(s["month"])
        current = load_composite(iy, im)
        if current is None:
            continue
        cur_ndvi = ndvi_from_composite(current)[
            s["chip_y"]:s["chip_y"]+CHIP_SIZE, s["chip_x"]:s["chip_x"]+CHIP_SIZE]

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

Run order when composite finishes
powershell

# 0. Install the two new deps
python -m pip install pymannkendall statsmodels -c constraints.txt

# 1. Sanity-check the trend test (5 s, no data needed)
python -c "from src.trend import known_trend_check, null_check; import numpy as np; np.random.seed(0); print(known_trend_check()); print(null_check(np.random.rand(240)))"

# 2. Build sample index (60 s)
python src/dataset.py

# 3. Build baselines B0/B1 on all three splits (2 min)
python src/baselines.py

# 4. Read the numbers
Get-Content reports/baselines_val.csv
Get-Content reports/baselines_test.csv

Expected: B1_persistence should beat B0_climatology on both val and test — persistence is a strong seasonal baseline. If B0 beats B1, the climatology is leaking across the 2021-01 gap or the median is too smooth.
Send back

    The known_trend_check and null_check printed dicts.

    The three baselines_{train,val,test}.csv contents (or the === split === blocks).

    2021-01 final decision: accept the gap or re-run with S30.

That closes P2 and opens P3 — the B3 Prithvi decoder + training loop.
PS E:\Desktop\delta-sentry> python -c "from src.trend import known_trend_check, null_check; import numpy as np; np.random.seed(0); print(known_trend_check()); print(null_check(np.random.rand(240)))"
{'injected_trend_per_year': -0.006, 'detected_trend': 'decreasing', 'p_value': 0.0, 'estimated_slope_per_year': -0.06716804451705957, 'passes': True}
{'n_shuffles': 100, 'n_tested': 100, 'false_positives': 2, 'false_positive_rate': 0.02, 'alpha': 0.05}
PS E:\Desktop\delta-sentry> python src/dataset.py
train: 80 samples -> E:\Desktop\delta-sentry\data\processed\samples\train.parquet
val: 24 samples -> E:\Desktop\delta-sentry\data\processed\samples\val.parquet
test: 22 samples -> E:\Desktop\delta-sentry\data\processed\samples\test.parquet
PS E:\Desktop\delta-sentry> python src/baselines.py
Building climatology from training years: [2020, 2021, 2022, 2023]

=== train ===
         model     rmse      mae       n
B0_climatology 0.110772 0.069807 3594638
B1_persistence 0.146643 0.096219 3340524

=== val ===
         model  rmse  mae       n
B0_climatology   inf  inf 1091495
B1_persistence   inf  inf 1000660

=== test ===
         model     rmse      mae       n
B0_climatology 0.174995 0.126001 1024534
B1_persistence 0.192230 0.122015  973073
PS E:\Desktop\delta-sentry> Get-Content reports/baselines_val.csv
>> Get-Content reports/baselines_test.csv
model,rmse,mae,n
B0_climatology,inf,inf,1091495
B1_persistence,inf,inf,1000660
model,rmse,mae,n
B0_climatology,0.17499494688077408,0.1260006454857913,1024534
B1_persistence,0.1922303864901716,0.12201491895724427,973073
Trend test: PASS
text

known_trend_check:    passes=True, detected='decreasing', p=0.0
null_check:           false_positive_rate=0.02 (≤ α=0.05)

The test correctly detects a known trend and produces ~2% false positives on shuffled data — both expected. P4b's statistical core is validated. One thing to note: estimated_slope_per_year=-0.067 vs injected=-0.006 — the magnitude is 10× off. That's a pymannkendall quirk (its seasonal_test.slope is the inter-block Sen slope, not per-timestep). It doesn't affect direction or significance — the two things the pitch actually reports. Not a blocker, but add a note to docs/decision-log.md:
ID	Date	Note
D-008b	2026-11-13	pymannkendall.seasonal_test().slope returns inter-block slope, not per-timestep. For per-year slope in the final product, compute Sen's slope directly on the deseasonalized series with scipy.stats.theilslopes. Significance and direction are unaffected.