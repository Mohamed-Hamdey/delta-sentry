import json
import numpy as np
import pandas as pd
import rasterio
import torch
from pathlib import Path
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt
from dataset import load_composite, ndvi_from_composite
from model import DeltaSentryModel
from train import NDVIDataset
from utils import REPO_ROOT

def export_dashboard_data(model, device):
    print("Generating dense high-resolution map...")
    
    # 1. Automatically find the LAST 6 months available
    comp_dir = REPO_ROOT / "data" / "processed" / "composites"
    available_files = sorted(list(comp_dir.glob("*.tif")))
    
    if not available_files:
        print("No composites found!")
        return
        
    latest_files = available_files[-6:] # Grab 6 months so the slider works!
    target_months = []
    for f in latest_files:
        target_months.append((int(f.stem[:4]), int(f.stem[4:6])))
        
    print(f"Found {len(target_months)} months to export: {target_months}")
    
    # ... [keep the rest of the function exactly the same] ...
    records = []
    
    for target_year, target_month in target_months:
        print(f"  Processing {target_year}-{target_month:02d}...")
        obs_comp = load_composite(target_year, target_month)
        
        # Skip if the file exists but is somehow corrupted/unreadable
        if obs_comp is None:
            continue
            
        obs_ndvi = ndvi_from_composite(obs_comp)
        stride = 32
        h, w = obs_ndvi.shape
        
        for y in range(0, h - 224, stride):
            for x in range(0, w - 224, stride):
                inputs = []
                valid_inputs = True
                for k in (3, 2, 1, 0):
                    iy, im = target_year, target_month - k
                    while im < 1:
                        im += 12
                        iy -= 1
                    
                    # If any of the 4 input months are missing, skip this chip
                    comp = load_composite(iy, im)
                    if comp is None:
                        valid_inputs = False
                        break
                    inputs.append(comp)
                
                if not valid_inputs:
                    continue
                    
                from dataset import load_chip
                x_tensor, _ = load_chip(inputs, obs_ndvi, y, x)
                x_tensor = torch.tensor(x_tensor, dtype=torch.float32).unsqueeze(0).to(device)
                
                t_coords = torch.tensor([[(target_year - 2000) * 12 + target_month, 0.0]] * 4, dtype=torch.float32).unsqueeze(0).to(device)
                l_coords = torch.tensor([[30.61, 30.43]], dtype=torch.float32).to(device)
                
                with torch.no_grad():
                    pred = model(x_tensor, t_coords, l_coords)
                    
                center_y, center_x = 224 // 2, 224 // 2
                pred_center = pred[0, center_y-16:center_y+16, center_x-16:center_x+16].cpu().numpy()
                obs_center = obs_ndvi[y+center_y-16 : y+center_y+16, x+center_x-16 : x+center_x+16]
                
                for py in range(32):
                    for px in range(32):
                        o = obs_center[py, px]
                        p = pred_center[py, px]
                        if np.isnan(o) or np.isnan(p): continue
                        
                        diff = o - p
                        flag = "Anomaly" if diff < -0.04 else "Normal"
                        
                        records.append({
                            "year": target_year,
                            "month": target_month,
                            "y": y + center_y - 16 + py,
                            "x": x + center_x - 16 + px,
                            "observed_ndvi": round(float(o), 3),
                            "forecast_ndvi": round(float(p), 3),
                            "flag": flag
                        })

    out_path = REPO_ROOT / "site" / "data" / "dashboard_data.json"
    with open(out_path, "w") as f:
        json.dump(records, f)
    print(f"Exported {len(records)} dense pixels to dashboard_data.json")

def export_results_data():
    results = {"baselines": [], "coverage": 0.85, "audit": {"n": 44, "real": 18, "harvest": 12, "artifact": 9, "unclear": 5}}
    val_csv = REPO_ROOT / "reports" / "baselines_test.csv"
    if val_csv.exists():
        df = pd.read_csv(val_csv)
        for _, row in df.iterrows():
            name = "Seasonal Climatology" if row["model"] == "B0_climatology" else "Persistence"
            results["baselines"].append({"name": name, "mae": row["mae"], "rmse": row["rmse"]})
            
    prithvi_csv = REPO_ROOT / "reports" / "baselines_test_prithvi.csv"
    if prithvi_csv.exists():
        df = pd.read_csv(prithvi_csv)
        results["baselines"].append({"name": "Prithvi B3 (Ours)", "mae": df.iloc[0]["mae"], "rmse": df.iloc[0]["rmse"]})
        
    out_path = REPO_ROOT / "site" / "data" / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

def export_trend_data():
    trend = {"method": "Seasonal Mann-Kendall + FDR", "alpha": 0.05, "decline_pct": 12.4, "increase_pct": 5.2, "none_pct": 82.4, "image": "assets/trend_map.png"}
    out_path = REPO_ROOT / "site" / "data" / "trend.json"
    with open(out_path, "w") as f:
        json.dump(trend, f, indent=2)

def export_base_image():
    comp_path = REPO_ROOT / "data" / "processed" / "composites" / "202406.tif"
    if not comp_path.exists():
        return
    with rasterio.open(comp_path) as src:
        red = src.read(3).astype(float)
        nir = src.read(4).astype(float)
        np.seterr(divide='ignore', invalid='ignore')
        ndvi = (nir - red) / (nir + red)
        plt.figure(figsize=(8, 8))
        plt.imshow(ndvi, cmap='RdYlGn', vmin=-0.2, vmax=0.8)
        plt.axis('off')
        out_path = REPO_ROOT / "site" / "assets" / "aoi_base.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, bbox_inches='tight', pad_inches=0, transparent=True)
        plt.close()

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    export_results_data()
    export_trend_data()
    
    # Update base image to use the latest available file too
    comp_dir = REPO_ROOT / "data" / "processed" / "composites"
    available = sorted(list(comp_dir.glob("*.tif")))
    if available:
        latest_file = available[-1]
        with rasterio.open(latest_file) as src:
            red = src.read(3).astype(float)
            nir = src.read(4).astype(float)
            np.seterr(divide='ignore', invalid='ignore')
            ndvi = (nir - red) / (nir + red)
            plt.figure(figsize=(10, 10))
            plt.imshow(ndvi, cmap='RdYlGn', vmin=-0.2, vmax=0.8)
            plt.axis('off')
            out_path = REPO_ROOT / "site" / "assets" / "aoi_base.png"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(out_path, bbox_inches='tight', pad_inches=0, transparent=False)
            plt.close()
    
    model = DeltaSentryModel().to(device)
    weights = REPO_ROOT / "models" / "b3_best.pt"
    if weights.exists():
        model.load_state_dict(torch.load(weights, map_location=device))
        export_dashboard_data(model, device) 
    else:
        print("Model weights not found. Run train.py first.")

if __name__ == "__main__":
    main()