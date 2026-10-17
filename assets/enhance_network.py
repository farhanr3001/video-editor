# Copyright (c) OpenMMLab. All rights reserved. Apache-2.0.
# Modified for Kinetic Cut: standalone inference; no MMCV/MMEngine, no downloads.
# Original: https://github.com/open-mmlab/mmagic
import torch
from torch import nn
from torch.nn import functional as F
BaseModule=nn.Module
WARNING=30
def print_log(*args,**kwargs):pass
def make_layer(block,count,**kwargs):return nn.Sequential(*(block(**kwargs) for _ in range(count)))
class ConvModule(nn.Module):
 def __init__(self,in_channels,out_channels,kernel_size,stride,padding,norm_cfg=None,act_cfg=None):
  super().__init__();self.conv=nn.Conv2d(in_channels,out_channels,kernel_size,stride,padding);self.activate=nn.ReLU(inplace=True) if act_cfg else nn.Identity()
 def forward(self,x):return self.activate(self.conv(x))
class ResidualBlockNoBN(nn.Module):
 def __init__(self,mid_channels):
  super().__init__();self.conv1=nn.Conv2d(mid_channels,mid_channels,3,1,1);self.conv2=nn.Conv2d(mid_channels,mid_channels,3,1,1)
 def forward(self,x):return x+self.conv2(F.relu(self.conv1(x),inplace=True))
