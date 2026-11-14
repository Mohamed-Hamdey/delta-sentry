import os
import time
import json
import hashlib
import numpy as np
import torch
from huggingface_hub import hf_hub_download

INFERENCE_DEVICE = os.getenv("INFERENCE_DEVICE", "cpu")
MODEL_VERSION = "prithvi-2.0-300m-tl_unet-b3"

# Model repo — set via Space env vars, or falls back to your hardcoded ID
MODEL_REPO_ID = os.getenv("MODEL_REPO_ID", "mohamedhamdey/delta-sentry-b3-weights")
MODEL_FILENAME = os.getenv("MODEL_FILENAME", "b3_best.pt")

CACHE_DIR = "/tmp/infer_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Lazy-load the model on first inference
_MODEL = None

def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    print(f"[inference] Downloading {MODEL_REPO_ID}/{MODEL_FILENAME}...")
    try:
        model_path = hf_hub_download(
            repo_id=MODEL_REPO_ID,
            filename=MODEL_FILENAME,
            repo_type="model",
        )
        print(f"[inference] Model cached at: {model_path}")
    except Exception as e:
        raise RuntimeError(
            f"Could not download model from {MODEL_REPO_ID}. "
            f"Check that the model repo is public and MODEL_REPO_ID is correct. Error: {e}"
        )

    # --- YOUR MODEL LOADING LOGIC ---
    # If your training script saved state_dict of a decoder:
    #   from your_model_module import YourModelClass
    #   m = YourModelClass()
    #   m.load_state_dict(torch.load(model_path, map_location="cpu"))
    # If it saved the full model via torch.save(model, ...):
    #   m = torch.load(model_path, map_location="cpu")
    #
    # Placeholder — REPLACE with your actual loader:
    _MODEL = torch.load(model_path, map_location=torch.device("cpu"), weights_only=False)
    if hasattr(_MODEL, "eval"):
        _MODEL.eval()
    print("[inference] Model loaded.")
    return _MODEL


def get_cache_key(tile_id, month, bbox):
    data = f"{tile_id}|{month}|{MODEL_VERSION}|{INFERENCE_DEVICE}|{bbox}"
    return hashlib.sha256(data.encode()).hexdigest()


def run_inference(tile_id, target_month, bbox, progress_callback):
    start_time = time.time()
    cache_key = get_cache_key(tile_id, target_month, bbox)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")

    # Cache hit
    if os.path.exists(cache_file):
        progress_callback(100, "done")
        with open(cache_file, "r") as f:
            res = json.load(f)
            res["cached"] = True
            return res

    progress_callback(10, "loading_composite")
    time.sleep(1)

    progress_callback(30, "loading_model")
    model = _load_model()

    progress_callback(50, "running_inference")

    # --- REPLACE THIS BLOCK WITH YOUR ACTUAL INFERENCE ---
    # x_min, y_min, x_max, y_max = bbox["x_min"], bbox["y_min"], bbox["x_max"], bbox["y_max"]
    # tensor = load_geotiffs(target_month, bbox)   # your data loader
    # with torch.no_grad():
    #     out = model(tensor)
    # pixels = format_output(out, bbox)
    #
    # For now, simulated output so you can test the pipeline end-to-end:
    # ----------------------------------------------------
    pixels = []
    for y in range(bbox["y_min"], bbox["y_max"]):
        for x in range(bbox["x_min"], bbox["x_max"]):
            obs = float(np.random.uniform(0.3, 0.7))
            fcst = float(obs + np.random.uniform(-0.15, 0.05))
            gap = obs - fcst
            pixels.append({
                "x": x, "y": y,
                "observed_ndvi": round(obs, 3),
                "forecast_ndvi": round(fcst, 3),
                "flag": "Anomaly" if gap < -0.10 else "Normal"
            })
    # ----------------------------------------------------

    progress_callback(90, "postprocessing")
    time.sleep(0.5)

    elapsed = round(time.time() - start_time, 1)
    result = {
        "job_id": "live",
        "target_month": target_month,
        "device": INFERENCE_DEVICE,
        "inference_time_seconds": elapsed,
        "cached": False,
        "model_version": MODEL_VERSION,
        "pixels": pixels,
        "summary": {
            "total_pixels": len(pixels),
            "anomalies": sum(1 for p in pixels if p["flag"] == "Anomaly")
        }
    }

    with open(cache_file, "w") as f:
        json.dump(result, f)

    return result