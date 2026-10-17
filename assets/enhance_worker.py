"""Isolated temporal inference. Invoked only after explicit component setup."""
import json,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cv2
import numpy as np
import torch
from enhance_network import RealBasicVSRNet


def device():
    if torch.cuda.is_available():return torch.device('cuda'), 'CUDA'
    try:
        import torch_directml
        if torch_directml.is_available():return torch_directml.device(), 'DirectML'
    except (ImportError,RuntimeError):pass
    return torch.device('cpu'), 'CPU'


def cut(a,b):
    a=cv2.resize(a,(48,32));b=cv2.resize(b,(48,32))
    return float(np.mean(np.abs(a.astype(np.float32)-b)))>42


def infer(model,frames,dev,tile,scale=4.,selection=None):
    """Overlapping spatial tiles; each tile includes the entire temporal window."""
    h,w=frames[0].shape[:2];selection=list(range(len(frames))) if selection is None else list(selection)
    oh,ow=max(1,round(h*scale)),max(1,round(w*scale))
    out=np.zeros((len(selection),oh,ow,3),np.float32);weights=np.zeros((oh,ow,1),np.float32)
    overlap=24;stride=max(32,tile-overlap*2)
    ys=list(range(0,max(1,h-tile+1),stride));xs=list(range(0,max(1,w-tile+1),stride))
    if ys[-1]!=max(0,h-tile):ys.append(max(0,h-tile))
    if xs[-1]!=max(0,w-tile):xs.append(max(0,w-tile))
    for y in ys:
        for x in xs:
            values=np.stack([f[y:min(h,y+tile),x:min(w,x+tile),::-1].copy() for f in frames]).astype(np.float32)/255
            th,tw=values.shape[1:3];ph=max(0,64-th);pw=max(0,64-tw)
            tensor=torch.from_numpy(values).permute(0,3,1,2)[None].to(dev)
            if ph or pw:
                tensor=torch.nn.functional.pad(tensor.reshape(-1,3,th,tw),(0,pw,0,ph),mode='replicate').reshape(1,len(frames),3,th+ph,tw+pw)
            with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16,enabled=dev.type=='cuda' and getattr(model,'use_fp16',False)):
                result=model(tensor)[0,:,:,:th*4,:tw*4].clamp(0,1).float().cpu().permute(0,2,3,1).numpy()[...,::-1]*255
            top,left=round(y*scale),round(x*scale);bottom,right=round((y+th)*scale),round((x+tw)*scale)
            sh,sw=bottom-top,right-left
            result=np.stack([cv2.resize(result[i],(sw,sh),interpolation=cv2.INTER_AREA if scale<4 else cv2.INTER_LINEAR) for i in selection])
            if not np.isfinite(result).all():raise RuntimeError('Restoration produced invalid pixels')
            wy=np.minimum(np.arange(sh)+1,np.arange(sh,0,-1));wx=np.minimum(np.arange(sw)+1,np.arange(sw,0,-1))
            feather=np.minimum(wy[:,None],wx[None,:]).clip(1,max(1,overlap*scale)).astype(np.float32)[...,None]
            out[:,top:bottom,left:right]+=result*feather;weights[top:bottom,left:right]+=feather
    return out/np.maximum(weights,1)


