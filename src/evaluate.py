# src/evaluate.py
import torch
import numpy as np
import pandas as pd
from torch.utils.data import DataLoader  # <-- Fixed this line

# Added 'src.' to the local imports so Python finds them
from model import DeltaSentryModel
from train import NDVIDataset
from utils import REPO_ROOT

def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Evaluating on {device}...")
    
    test_ds = NDVIDataset(REPO_ROOT / "data" / "processed" / "samples" / "test.parquet")
    test_loader = DataLoader(test_ds, batch_size=2, shuffle=False)
    
    model = DeltaSentryModel().to(device)
    weights_path = REPO_ROOT / "models" / "b3_best.pt"
    if not weights_path.exists():
        print("No model weights found! Run train.py first.")
        return
        
    model.load_state_dict(torch.load(weights_path, map_location=device))
    model.eval()
    
    total_sq_err = 0.0
    total_abs_err = 0.0
    total_pixels = 0
    
    with torch.no_grad():
        for x, t_coords, l_coords, y in test_loader:
            x, t_coords, l_coords, y = x.to(device), t_coords.to(device), l_coords.to(device), y.to(device)
            pred = model(x, t_coords, l_coords)
            
            mask = ~torch.isnan(y)
            if mask.sum() == 0: continue
            
            total_sq_err += ((pred[mask] - y[mask]) ** 2).sum().item()
            total_abs_err += (pred[mask] - y[mask]).abs().sum().item()
            total_pixels += mask.sum().item()
            
    rmse = np.sqrt(total_sq_err / total_pixels)
    mae = total_abs_err / total_pixels
    
    print("\n=== Prithvi B3 Test Results ===")
    print(f"RMSE: {rmse:.4f}")
    print(f"MAE:  {mae:.4f}")
    print("===============================")
    
    # Save to CSV for the presentation
    results = pd.DataFrame([{"model": "Prithvi_B3_frozen", "rmse": rmse, "mae": mae, "n": total_pixels}])
    out_path = REPO_ROOT / "reports" / "baselines_test_prithvi.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_path, index=False)

if __name__ == "__main__":
    main()