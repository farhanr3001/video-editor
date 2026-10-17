# Copyright (c) 2021 Xintao Wang. BSD-3-Clause; see licenses/AI-Enhance-BSD-3-Clause.txt.
# Standalone adaptation of Real-ESRGAN's SRVGGNetCompact; no BasicSR dependency.
from torch import nn
from torch.nn import functional as F


class SRVGGNetCompact(nn.Module):
    def __init__(self):
        super().__init__()
        layers=[nn.Conv2d(3,64,3,1,1),nn.PReLU(64)]
        for _ in range(32):layers.extend((nn.Conv2d(64,64,3,1,1),nn.PReLU(64)))
        layers.append(nn.Conv2d(64,48,3,1,1))
        self.body=nn.ModuleList(layers);self.upsampler=nn.PixelShuffle(4)

    def forward(self,image):
        value=image
        for layer in self.body:
            # DirectML's PReLU broadcast creates an unsupported tensor rank.
            # Equivalent per-channel arithmetic keeps inference on the device.
            if value.device.type == 'privateuseone' and isinstance(layer,nn.PReLU):
                value=value.clamp_min(0)+value.clamp_max(0)*layer.weight.view(1,-1,1,1)
            else:value=layer(value)
        return self.upsampler(value)+F.interpolate(image,scale_factor=4,mode='nearest')
