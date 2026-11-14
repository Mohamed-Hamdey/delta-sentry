# src/aoi_coverage.py
import earthaccess
from datetime import date

CANDIDATES = {
    "Beheira": (30.378, 30.565, 30.482, 30.655),
    "Dakahlia": (31.248, 30.955, 31.352, 31.045),
}

earthaccess.login(strategy="interactive", persist=True)

for name, bbox in CANDIDATES.items():
    print(f"\n=== {name} ===")
    months_with_data = 0
    for month in range(1, 13):
        start = date(2024, month, 1)
        end = date(2024, month, 28) if month == 2 else date(2024, month, 30)
        granules = earthaccess.search_data(
            short_name="HLSL30",
            bounding_box=bbox,
            temporal=(start.isoformat(), end.isoformat()),
            cloud_cover=(0, 40),   # tolerate up to 40% cloud
        )
        if len(granules) > 0:
            months_with_data += 1
            print(f"  2024-{month:02d}: {len(granules)} granules")
        else:
            print(f"  2024-{month:02d}: 0")
    print(f"  months with >=1 granule: {months_with_data}/12")