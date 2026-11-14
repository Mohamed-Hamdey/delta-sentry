# smoke_test_prithvi.py — run once, then keep as a regression check
import torch
from terratorch import BACKBONE_REGISTRY

device = "cuda"
dtype = torch.float16

# Build the Prithvi-EO-2.0 backbone model
model = BACKBONE_REGISTRY.build(
    "terratorch_prithvi_eo_v2_300_tl",
    pretrained=True,
    num_frames=4,
    bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"],
).to(device).eval()

# batch 1, 6 bands, 4 frames, 224x224
x = torch.randn(1, 6, 4, 224, 224, device=device, dtype=dtype)

# FIX: Provide 2 features per time step: [Year/Index, Julian Day]
# Shape becomes (Batch=1, Frames=4, Features=2) -> Dimension 2 has size 2
temporal_coords = torch.tensor([
    [[0.0, 15.0],   # Frame 0: index 0, day 15
     [0.0, 45.0],   # Frame 1: index 0, day 45
     [0.0, 75.0],   # Frame 2: index 0, day 75
     [0.0, 105.0]]  # Frame 3: index 0, day 105
], device=device, dtype=torch.float32) 

location_coords = torch.tensor([[30.61, 30.43]], device=device, dtype=torch.float32)

# Run forward pass with modern autocast
with torch.no_grad(), torch.amp.autocast('cuda', dtype=dtype):
    out = model(x, temporal_coords=temporal_coords, location_coords=location_coords)

torch.cuda.synchronize()
peak_mib = torch.cuda.max_memory_allocated() / 1024**2
print("output shape:", out.shape if hasattr(out, "shape") else type(out))
print(f"peak VRAM: {peak_mib:.0f} MiB")