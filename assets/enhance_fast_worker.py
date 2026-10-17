"""Compact restoration with bounded GPU work and motion-checked residual reuse."""
import hashlib,json,os,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cv2
import numpy as np
import torch
from enhance_fast_network import SRVGGNetCompact


def cut(a,b):
    return float(np.mean(cv2.absdiff(cv2.resize(a,(48,32)),cv2.resize(b,(48,32)))))>42


class Finisher:
    def __init__(self):
        self.previous=None;self.cascade=None;self.grids={}

    def apply(self,original,neural,p):
        h,w=original.shape[:2];size=(max(1,round(w*p['upscale'])),max(1,round(h*p['upscale'])))
        raw=cv2.resize(original,size,interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
        neural=np.ascontiguousarray(neural,np.float32)
        low=cv2.GaussianBlur(neural,(0,0),1.1);raw_low=cv2.GaussianBlur(raw,(0,0),1.1)
        clean=cv2.addWeighted(raw,1,cv2.subtract(low,raw_low),p['denoise']/100,0)
        detail=cv2.subtract(cv2.subtract(neural,low),cv2.subtract(raw,raw_low))
        enhanced=cv2.addWeighted(clean,1,detail,.25+.75*p['detail_recovery']/100,0)
        enhanced=cv2.addWeighted(enhanced,1,cv2.subtract(neural,raw),.25*p['deblur']/100,0)
        if p['face_restore']:
            if self.cascade is None:self.cascade=cv2.CascadeClassifier(str(Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml'))
            factor=min(1.,256/max(h,w));small=cv2.resize(original,(max(1,round(w*factor)),max(1,round(h*factor))))
            for x,y,fw,fh in self.cascade.detectMultiScale(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY),1.15,4,minSize=(max(12,round(24*factor)),)*2):
                scale=p['upscale']/factor;x,y,fw,fh=[v*scale for v in (x,y,fw,fh)]
                mask=np.zeros(raw.shape[:2],np.float32);cv2.ellipse(mask,(round(x+fw/2),round(y+fh/2)),(max(1,round(fw*.6)),max(1,round(fh*.65))),0,0,360,1,-1)
                mask=cv2.GaussianBlur(mask,(0,0),max(1,fw*.08));mask=cv2.merge([mask]*3)*(p['face_restore_strength']/100*.35)
                enhanced=cv2.add(enhanced,cv2.multiply(cv2.subtract(neural,enhanced),mask))
        residual=cv2.subtract(enhanced,raw);stability=p['temporal_stability']/100
        if self.previous is not None and stability and not cut(self.previous[0],original):
            old,old_residual=self.previous
            factor=min(1.,256/max(h,w));flow_size=(max(1,round(w*factor)),max(1,round(h*factor)))
            a=cv2.resize(cv2.cvtColor(original,cv2.COLOR_BGR2GRAY),flow_size);b=cv2.resize(cv2.cvtColor(old,cv2.COLOR_BGR2GRAY),flow_size)
            flow=cv2.calcOpticalFlowFarneback(a,b,None,.5,3,15,3,5,1.2,0)
            flow=cv2.resize(flow,size);flow[:,:,0]*=size[0]/flow_size[0];flow[:,:,1]*=size[1]/flow_size[1]
            if size not in self.grids:self.grids={size:np.meshgrid(np.arange(size[0],dtype=np.float32),np.arange(size[1],dtype=np.float32))}
            xx,yy=self.grids[size];mx=cv2.add(xx,flow[:,:,0]);my=cv2.add(yy,flow[:,:,1])
            warped_raw=cv2.remap(cv2.resize(old,size).astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
            distance=cv2.transform(cv2.absdiff(raw,warped_raw),np.array([[1/3,1/3,1/3]],np.float32))
            confidence=cv2.exp(distance*(-1/8));valid=((mx>=0)&(mx<size[0]-1)&(my>=0)&(my<size[1]-1))
            amount=cv2.merge([confidence*valid*(stability*.65)]*3)
            warped=cv2.remap(old_residual,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
            residual=cv2.add(residual,cv2.multiply(cv2.subtract(warped,residual),amount))
        self.previous=(original,residual)
        enhanced=cv2.add(raw,residual)
        if p['sharpen']:
            high=cv2.subtract(enhanced,cv2.GaussianBlur(enhanced,(0,0),.7)).clip(-12,12)
            enhanced=cv2.addWeighted(enhanced,1,high,p['sharpen']/100*.6,0)
        enhanced=cv2.addWeighted(raw,1-p['mix']/100*p['enhancement_strength']/100,enhanced,p['mix']/100*p['enhancement_strength']/100,0)
        if not np.isfinite(enhanced).all():raise RuntimeError('Restoration produced invalid pixels')
        return np.rint(enhanced).clip(0,255).astype(np.uint8)


class GPUFinisher:
    """Keep full-size image arithmetic on CUDA; flow/detection stay small."""
    def __init__(self,device):
        self.device=device;self.previous=None;self.kernels={};self.grids={};self.cascade=None;self.faces=[];self.number=0

    def blur(self,value,sigma):
        from torch.nn import functional as F
        k=max(1,min(int(round(sigma*8+1))|1,2*min(value.shape[-2:])-1))
        if k<=1:return value
        key=(k,sigma)
        if key not in self.kernels:
            kernel=torch.from_numpy(cv2.getGaussianKernel(k,sigma).astype(np.float32).reshape(1,1,k)).to(self.device)
            self.kernels[key]=(kernel.reshape(1,1,1,k).repeat(3,1,1,1),kernel.reshape(1,1,k,1).repeat(3,1,1,1))
        x,y=self.kernels[key];pad=k//2
        return F.conv2d(F.pad(F.conv2d(F.pad(value,(pad,pad,0,0),mode='reflect'),x,groups=3),(0,0,pad,pad),mode='reflect'),y,groups=3)

    def apply(self,original,neural,p):
        from torch.nn import functional as F
        h,w=original.shape[:2];oh,ow=neural.shape[-2:]
        raw=torch.from_numpy(original[:,:,::-1].copy()).permute(2,0,1)[None].to(self.device,dtype=torch.float32)
        raw=F.interpolate(raw,size=(oh,ow),mode='bicubic',align_corners=False).clamp(0,255)
        neural=neural.float()*255;low=self.blur(neural,1.1);raw_low=self.blur(raw,1.1)
        enhanced=raw+(low-raw_low)*(p['denoise']/100)
        enhanced+=(neural-low-(raw-raw_low))*(.25+.75*p['detail_recovery']/100)
        enhanced+=(neural-raw)*(.25*p['deblur']/100)
        scene_cut=self.previous is not None and cut(self.previous[0],original)
        if p['face_restore']:
            if self.cascade is None:self.cascade=cv2.CascadeClassifier(str(Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml'))
            factor=min(1.,256/max(h,w));small=cv2.resize(original,(max(1,round(w*factor)),max(1,round(h*factor))))
            if self.number%5==0 or scene_cut:
                self.faces=self.cascade.detectMultiScale(cv2.cvtColor(small,cv2.COLOR_BGR2GRAY),1.15,4,minSize=(max(12,round(24*factor)),)*2) if min(small.shape[:2])>=16 else []
            if len(self.faces):
                mask=np.zeros(small.shape[:2],np.float32)
                for x,y,fw,fh in self.faces:cv2.ellipse(mask,(round(x+fw/2),round(y+fh/2)),(max(1,round(fw*.6)),max(1,round(fh*.65))),0,0,360,1,-1)
                mask=cv2.GaussianBlur(mask,(0,0),max(1,small.shape[1]*.02))
                mask=F.interpolate(torch.from_numpy(mask)[None,None].to(self.device),size=(oh,ow),mode='bilinear',align_corners=False)
                enhanced+=(neural-enhanced)*mask*(p['face_restore_strength']/100*.35)
        residual=enhanced-raw;stability=p['temporal_stability']/100
        if self.previous is not None and stability and not scene_cut and min(h,w)>=8:
            old,old_residual=self.previous;factor=min(1.,256/max(h,w));size=(max(1,round(w*factor)),max(1,round(h*factor)))
            a=cv2.resize(cv2.cvtColor(original,cv2.COLOR_BGR2GRAY),size);b=cv2.resize(cv2.cvtColor(old,cv2.COLOR_BGR2GRAY),size)
            flow=cv2.calcOpticalFlowFarneback(a,b,None,.5,3,15,3,5,1.2,0)
            flow=F.interpolate(torch.from_numpy(flow.copy()).permute(2,0,1)[None].to(self.device),size=(oh,ow),mode='bilinear',align_corners=False)
            flow[:,0]*=ow/size[0];flow[:,1]*=oh/size[1]
            if (oh,ow) not in self.grids:
                yy,xx=torch.meshgrid(torch.arange(oh,device=self.device,dtype=torch.float32),torch.arange(ow,device=self.device,dtype=torch.float32),indexing='ij')
                self.grids={(oh,ow):(xx,yy)}
            xx,yy=self.grids[(oh,ow)];mx=xx+flow[0,0];my=yy+flow[0,1]
            grid=torch.stack((mx/max(1,ow-1)*2-1,my/max(1,oh-1)*2-1),dim=-1)[None]
            old_raw=torch.from_numpy(old[:,:,::-1].copy()).permute(2,0,1)[None].to(self.device,dtype=torch.float32)
            old_raw=F.interpolate(old_raw,size=(oh,ow),mode='bicubic',align_corners=False).clamp(0,255)
            warped_raw=F.grid_sample(old_raw,grid,mode='bilinear',padding_mode='reflection',align_corners=True)
            confidence=torch.exp(-(raw-warped_raw).abs().mean(dim=1,keepdim=True)/8)
            valid=((mx>=0)&(mx<ow-1)&(my>=0)&(my<oh-1))[None,None]
            amount=confidence*valid*stability*.65
            warped=F.grid_sample(old_residual,grid,mode='bilinear',padding_mode='reflection',align_corners=True)
            residual=residual+(warped-residual)*amount
        self.previous=(original,residual);self.number+=1
        enhanced=raw+residual
        if p['sharpen']:enhanced+=(enhanced-self.blur(enhanced,.7)).clamp(-12,12)*(p['sharpen']/100*.6)
        enhanced=raw+(enhanced-raw)*(p['mix']/100*p['enhancement_strength']/100)
        if not torch.isfinite(enhanced).all():raise RuntimeError('Restoration produced invalid pixels')
        return np.ascontiguousarray(enhanced.round().clamp(0,255).byte()[0].cpu().permute(1,2,0).numpy()[:,:,::-1])


def parent_guard(pid):
    """A kernel process handle avoids PID reuse and kills orphaned inference."""
    if not pid:return
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
        api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];api.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=api.OpenProcess(0x100000,False,pid)
        if not handle:raise RuntimeError('Could not bind inference lifetime to the editor')
        def watch():
            try:
                while api.WaitForSingleObject(handle,200)==258:pass
                os._exit(3)
            finally:api.CloseHandle(handle)
    else:
        def watch():
            while os.getppid()==pid:time.sleep(.2)
            os._exit(3)
    threading.Thread(target=watch,daemon=True,name='enhance-parent-lifetime').start()


class Budget:
    def __init__(self,device,duty):
        self.device=device;self.duty=max(.2,min(.8,float(duty)));self.gpu=0.;self.sleep=0.
    def synchronize(self):
        if self.device.type=='cuda':torch.cuda.synchronize(self.device)
    def finish(self,began,gpu_done):
        work=gpu_done-began;self.gpu+=work
        delay=max(0,work/self.duty-(time.monotonic()-began))
        if delay:time.sleep(delay);self.sleep+=delay


def infer(model,original,device,scale,limit,keep_tensor=False):
    h,w=original.shape[:2];oh,ow=max(1,round(h*scale)),max(1,round(w*scale))
    # Core tiles have a complete network receptive-field halo. Small webcam
    # crops fit a single pass; large frames cannot allocate unbounded GPU memory.
    whole=h*w<=limit and max(h,w)<=1024;core=256;halo=36
    output=None if whole and keep_tensor else np.empty((oh,ow,3),np.float32)
    for y in ([0] if whole else range(0,h,core)):
        for x in ([0] if whole else range(0,w,core)):
            bottom,right=(h,w) if whole else (min(h,y+core),min(w,x+core))
            top,left=max(0,y-halo),max(0,x-halo);end_y,end_x=min(h,bottom+halo),min(w,right+halo)
            patch=original[top:end_y,left:end_x,::-1].copy()
            tensor=torch.from_numpy(patch).permute(2,0,1)[None].to(device=device,dtype=next(model.parameters()).dtype)/255
            with torch.no_grad():
                result=model(tensor).clamp(0,1)
                # Transfer only requested output size, not all 4x RGB frames.
                result=torch.nn.functional.interpolate(result,size=(max(1,round((end_y-top)*scale)),max(1,round((end_x-left)*scale))),mode='bilinear',align_corners=False)
                if whole and keep_tensor:return result
                result=result[0].float().cpu().permute(1,2,0).numpy()[:,:,::-1]
            sy,sx=round(y*scale),round(x*scale);ey,ex=round(bottom*scale),round(right*scale)
            py,px=sy-round(top*scale),sx-round(left*scale)
            output[sy:ey,sx:ex]=result[py:py+ey-sy,px:px+ex-sx]*255
    return output


def main(config_path):
    config=json.loads(Path(config_path).read_text());parent_guard(config.get('parent_pid'))
    torch.set_num_threads(2);cv2.setNumThreads(2)
    p=config['parameters'];output=Path(config['output']);output.mkdir(parents=True,exist_ok=True)
    states=[]
    for path,digest in config['models']:
        path=Path(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Restoration model integrity check failed')
        states.append(torch.load(path,map_location='cpu',weights_only=True)['params'])
    strong=p['denoise']/100;model=SRVGGNetCompact()
    model.load_state_dict({k:states[0][k]*strong+states[1][k]*(1-strong) for k in states[0]},strict=True)
    requested=config.get('backend','Auto')
    if requested not in ('Auto','CUDA','DirectML'):raise RuntimeError('Unknown GPU backend')
    if torch.cuda.is_available() and requested!='DirectML':
        device=torch.device('cuda');backend='CUDA'
        total=torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(.4,1024**3/total),0)
        if p['quality_mode']!='Maximum':model.half()
    else:
        if requested=='CUDA':raise RuntimeError('CUDA is unavailable; inference was stopped without a CPU retry.')
        try:
            import torch_directml
            if not torch_directml.is_available():raise RuntimeError('DirectML unavailable')
            device=torch_directml.device();backend='DirectML'
        except (ImportError,RuntimeError) as error:
            raise RuntimeError('No usable GPU backend. Choose the CUDA or DirectML optional download; no slow CPU fallback was started.') from error
    model.eval().to(device);budget=Budget(device,config.get('gpu_duty',.5));finisher=Finisher();gpu_finisher=GPUFinisher(device) if device.type=='cuda' else None
    capture=cv2.VideoCapture(config['input']);emitted=0;start=time.monotonic()
    print(json.dumps(dict(phase='ready',frames=0,backend=backend)),flush=True)
    try:
        while True:
            ok,original=capture.read()
            if not ok:break
            if max(original.shape[:2])*p['upscale']>8192:raise RuntimeError('Enhancement output exceeds 8192 pixels')
            began=time.monotonic();cleanup=p['compression_cleanup']/100
            source=cv2.addWeighted(original,1-cleanup*.5,cv2.bilateralFilter(original,5,18,3),cleanup*.5,0) if cleanup else original
            restored=infer(model,source,device,p['upscale'],196608 if p['quality_mode'] in ('Preview','Balanced') else 262144,keep_tensor=gpu_finisher is not None)
            if isinstance(restored,torch.Tensor):enhanced=gpu_finisher.apply(original,restored,p)
            else:enhanced=finisher.apply(original,restored,p)
            budget.synchronize();gpu_done=time.monotonic()
            if not cv2.imwrite(str(output/f'{emitted:08d}.png'),enhanced,[cv2.IMWRITE_PNG_COMPRESSION,1]):raise RuntimeError('Could not save enhanced frame')
            budget.finish(began,gpu_done);emitted+=1
            print(json.dumps(dict(frames=emitted,backend=backend,seconds=time.monotonic()-start)),flush=True)
    finally:
        capture.release()
    if not emitted:raise RuntimeError('No video frames were restored')
    record=dict(frames=emitted,backend=backend,engine='compact-v1',seconds=time.monotonic()-start,gpu_work_seconds=budget.gpu,scheduler_sleep_seconds=budget.sleep)
    if device.type=='cuda':record['peak_gpu_mb']=torch.cuda.max_memory_allocated()/1024**2
    (output/'worker.json').write_text(json.dumps(record))


if __name__=='__main__':main(sys.argv[1])
