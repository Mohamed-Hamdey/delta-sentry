# src/train.py
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import os
from pathlib import Path
from model import DeltaSentryModel
from dataset import load_chip, load_composite, ndvi_from_composite, CHIP_SIZE
from utils import REPO_ROOT

class NDVIDataset(Dataset):
    def __init__(self, parquet_path):
        self.samples = pd.read_parquet(parquet_path)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples.iloc[idx]
        year, month = int(s["year"]), int(s["month"])
        ty, tm = int(s["target_year"]), int(s["target_month"])
        
        inputs = []
        for k in (3, 2, 1, 0):
            iy, im = year, month - k
            while im < 1:
                im += 12
                iy -= 1
            inputs.append(load_composite(iy, im))
            
        target_comp = load_composite(ty, tm)
        target_ndvi = ndvi_from_composite(target_comp)
        
        x, y = load_chip(inputs, target_ndvi, int(s["chip_y"]), int(s["chip_x"]))
        
        x = torch.tensor(x, dtype=torch.float32)
        y = torch.tensor(y, dtype=torch.float32)
        
        t_val = float((ty - 2000) * 12 + tm)
        temporal_coords = torch.tensor([[t_val, 0.0]] * 4, dtype=torch.float32)
        location_coords = torch.tensor([30.61, 30.43], dtype=torch.float32)
        
        return x, temporal_coords, location_coords, y

def evaluate(model, dataloader, device):
    model.eval()
    total_sq_err = 0.0
    total_pixels = 0
    
    with torch.no_grad():
        for x, t_coords, l_coords, y in dataloader:
            x, t_coords, l_coords, y = x.to(device), t_coords.to(device), l_coords.to(device), y.to(device)
            pred = model(x, t_coords, l_coords)
            
            mask = ~torch.isnan(y)
            if mask.sum() == 0: continue
            
            # Calculate squared error for RMSE
            sq_err = (pred[mask] - y[mask]) ** 2
            total_sq_err += sq_err.sum().item()
            total_pixels += mask.sum().item()
            
    rmse = np.sqrt(total_sq_err / total_pixels) if total_pixels > 0 else float('nan')
    model.train()
    return rmse

def train():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    train_ds = NDVIDataset(REPO_ROOT / "data" / "processed" / "samples" / "train.parquet")
    val_ds = NDVIDataset(REPO_ROOT / "data" / "processed" / "samples" / "val.parquet")
    
    train_loader = DataLoader(train_ds, batch_size=2, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=2, shuffle=False)
    
    model = DeltaSentryModel().to(device)
    optimizer = torch.optim.AdamW(model.decoder.parameters(), lr=1e-4)
    criterion = nn.MSELoss()
    
    best_val_rmse = float("inf")
    epochs = 15  # Increase this when you have the full dataset
    
    os.makedirs(REPO_ROOT / "models", exist_ok=True)
    
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0
        
        for batch_idx, (x, t_coords, l_coords, y) in enumerate(train_loader):
            x, t_coords, l_coords, y = x.to(device), t_coords.to(device), l_coords.to(device), y.to(device)
            
            optimizer.zero_grad()
            with torch.amp.autocast('cuda', enabled=(device=="cuda")):
                pred = model(x, t_coords, l_coords)
                mask = ~torch.isnan(y)
                if mask.sum() == 0: continue
                loss = criterion(pred[mask], y[mask])
                
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.decoder.parameters(), max_norm=1.0)
            optimizer.step()
            epoch_loss += loss.item()
            
        # Validation step
        val_rmse = evaluate(model, val_loader, device)
        print(f"Epoch {epoch:02d} | Train Loss: {epoch_loss/len(train_loader):.4f} | Val RMSE: {val_rmse:.4f}")
        
        # Save best model
        if val_rmse < best_val_rmse:
            best_val_rmse = val_rmse
            torch.save(model.state_dict(), REPO_ROOT / "models" / "b3_best.pt")
            print(f"  --> Saved new best model (Val RMSE: {val_rmse:.4f})")

if __name__ == "__main__":
    train()