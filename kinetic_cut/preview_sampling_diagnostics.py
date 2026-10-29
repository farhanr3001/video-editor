"""Opt-in native preview sampling checks. Inputs are read-only fixture paths."""
import json,os,time,traceback
from pathlib import Path


def sampling_state(surface):
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtCore import QPointF
    grids={}
    for key,layer in surface.layers.items():
        if not layer.isVisible():continue
        size=layer.property('rasterSize');capture=layer.findChild(QQuickItem,'gradedTexture')
        origin=layer.mapToScene(QPointF(0,0));corner=layer.mapToScene(QPointF(layer.width(),layer.height()))
        grids[key]=dict(origin=[origin.x(),origin.y()],corner=[corner.x(),corner.y()],size=[size.width(),size.height()],intermediate=bool(capture and capture.property('sourceItem')),width=layer.width(),height=layer.height())
    return dict(image_sampling={k:dict(mipmap=v.property('mipmap'),minification=v.property('minification')) for k,v in surface.layer_images.items() if k in surface._used_textures},sampling_time=surface.canvas.project.playhead,sampling_grids=grids,texture_progress={k:v.property('progress') for k,v in surface.layer_images.items() if k in surface._used_textures},source_frame_us={str(k):v.get('stamp') for k,v in surface.sources.items() if v.get('ready')},sampling_dpr=surface.view.devicePixelRatio())


