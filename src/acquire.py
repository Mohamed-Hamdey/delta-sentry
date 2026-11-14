# src/acquire.py
"""Build the HLS granule manifest with per-band asset URLs for the frozen AOI."""
from pathlib import Path
import earthaccess
import pandas as pd
from utils import load_yaml, REPO_ROOT, GDAL_CONFIG

YEAR_RANGE = range(2020, 2026)
MONTH_RANGE = range(1, 13)


def month_window(year: int, month: int):
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-28" if month == 2 else f"{year}-{month:02d}-30"
    return start, end


def find_asset(links: dict, suffix: str) -> str:
    """Return the URL whose filename ends with `suffix`, else ''."""
    for name, url in links.items():
        if name.endswith(suffix):
            return url
    return ""


def main():
    aoi = load_yaml("config/aoi.yaml")
    bands_cfg = load_yaml("config/bands.yaml")["products"]["HLSL30"]
    bbox = tuple(aoi["bbox_wgs84"])
    earthaccess.login(strategy="interactive", persist=True)

    rows = []
    for year in YEAR_RANGE:
        for month in MONTH_RANGE:
            start, end = month_window(year, month)
            granules = earthaccess.search_data(
                short_name="HLSL30", bounding_box=bbox,
                temporal=(start, end), cloud_cover=(0, 80),
            )
            for g in granules:
                umm = g["umm"]
                links = {Path(u["URL"]).name: u["URL"] for u in umm["RelatedUrls"]}
                row = {
                    "granule_id": umm["GranuleUR"],
                    "year": year, "month": month,
                    "temporal_start": umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
                    "n_assets": len(links),
                }
                for pband, fname in bands_cfg.items():
                    row[f"{pband}_url"] = find_asset(links, fname)
                rows.append(row)
            print(f"{year}-{month:02d}: {len(granules)} granules")

    df = pd.DataFrame(rows).sort_values(["year", "month", "temporal_start"])
    out = REPO_ROOT / "data" / "interim" / "granule_manifest.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    # Sanity: fail loudly if URL columns are empty
    for col in [c for c in df.columns if c.endswith("_url")]:
        non_empty = (df[col].fillna("").astype(str).str.len() > 0).sum()
        print(f"{col}: {non_empty}/{len(df)} populated")
        if non_empty == 0:
            raise RuntimeError(f"Column {col} is empty — check bands.yaml suffix names")

    print(f"\nwrote {len(df)} granules to {out}")


if __name__ == "__main__":
    main()