class PixelShufflePack(nn.Module):
 def __init__(self,in_channels,out_channels,scale_factor,upsample_kernel):
  super().__init__();self.upsample_conv=nn.Conv2d(in_channels,out_channels*scale_factor**2,upsample_kernel,1,upsample_kernel//2);self.scale_factor=scale_factor
 def forward(self,x):return F.pixel_shuffle(self.upsample_conv(x),self.scale_factor)
def flow_warp(x,flow,padding_mode='zeros'):
 n,c,h,w=x.shape
 yy,xx=torch.meshgrid(torch.arange(h,device=x.device,dtype=x.dtype),torch.arange(w,device=x.device,dtype=x.dtype),indexing='ij')
 grid=torch.stack((xx,yy),-1)[None]+flow
 grid=torch.stack((2*grid[...,0]/max(w-1,1)-1,2*grid[...,1]/max(h-1,1)-1),-1)
 if x.device.type=='privateuseone':
  # DirectML does not implement grid_sample. Equivalent bilinear gathers keep
  # temporal alignment on the GPU instead of copying feature maps to the CPU.
  px=xx[None]+flow[...,0];py=yy[None]+flow[...,1]
  if padding_mode=='border':px=px.clamp(0,w-1);py=py.clamp(0,h-1)
  x0=px.floor();y0=py.floor();dx=px-x0;dy=py-y0
  def at(ix,iy):
   valid=((ix>=0)&(ix<w)&(iy>=0)&(iy<h)).to(x.dtype)
   index=(iy.clamp(0,h-1).long()*w+ix.clamp(0,w-1).long()).reshape(n,1,h*w).expand(n,c,h*w)
   return torch.gather(x.reshape(n,c,h*w),2,index).reshape(n,c,h,w)*valid[:,None]
  return at(x0,y0)*((1-dx)*(1-dy))[:,None]+at(x0+1,y0)*(dx*(1-dy))[:,None]+at(x0,y0+1)*((1-dx)*dy)[:,None]+at(x0+1,y0+1)*(dx*dy)[:,None]
 return F.grid_sample(x,grid,mode='bilinear',padding_mode=padding_mode,align_corners=True)
class BasicVSRNet(BaseModule):
    """BasicVSR network structure for video super-resolution.

    Support only x4 upsampling.

    Paper:
        BasicVSR: The Search for Essential Components in Video Super-Resolution
        and Beyond, CVPR, 2021

    Args:
        mid_channels (int): Channel number of the intermediate features.
            Default: 64.
        num_blocks (int): Number of residual blocks in each propagation branch.
            Default: 30.
        spynet_pretrained (str): Pre-trained model path of SPyNet.
            Default: None.
    """

    def __init__(self, mid_channels=64, num_blocks=30, spynet_pretrained=None):

        super().__init__()

        self.mid_channels = mid_channels

        # optical flow network for feature alignment
        self.spynet = SPyNet(pretrained=spynet_pretrained)

        # propagation branches
        self.backward_resblocks = ResidualBlocksWithInputConv(
            mid_channels + 3, mid_channels, num_blocks)
        self.forward_resblocks = ResidualBlocksWithInputConv(
            mid_channels + 3, mid_channels, num_blocks)

        # upsample
        self.fusion = nn.Conv2d(
            mid_channels * 2, mid_channels, 1, 1, 0, bias=True)
        self.upsample1 = PixelShufflePack(
            mid_channels, mid_channels, 2, upsample_kernel=3)
        self.upsample2 = PixelShufflePack(
            mid_channels, 64, 2, upsample_kernel=3)
        self.conv_hr = nn.Conv2d(64, 64, 3, 1, 1)
        self.conv_last = nn.Conv2d(64, 3, 3, 1, 1)
        self.img_upsample = nn.Upsample(
            scale_factor=4, mode='bilinear', align_corners=False)

        # activation function
        self.lrelu = nn.LeakyReLU(negative_slope=0.1, inplace=True)

        self._raised_warning = False

    def check_if_mirror_extended(self, lrs):
        """Check whether the input is a mirror-extended sequence.

        If mirror-extended, the i-th (i=0, ..., t-1) frame is equal to the
        (t-1-i)-th frame.

        Args:
            lrs (tensor): Input LR images with shape (n, t, c, h, w)
        """

        self.is_mirror_extended = False
        if lrs.size(1) % 2 == 0:
            lrs_1, lrs_2 = torch.chunk(lrs, 2, dim=1)
            if torch.norm(lrs_1 - lrs_2.flip(1)) == 0:
                self.is_mirror_extended = True

    def compute_flow(self, lrs):
        """Compute optical flow using SPyNet for feature warping.

        Note that if the input is an mirror-extended sequence, 'flows_forward'
        is not needed, since it is equal to 'flows_backward.flip(1)'.

        Args:
            lrs (tensor): Input LR images with shape (n, t, c, h, w)

        Return:
            tuple(Tensor): Optical flow. 'flows_forward' corresponds to the
                flows used for forward-time propagation (current to previous).
                'flows_backward' corresponds to the flows used for
                backward-time propagation (current to next).
        """

        n, t, c, h, w = lrs.size()
        lrs_1 = lrs[:, :-1, :, :, :].reshape(-1, c, h, w)
        lrs_2 = lrs[:, 1:, :, :, :].reshape(-1, c, h, w)

        flows_backward = self.spynet(lrs_1, lrs_2).view(n, t - 1, 2, h, w)

        if self.is_mirror_extended:  # flows_forward = flows_backward.flip(1)
            flows_forward = None
        else:
            flows_forward = self.spynet(lrs_2, lrs_1).view(n, t - 1, 2, h, w)

        return flows_forward, flows_backward

    def forward(self, lrs):
        """Forward function for BasicVSR.

        Args:
            lrs (Tensor): Input LR sequence with shape (n, t, c, h, w).

        Returns:
            Tensor: Output HR sequence with shape (n, t, c, 4h, 4w).
        """
        n, t, c, h, w = lrs.size()
        if (h < 64 or w < 64) and not self._raised_warning:
            print_log(
                f'{self.__class__.__name__} is designed for input '
                'larger than 64x64, but the resolution of current image '
                f'is {h}x{w}. We recommend you to check your input.',
                'current', WARNING)
            self._raised_warning = True

        # check whether the input is an extended sequence
        self.check_if_mirror_extended(lrs)

        # compute optical flow
        flows_forward, flows_backward = self.compute_flow(lrs)

        # backward-time propagation
        outputs = []
        feat_prop = lrs.new_zeros(n, self.mid_channels, h, w)
        for i in range(t - 1, -1, -1):
            if i < t - 1:  # no warping required for the last timestep
                flow = flows_backward[:, i, :, :, :]
                feat_prop = flow_warp(feat_prop, flow.permute(0, 2, 3, 1))

            feat_prop = torch.cat([lrs[:, i, :, :, :], feat_prop], dim=1)
            feat_prop = self.backward_resblocks(feat_prop)

            outputs.append(feat_prop)
        outputs = outputs[::-1]

        # forward-time propagation and upsampling
        feat_prop = torch.zeros_like(feat_prop)
        for i in range(0, t):
            lr_curr = lrs[:, i, :, :, :]
            if i > 0:  # no warping required for the first timestep
                if flows_forward is not None:
                    flow = flows_forward[:, i - 1, :, :, :]
                else:
                    flow = flows_backward[:, -i, :, :, :]
                feat_prop = flow_warp(feat_prop, flow.permute(0, 2, 3, 1))

            feat_prop = torch.cat([lr_curr, feat_prop], dim=1)
            feat_prop = self.forward_resblocks(feat_prop)

            # upsampling given the backward and forward features
            out = torch.cat([outputs[i], feat_prop], dim=1)
            out = self.lrelu(self.fusion(out))
            out = self.lrelu(self.upsample1(out))
            out = self.lrelu(self.upsample2(out))
            out = self.lrelu(self.conv_hr(out))
            out = self.conv_last(out)
            base = self.img_upsample(lr_curr)
            out += base
            outputs[i] = out

        return torch.stack(outputs, dim=1)


class ResidualBlocksWithInputConv(BaseModule):
    """Residual blocks with a convolution in front.

    Args:
        in_channels (int): Number of input channels of the first conv.
        out_channels (int): Number of channels of the residual blocks.
            Default: 64.
        num_blocks (int): Number of residual blocks. Default: 30.
    """

    def __init__(self, in_channels, out_channels=64, num_blocks=30):
        super().__init__()

        main = []

        # a convolution used to match the channels of the residual blocks
        main.append(nn.Conv2d(in_channels, out_channels, 3, 1, 1, bias=True))
        main.append(nn.LeakyReLU(negative_slope=0.1, inplace=True))

        # residual blocks
        main.append(
            make_layer(
                ResidualBlockNoBN, num_blocks, mid_channels=out_channels))

        self.main = nn.Sequential(*main)

    def forward(self, feat):
        """Forward function for ResidualBlocksWithInputConv.

        Args:
            feat (Tensor): Input feature with shape (n, in_channels, h, w)

        Returns:
            Tensor: Output feature with shape (n, out_channels, h, w)
        """
        return self.main(feat)


class SPyNet(BaseModule):
    """SPyNet network structure.

    The difference to the SPyNet in [tof.py] is that
        1. more SPyNetBasicModule is used in this version, and
        2. no batch normalization is used in this version.

    Paper:
        Optical Flow Estimation using a Spatial Pyramid Network, CVPR, 2017

    Args:
        pretrained (str): path for pre-trained SPyNet. Default: None.
    """

    def __init__(self, pretrained):
        super().__init__()

        self.basic_module = nn.ModuleList(
            [SPyNetBasicModule() for _ in range(6)])

        if isinstance(pretrained, str):
            logger = MMLogger.get_current_instance()
            load_checkpoint(self, pretrained, strict=True, logger=logger)
        elif pretrained is not None:
            raise TypeError('[pretrained] should be str or None, '
                            f'but got {type(pretrained)}.')

        self.register_buffer(
            'mean',
            torch.Tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer(
            'std',
            torch.Tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def compute_flow(self, ref, supp):
        """Compute flow from ref to supp.

        Note that in this function, the images are already resized to a
        multiple of 32.

        Args:
            ref (Tensor): Reference image with shape of (n, 3, h, w).
            supp (Tensor): Supporting image with shape of (n, 3, h, w).

        Returns:
            Tensor: Estimated optical flow: (n, 2, h, w).
        """
        n, _, h, w = ref.size()

        # normalize the input images
        ref = [(ref - self.mean) / self.std]
        supp = [(supp - self.mean) / self.std]

        # generate downsampled frames
        for level in range(5):
            ref.append(
                F.avg_pool2d(
                    input=ref[-1],
                    kernel_size=2,
                    stride=2,
                    count_include_pad=False))
            supp.append(
                F.avg_pool2d(
                    input=supp[-1],
                    kernel_size=2,
                    stride=2,
                    count_include_pad=False))
        ref = ref[::-1]
        supp = supp[::-1]

        # flow computation
        flow = ref[0].new_zeros(n, 2, h // 32, w // 32)
        for level in range(len(ref)):
            if level == 0:
                flow_up = flow
            else:
                flow_up = F.interpolate(
                    input=flow,
                    scale_factor=2,
                    mode='bilinear',
                    align_corners=True) * 2.0

            # add the residue to the upsampled flow
            flow = flow_up + self.basic_module[level](
                torch.cat([
                    ref[level],
                    flow_warp(
                        supp[level],
                        flow_up.permute(0, 2, 3, 1),
                        padding_mode='border'), flow_up
                ], 1))

        return flow

    def forward(self, ref, supp):
        """Forward function of SPyNet.

        This function computes the optical flow from ref to supp.

        Args:
            ref (Tensor): Reference image with shape of (n, 3, h, w).
            supp (Tensor): Supporting image with shape of (n, 3, h, w).

        Returns:
            Tensor: Estimated optical flow: (n, 2, h, w).
        """

        # upsize to a multiple of 32
        h, w = ref.shape[2:4]
        w_up = w if (w % 32) == 0 else 32 * (w // 32 + 1)
        h_up = h if (h % 32) == 0 else 32 * (h // 32 + 1)
        ref = F.interpolate(
            input=ref, size=(h_up, w_up), mode='bilinear', align_corners=False)
        supp = F.interpolate(
            input=supp,
            size=(h_up, w_up),
            mode='bilinear',
            align_corners=False)

        # compute flow, and resize back to the original resolution
        flow = F.interpolate(
            input=self.compute_flow(ref, supp),
            size=(h, w),
            mode='bilinear',
            align_corners=False)

        # adjust the flow values
        flow[:, 0, :, :] *= float(w) / float(w_up)
        flow[:, 1, :, :] *= float(h) / float(h_up)

        return flow


class SPyNetBasicModule(BaseModule):
    """Basic Module for SPyNet.

    Paper:
        Optical Flow Estimation using a Spatial Pyramid Network, CVPR, 2017
    """

    def __init__(self):
        super().__init__()

        self.basic_module = nn.Sequential(
            ConvModule(
                in_channels=8,
                out_channels=32,
                kernel_size=7,
                stride=1,
                padding=3,
                norm_cfg=None,
                act_cfg=dict(type='ReLU')),
            ConvModule(
                in_channels=32,
                out_channels=64,
                kernel_size=7,
                stride=1,
                padding=3,
                norm_cfg=None,
                act_cfg=dict(type='ReLU')),
            ConvModule(
                in_channels=64,
                out_channels=32,
                kernel_size=7,
                stride=1,
                padding=3,
                norm_cfg=None,
                act_cfg=dict(type='ReLU')),
            ConvModule(
                in_channels=32,
                out_channels=16,
                kernel_size=7,
                stride=1,
                padding=3,
                norm_cfg=None,
                act_cfg=dict(type='ReLU')),
            ConvModule(
                in_channels=16,
                out_channels=2,
                kernel_size=7,
                stride=1,
                padding=3,
                norm_cfg=None,
                act_cfg=None))

    def forward(self, tensor_input):
        """
        Args:
            tensor_input (Tensor): Input tensor with shape (b, 8, h, w).
                8 channels contain:
                [reference image (3), neighbor image (3), initial flow (2)].

        Returns:
            Tensor: Refined flow with shape (b, 2, h, w)
        """
        return self.basic_module(tensor_input)

class RealBasicVSRNet(BaseModule):
    """RealBasicVSR network structure for real-world video super-resolution.

    Support only x4 upsampling.

    Paper:
        Investigating Tradeoffs in Real-World Video Super-Resolution, arXiv

    Args:
        mid_channels (int, optional): Channel number of the intermediate
            features. Default: 64.
        num_propagation_blocks (int, optional): Number of residual blocks in
            each propagation branch. Default: 20.
        num_cleaning_blocks (int, optional): Number of residual blocks in the
            image cleaning module. Default: 20.
        dynamic_refine_thres (int, optional): Stop cleaning the images when
            the residue is smaller than this value. Default: 255.
        spynet_pretrained (str, optional): Pre-trained model path of SPyNet.
            Default: None.
        is_fix_cleaning (bool, optional): Whether to fix the weights of
            the image cleaning module during training. Default: False.
        is_sequential_cleaning (bool, optional): Whether to clean the images
            sequentially. This is used to save GPU memory, but the speed is
            slightly slower. Default: False.
    """

    def __init__(self,
                 mid_channels=64,
                 num_propagation_blocks=20,
                 num_cleaning_blocks=20,
                 dynamic_refine_thres=255,
                 spynet_pretrained=None,
                 is_fix_cleaning=False,
                 is_sequential_cleaning=False):

        super().__init__()

        self.dynamic_refine_thres = dynamic_refine_thres / 255.
        self.is_sequential_cleaning = is_sequential_cleaning

        # image cleaning module
        self.image_cleaning = nn.Sequential(
            ResidualBlocksWithInputConv(3, mid_channels, num_cleaning_blocks),
            nn.Conv2d(mid_channels, 3, 3, 1, 1, bias=True),
        )

        if is_fix_cleaning:  # keep the weights of the cleaning module fixed
            self.image_cleaning.requires_grad_(False)

        # BasicVSR
        self.basicvsr = BasicVSRNet(mid_channels, num_propagation_blocks,
                                    spynet_pretrained)
        self.basicvsr.spynet.requires_grad_(False)

    def forward(self, lqs, return_lqs=False):
        """Forward function for BasicVSR++.

        Args:
            lqs (tensor): Input low quality (LQ) sequence with
                shape (n, t, c, h, w).
            return_lqs (bool): Whether to return LQ sequence. Default: False.

        Returns:
            Tensor: Output HR sequence.
        """
        n, t, c, h, w = lqs.size()

        for _ in range(0, 3):  # at most 3 cleaning, determined empirically
            if self.is_sequential_cleaning:
                residues = []
                for i in range(0, t):
                    residue_i = self.image_cleaning(lqs[:, i, :, :, :])
                    lqs[:, i, :, :, :] += residue_i
                    residues.append(residue_i)
                residues = torch.stack(residues, dim=1)
            else:  # time -> batch, then apply cleaning at once
                lqs = lqs.view(-1, c, h, w)
                residues = self.image_cleaning(lqs)
                lqs = (lqs + residues).view(n, t, c, h, w)

            # determine whether to continue cleaning
            if torch.mean(torch.abs(residues)) < self.dynamic_refine_thres:
                break

        # Super-resolution (BasicVSR)
        outputs = self.basicvsr(lqs)

        if return_lqs:
            return outputs, lqs
        else:
            return outputs