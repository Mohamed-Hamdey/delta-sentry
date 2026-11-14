# Environment

Recorded at P0.1. Update after installing the env.

## Hardware
- GPU: NVIDIA GeForce RTX 3060 Laptop GPU — **6144 MiB (6 GB)**
- Driver: 581.83
- RAM: 16 GB
- CPU: 11th Gen Intel Core i7-11800H @ 2.30 GHz

## Software
- Python: 3.12.7
- CUDA / nvcc: PyTorch runtime CUDA 12.1 (NVIDIA RTX 3060, Driver 581.83)
- PyTorch wheel:  2.5.1+cu121
- TerraTorch version: 1.2.14 
- earthaccess: 0.19.0 
- rasterio / rioxarray / xarray / geopandas: 1.5.2 / 0.24.0 / 2026.9.0 / 1.2.0
- Locked env hash (`pip freeze` sha256):  92ff78b288e14c54cad0952c81d20a56c97e8f9e444d22c5b27194e5eee6f66f

## Constraints
- 6 GB VRAM: B3 (frozen backbone + decoder) is the guaranteed path.
  M1 (partial unfreezing) only with mixed precision, gradient checkpointing, batch 1.
- Full fine-tuning of the 300M model is out of scope on this GPU.
- Python 3.12: verify TerraTorch + PyTorch support before P3. If incompatible,
  create a 3.11 venv and log it as a decision (D-004b).

## Prithvi smoke test (P0.5) — PASS
- Checkpoint: terratorch_prithvi_eo_v2_300_tl, pretrained=True
- TerraTorch: 1.1.1 (all v2 backbones registered, incl. eo_v2_300_tl)
- PyTorch: 2.6.0+cu124, CUDA available = True (RTX 3060 Laptop, 6144 MiB)
- Pinned stack: numpy 1.26.4, pyarrow 20.0.0, numexpr 2.10.2
- Input: (1, 6, 4, 224, 224) float16, batch 1
- Band order loaded: BLUE, GREEN, RED, NIR_NARROW, SWIR_1, SWIR_2 (matches HLS plan)
- Forward output: list of intermediate feature maps (backbone — decoder required)
- Peak VRAM (forward only): 1862 MiB / 6144 MiB
- Headroom for B3 training: ~4.3 GB
- Result: PASS