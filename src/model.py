import torch
import torch.nn as nn
from terratorch import BACKBONE_REGISTRY


class PrithviNDVIDecoder(nn.Module):
    def __init__(self, embed_dim=1024):
        super().__init__()
        self.conv1 = nn.Conv2d(embed_dim, 256, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(256, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 64, kernel_size=3, padding=1)
        self.final = nn.Conv2d(64, 1, kernel_size=1)
        self.relu = nn.ReLU(inplace=True)
        self.upsample = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)

    def forward(self, x):
        # x shape: (B, 1024, 14, 14)
        x = self.relu(self.conv1(x))
        x = self.upsample(x)   # 28x28
        x = self.relu(self.conv2(x))
        x = self.upsample(x)   # 56x56
        x = self.relu(self.conv3(x))
        x = self.upsample(x)   # 112x112
        x = self.upsample(x)   # 224x224
        x = self.final(x)
        return x.squeeze(1)    # (B, 224, 224)


class DeltaSentryModel(nn.Module):
    def __init__(self, num_frames=4):
        super().__init__()
        self.num_frames = num_frames
        self.backbone = BACKBONE_REGISTRY.build(
            "terratorch_prithvi_eo_v2_300_tl",
            pretrained=True,
            num_frames=num_frames,
            bands=["BLUE", "GREEN", "RED", "NIR_NARROW", "SWIR_1", "SWIR_2"],
        )
        for param in self.backbone.parameters():
            param.requires_grad = False

        # Prithvi-EO-V2-300M uses embed_dim=1024
        embed_dim = getattr(self.backbone, "embed_dim", 1024)
        self.decoder = PrithviNDVIDecoder(embed_dim=embed_dim)

    def forward(self, x, temporal_coords, location_coords):
        # x: (B, 6, 4, 224, 224)
        features = self.backbone(x, temporal_coords=temporal_coords, location_coords=location_coords)
        out = features[-1] if isinstance(features, (list, tuple)) else features

        if out.ndim == 3:
            # out shape: (B, 1 + T*H*W, C) -> e.g., (B, 785, 1024)
            B, N, C = out.shape
            if (N - 1) % self.num_frames == 0:
                out = out[:, 1:, :]  # Strip the CLS token -> (B, 784, 1024)
                N -= 1
            tokens_per_frame = N // self.num_frames  # 196
            H = W = int(tokens_per_frame ** 0.5)     # 14
            # Reshape to (B, T, H, W, C) -> (B, T, C, H, W) -> average over T
            out = out.reshape(B, self.num_frames, H, W, C).permute(0, 1, 4, 2, 3).mean(dim=1)
        elif out.ndim == 5:
            out = out.mean(dim=1)

        return self.decoder(out)