def finish(original,restored,p,previous):
    scale=p['upscale'];h,w=original.shape[:2];size=(max(1,round(w*scale)),max(1,round(h*scale)))
    raw=cv2.resize(original,size,interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
    neural=cv2.resize(restored,size,interpolation=cv2.INTER_AREA if scale<4 else cv2.INTER_LINEAR)
    low=cv2.GaussianBlur(neural,(0,0),1.1)
    # Independent conservative controls over learned restoration bands, not
    # fabricated text/face generation or an unsharp-mask substitute for the model.
    detail=p['detail_recovery']/100;deblur=p['deblur']/100;denoise=p['denoise']/100
    smooth=cv2.GaussianBlur(raw,(0,0),.8)
    clean=raw+(low-cv2.GaussianBlur(raw,(0,0),1.1))*denoise
    restored=clean+(neural-low-(raw-cv2.GaussianBlur(raw,(0,0),1.1)))*(.25+.75*detail)
    restored+=(neural-raw)*(.25*deblur)
    if p['face_restore']:
        cascade=cv2.CascadeClassifier(str(Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml'))
        for x,y,fw,fh in cascade.detectMultiScale(cv2.cvtColor(original,cv2.COLOR_BGR2GRAY),1.15,4,minSize=(24,24)):
            mask=np.zeros(raw.shape[:2],np.float32);cv2.ellipse(mask,(round((x+fw/2)*scale),round((y+fh/2)*scale)),(max(1,round(fw*.6*scale)),max(1,round(fh*.65*scale))),0,0,360,1,-1)
            mask=cv2.GaussianBlur(mask,(0,0),max(1,fw*scale*.08))[...,None]
            restored+=(neural-restored)*mask*(p['face_restore_strength']/100*.35)
    residual=restored-raw
    stability=p['temporal_stability']/100
    if previous is not None and stability and not cut(previous[0],original):
        old,old_residual=previous
        a=cv2.cvtColor(original,cv2.COLOR_BGR2GRAY);b=cv2.cvtColor(old,cv2.COLOR_BGR2GRAY)
        flow=cv2.calcOpticalFlowFarneback(a,b,None,.5,3,15,3,5,1.2,0)
        flow=cv2.resize(flow,size)*scale
        xx,yy=np.meshgrid(np.arange(size[0],dtype=np.float32),np.arange(size[1],dtype=np.float32))
        mx=xx+flow[...,0];my=yy+flow[...,1]
        warped_raw=cv2.remap(cv2.resize(old,size).astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        confidence=np.exp(-np.mean(np.abs(raw-warped_raw),axis=2,keepdims=True)/8)
        valid=((mx>=0)&(mx<size[0]-1)&(my>=0)&(my<size[1]-1))[...,None]
        warped=cv2.remap(old_residual,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        amount=confidence*valid*stability*.65;residual=residual*(1-amount)+warped*amount
    sharpen=p['sharpen']/100
    enhanced=raw+residual
    if sharpen:enhanced+=np.clip(enhanced-cv2.GaussianBlur(enhanced,(0,0),.7),-12,12)*sharpen*.6
    amount=p['enhancement_strength']/100*p['mix']/100
    return np.rint(raw+(enhanced-raw)*amount).clip(0,255).astype(np.uint8),(original,residual)


def main(config_path):
    config=json.loads(Path(config_path).read_text());p=config['parameters'];output=Path(config['output']);output.mkdir(exist_ok=True)
    torch.set_num_threads(2)
    weights=Path(config['model']);digest=hashlib.sha256(weights.read_bytes()).hexdigest()
    if digest!=config['model_sha256']:raise RuntimeError('Restoration model integrity check failed')
    checkpoint=torch.load(weights,map_location='cpu',weights_only=True)
    state=checkpoint.get('state_dict',checkpoint)
    prefix='generator_ema.' if any(k.startswith('generator_ema.') for k in state) else 'generator.'
    state={k.removeprefix(prefix):v for k,v in state.items() if k.startswith(prefix)}
    model=RealBasicVSRNet();model.load_state_dict(state,strict=True);model.eval();dev,backend=device();model.to(dev)
    model.use_fp16=p['quality_mode']!='Maximum'
    core,context,tile={'Preview':(8,1,160),'Balanced':(8,4,160),'High':(12,6,192),'Maximum':(16,8,256)}[p['quality_mode']]
    capture=cv2.VideoCapture(config['input']);buffer=[];offset=0;emitted=0;previous=None;finished=False;start=time.monotonic()
    try:
        while True:
            while not finished and len(buffer)<core+context*2:
                ok,image=capture.read()
                if not ok:finished=True;break
                buffer.append(image)
                frame_bytes=image.shape[0]*image.shape[1]*p['upscale']**2*3*4
                core=min(core,max(1,int(128*1024**2/max(1,frame_bytes))))
            if offset>=len(buffer):break
            end=min(len(buffer),offset+core);left=max(0,offset-context);right=min(len(buffer),end+context)
            # Never propagate features through a hard cut.
            bounds=[left]+[i for i in range(left+1,right) if cut(buffer[i-1],buffer[i])]+[right]
            predictions={}
            for lo,hi in zip(bounds,bounds[1:]):
                if hi<=offset or lo>=end:continue
                inputs=buffer[lo:hi];cleanup=p['compression_cleanup']/100
                if cleanup:inputs=[cv2.addWeighted(f,1-cleanup*.5,cv2.bilateralFilter(f,5,18,3),cleanup*.5,0) for f in inputs]
                selection=range(max(offset,lo)-lo,min(end,hi)-lo)
                try:restored=infer(model,inputs,dev,tile,p['upscale'],selection)
                except (RuntimeError,NotImplementedError) as error:
                    if backend=='CPU':raise
                    print('GPU fallback: '+str(error),file=sys.stderr,flush=True)
                    dev=torch.device('cpu');backend='CPU (GPU operation unavailable)';model.to(dev);restored=infer(model,inputs,dev,tile,p['upscale'],selection)
                for result_index,i in enumerate(range(max(offset,lo),min(end,hi))):predictions[i]=restored[result_index]
            for i in range(offset,end):
                image,previous=finish(buffer[i],predictions[i],p,previous)
                if not cv2.imwrite(str(output/f'{emitted:08d}.png'),image):raise RuntimeError('Could not save enhanced frame')
                emitted+=1
            print(json.dumps({'frames':emitted,'backend':backend,'seconds':time.monotonic()-start}),flush=True)
            keep=max(0,end-context);buffer=buffer[keep:];offset=end-keep
    finally:capture.release()
    if not emitted:raise RuntimeError('No video frames were restored')
    (output/'worker.json').write_text(json.dumps({'frames':emitted,'backend':backend,'seconds':time.monotonic()-start}))

if __name__=='__main__':main(sys.argv[1])