def run(output):
    os.environ['KINETIC_SAMPLING_DIAGNOSTIC']='1'
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    config=json.loads(Path(os.environ['KINETIC_SAMPLING_FIXTURES']).read_text(encoding='utf-8'))
    import hashlib,copy,sys
    import numpy as np
    from PIL import Image
    from PySide6.QtCore import QEventLoop,QTimer,QRectF
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Crop
    from .visual_fx import default_visual_fx,evaluate_visual_fx,apply_visual_fx_to_transform
    from .ui import MainWindow
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
    report=dict(passed=False,cases=[],checks=[],private_desktop=os.environ.get('KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP'),frozen=bool(getattr(sys,'frozen',False)))
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def check(name,condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        if not condition:save();raise AssertionError(name)
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def array(q):
        q=q.convertToFormat(QImage.Format_RGBA8888)
        return np.frombuffer(q.constBits(),np.uint8).reshape(q.height(),q.width(),4)[...,:3].copy()
    protected={v['path']:hashlib.sha256(Path(v['path']).read_bytes()).hexdigest() for v in config['media']}
    w=None;peer=None
    try:
        w=MainWindow();w.resize(1700,1000);w.autosave_timer.stop();w.preview_quality.request=lambda:None
        w.request_waveform=lambda _:None;w.preview.setFixedSize(640,720);w.preview.set_transform_controls_visible(False)
        w.show();w.transport.set_monitor_gain(0.);wait(500);gpu=w.preview.gpu;peer=getattr(gpu,'peer',None)
        if peer:
            original_collect=gpu.collect
            def observed_collect():
                if gpu.peer.error:
                    errors=report.setdefault('renderer_errors',[])
                    if gpu.peer.error not in errors:errors.append(gpu.peer.error)
                original_collect()
            gpu.status_timer.timeout.disconnect(gpu.collect);gpu.status_timer.timeout.connect(observed_collect)
        check('native preview enabled',gpu is not None)
        count=int(os.environ.get('KINETIC_SAMPLING_FRAMES','18'));scope=os.environ.get('KINETIC_SAMPLING_SCOPE','full')
        for entry in ([] if os.environ.get('KINETIC_SAMPLING_COMPOSITOR_ONLY')=='1' else config['media']):
            path=Path(entry['path']);is_video=entry['kind']=='video';source=None if is_video else Image.open(path).convert('RGB')
            for effect_name in ['Slow Push-In','Smooth Zoom','Punch Zoom']:
                if scope=='dpi' and effect_name!='Slow Push-In':continue
                for display_width in [324,600,941]:
                    if scope=='dpi' and display_width==600:continue
                    report['current_case']=[entry['name'],effect_name,display_width]
                    media=MediaItem('sample',str(path),entry['kind'],path.name,6,entry['width'],entry['height'],entry.get('fps',60),False)
                    effect=default_visual_fx(effect_name);item=TimelineItem('clip',media.id,'video_1',0,6,transform=Transform(y=.5),effects=[effect])
                    project=Project(settings=ProjectSettings(width=entry['width'],height=entry['height'],fps=60,blur=0),media=[media],timeline=[item])
                    w.set_project(project);w.preview.set_transform_controls_visible(False);w.transport.set_monitor_gain(0.)
                    w.preview.view_zoom=1.;base=w.preview.composition_rect();w.preview.view_zoom=display_width/base.width();w.preview.update();w.seek(0.)
                    wait(200)
                    deadline=time.monotonic()+10
                    def ready():
                        d=gpu.diagnostics()
                        return gpu.frames>0 and (bool(d.get('gpu_source_frames')) if is_video else d.get('texture_progress',{}).get('file:'+str(path),0)>=1)
                    while not ready() and time.monotonic()<deadline:wait(30)
                    if not ready():report['not_ready']=gpu.diagnostics()
                    check('current media ready before sampling',ready())
                    frame=w.preview.composition_rect();folder=out/(entry['name']+'-'+effect_name.replace(' ','_')+'-'+str(display_width));folder.mkdir(exist_ok=True)
                    errors=[];temporal=[];previous=None;grids=[];samples=[];pictures=[];reference_frames=[]
                    span=1.5 if effect_name!='Punch Zoom' else .45
                    for n in range(count):
                        at=n/max(1,count-1)*span;w.seek(at);wait(45 if not is_video else 100)
                        # A first capture can precede the render-thread polish
                        # of new anchored geometry. Keep the scene paused and
                        # verify the current epoch after another rendered frame.
                        gpu.view.grabWindow();wait(30)
                        image=gpu.view.grabWindow();check('nonempty native capture',not image.isNull())
                        pixels=array(image);dpr=pixels.shape[1]/w.preview.width()
                        # Compare exactly the captured physical pixel footprint,
                        # including fractional canvas origin, zoom and device scale.
                        x0=max(0,int(np.ceil(frame.left()*dpr)))+4;y0=max(0,int(np.ceil(frame.top()*dpr)))+4
                        x1=min(pixels.shape[1],int(np.floor(frame.right()*dpr)))-4;y1=min(pixels.shape[0],int(np.floor(frame.bottom()*dpr)))-4
                        crop=pixels[y0:y1,x0:x1]
                        if not (crop.size>100 and float(crop.std())>1.):
                            image.save(str(out/'failed-full-capture.png'));report['failed_frame']=dict(index=n,frame=[frame.x(),frame.y(),frame.width(),frame.height()],region=[x0,y0,x1,y1],diagnostics=gpu.diagnostics())
                        check('fine-detail region visible',crop.size>100 and float(crop.std())>1.)
                        shown=copy.copy(item);shown.transform=copy.copy(item.transform)
                        fx=evaluate_visual_fx(shown,at,project.settings.width,project.settings.height);apply_visual_fx_to_transform(shown.transform,fx)
                        target=w.preview._layer_rect(shown,QImage(1,1,QImage.Format_RGB32),frame)
                        wait(25);diag=gpu.diagnostics()
                        check('captured scene uses current transform time',abs(diag.get('sampling_time',-1)-at)<1e-6)
                        grids.append(diag.get('sampling_grids',{}));samples.append(dict(at=at,scale=shown.transform.scale,target=[target.x(),target.y(),target.width(),target.height()],source_frame_us=diag.get('source_frame_us',{})))
                        if source is not None:
                            sw,sh=source.size;box=((x0/dpr-target.left())/target.width()*sw,(y0/dpr-target.top())/target.height()*sh,(x1/dpr-target.left())/target.width()*sw,(y1/dpr-target.top())/target.height()*sh)
                            ref=np.array(source.resize((x1-x0,y1-y0),Image.Resampling.LANCZOS,box=box)).astype(np.float32)
                            err=crop.astype(np.float32)-ref;errors.append(float(np.sqrt(np.mean(err**2))))
                            if previous is not None:temporal.append(float(np.sqrt(np.mean((err-previous)**2))))
                            previous=err
                            if n in (0,count//2,count-1):Image.fromarray(ref.astype(np.uint8)).save(folder/f'reference-{n:03}.png')
                        pictures.append(crop)
                        if entry['name']!='smooth' and os.environ.get('KINETIC_SAMPLING_SAVE_FRAMES','1')=='1' and (display_width==324 or n in (0,count-1)):Image.fromarray(crop).save(folder/f'{n:03}.png')
                    diag=gpu.diagnostics();check('actual Direct3D11 composition',diag.get('graphics_backend')=='Direct3D11')
                    if is_video:
                        check('real video delivered native frames',diag.get('gpu_source_frames',0)>0 and bool(diag.get('active_decoders')))
                        check('real video pixels move',float(np.mean(np.abs(pictures[-1].astype(float)-pictures[0])))>1.)
                    distinct={tuple(v['size']) for g in grids for v in g.values()}
                    baseline=os.environ.get('KINETIC_SAMPLING_BASELINE')=='1'
                    if not baseline:
                        check('animated clip never reallocates processing grid',len(distinct)==1)
                        check('ordinary zoom bypasses intermediate captures',all(not v['intermediate'] for g in grids for v in g.values()))
                    row=dict(media=entry['name'],kind=entry['kind'],effect=effect_name,display_width=display_width,dpr=dpr,frames=count,rmse_reference=float(np.mean(errors)) if errors else None,temporal_residual=float(np.mean(temporal)) if temporal else None,distinct_grids=len(distinct),samples=samples,diagnostics=diag)
                    report['cases'].append(row);save();print(json.dumps({k:row[k] for k in ['media','effect','display_width','dpr','temporal_residual','distinct_grids']}),flush=True)
        # Paused crop/grade/alpha/ellipse and blur toggles use the same real preview.
        entry=config['media'][0];media=MediaItem('guard',entry['path'],'image','guard',2,entry['width'],entry['height'])
        item=TimelineItem('guard','guard','video_1',0,2,crop=Crop(.1,.08,.8,.84),transform=Transform(y=.5),brightness=.1,saturation=.6,opacity=75)
        project=Project(settings=ProjectSettings(width=entry['width'],height=entry['height'],fps=60,blur=0),media=[media],timeline=[item]);w.set_project(project);w.preview.view_zoom=1.2;w.preview.set_transform_controls_visible(False)
        guards=[]
        for blur in (0,3,0):
            item.effects=[dict(name='Gaussian Blur',horizontal=blur,vertical=blur+1 if blur else 0,blend=100,border='Reflect',enabled=True)]
            w.project.touch();w.transport.sync(True);wait(150);im=gpu.view.grabWindow();guards.append(array(im));im.save(str(out/f'crop-colour-blur-{len(guards)}.png'))
        check('blur changes real pixels',float(np.mean(np.abs(guards[1].astype(float)-guards[0])))>.1)
        check('return to zero blur preserves crop and grade',float(np.max(np.abs(guards[2].astype(float)-guards[0])))<=1)
        check('owner fixture bytes unchanged',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in protected.items()))
        if os.environ.get('KINETIC_SAMPLING_COMPOSITOR_ONLY')=='1':
            # Existing native pixel assertions, selected without unrelated
            # timeline input assumptions tied to an unavailable owner source.
            w.preview.setMinimumSize(0,0);w.preview.setMaximumSize(16777215,16777215);w.preview.view_zoom=1.;wait(100)
            from .creative_diagnostics import preview_checks
            from .transition_diagnostics import preview_checks as transitions
            from .gpu_diagnostics import composition_checks
            preview_checks(w,out,check,wait);transitions(w,out,check,wait);composition_checks(w,out,check,wait)
        report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc());save();raise
    finally:
        if w:
            w.transport.pause();w.close();deadline=time.monotonic()+12
            while peer and peer.active and time.monotonic()<deadline:wait(30)
            report['renderer_closed']=not peer or not peer.active and peer.exitcode==0 and not peer.forced_shutdown
            report['passed']=report['passed'] and report['renderer_closed']
        save()
    return 0 if report['passed'] else 1
