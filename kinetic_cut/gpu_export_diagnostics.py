"""Headless native export correctness/cancellation checks; no speed benchmark."""
def run(output):
    import os,json,math,threading
    from pathlib import Path
    import numpy as np
    from PIL import Image
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home');os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Caption,CaptionStyle
    from .exporter import ExportPreset,export
    from .gpu_export import prepare_recipe,render_native,mux_command
    from .export_process import render
    from .process import run as command
    report=dict(checks=[],benchmark=False)
    def check(name,condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        assert condition,name
    y,x=np.mgrid[:180,:320]
    pixels=np.stack([40+160*x/320,40+160*y/180,80+50*np.sin(x/18)],axis=2).astype(np.uint8)
    source=out/'pattern.png';Image.fromarray(pixels).save(source)
    def decoded(path):
        import av
        with av.open(str(path)) as movie:return np.array([f.to_ndarray(format='rgb24') for f in movie.decode(video=0)]).astype(float)
    results=[]
    from .creative_effects import NAMES as CREATIVE_NAMES, default_effect
    for name in (*CREATIVE_NAMES,'creative-stack','creative-window','finishing-flip','finishing-stack','finishing-animation','retime-finishing','blur','grade','matrix','key','sharpen','mask','background','animation','titles','hevc','120fps','video-untagged','video-bt709','video-full-range'):
        directory=out/name;directory.mkdir(exist_ok=True);fps=120 if name=='120fps' else 60
        item=TimelineItem('i','m','video_1',0,.2,transform=Transform(x=.5,y=.5))
        project=Project(settings=ProjectSettings(width=320,height=180,fps=fps),media=[MediaItem('m',str(source),'image','Pattern',1,320,180)],timeline=[item])
        if name.startswith('video-'):
            video=directory/'source.mp4';large=np.array(Image.fromarray(pixels).resize((1280,720)))
            options=[]
            if name=='video-bt709':options=['-vf','scale=out_color_matrix=bt709:out_range=tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709']
            if name=='video-full-range':options=['-vf','scale=out_range=pc','-color_range','pc']
            result=command(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1280x720','-r','60','-i','pipe:0',*options,'-c:v','libx264','-crf','10','-pix_fmt','yuv420p',str(video)],input=np.broadcast_to(large,(12,720,1280,3)).tobytes(),capture_output=True)
            check(name+' source fixture completes',result.returncode==0)
            project.media=[MediaItem('m',str(video),'video','Video colour fixture',.2,1280,720,60)]
        if name in CREATIVE_NAMES:item.effects=[default_effect(name,item)]
        if name=='creative-stack':item.effects=[default_effect('Duotone',item),dict(name='Gaussian Blur',horizontal=8,vertical=8,blend=65),default_effect('Color Tint',item),default_effect('Invert Colors',item)]
        if name=='creative-window':
            item.in_point=.23;item.effects=[default_effect('Color Flash')];item.effects[0]['speed']=3.1;item.effects[0]['phase']=28
        if name=='finishing-flip':
            from .model import Crop
            item.crop=Crop(.1,.1,.8,.8);item.transform.flip_horizontal=item.transform.flip_vertical=True;item.transform.rotation=15
            item.effects=[default_effect('Mosaic Pixelate'),default_effect('Vignette')]
        if name=='finishing-stack':item.effects=[default_effect('Soft Glow'),dict(name='Gaussian Blur',horizontal=8,vertical=8,blend=65),default_effect('Chromatic Aberration'),default_effect('Vignette')]
        if name=='finishing-animation':
            item.effects=[default_effect('Vignette'),default_effect('Wave Distortion')];item.keyframes={'scale':[dict(time=0,value=.6),dict(time=.2,value=1.)],'rotation':[dict(time=0,value=-12),dict(time=.2,value=22)]}
        if name=='retime-finishing':item.speed=.5;item.effects=[default_effect('RGB Glitch'),default_effect('Lens Distortion')]
        if name=='blur':item.effects=[dict(name='Gaussian Blur',horizontal=28,vertical=14,blend=65)]
        if name=='grade':item.brightness=.15;item.contrast=1.2;item.saturation=.7
        if name=='matrix':item.effects=[dict(name='Sepia',amount=45),dict(name='Warm Tone',amount=50)]
        if name=='key':item.effects=[dict(name='Chroma Key',color='#789060',similarity=15,softness=12)]
        if name=='sharpen':item.sharpen=.5
        if name=='mask':item.crop_softness=20;item.transform.shape='circle';item.transform.scale=.8
        if name=='background':item.role='background'
        if name=='animation':item.keyframes={'scale':[dict(time=0,value=.5),dict(time=.2,value=1.)],'rotation':[dict(time=0,value=-12),dict(time=.2,value=22)]}
        if name=='titles':
            project.timeline.append(TimelineItem('title','','video_1',0,.2,role='title',title_text='GPU title',title_style=CaptionStyle(size=22,animation='none')))
            project.captions=[Caption('caption',.05,.15,'Subtitle',style=CaptionStyle(size=18,position_y=.85,animation='none'),customize=True)]
        preset=ExportPreset('Native check','h265' if name=='hevc' else 'h264',15,192,'Native check','auto')
        job=prepare_recipe(project,preset,directory,True,{},'ffmpeg',None,None)
        status=render_native(job,directory)
        target=directory/'gpu.mp4';code,tail=render(mux_command(project,job,str(target),preset,'ffmpeg',False),project.duration)
        check(name+' GPU output completes',code==0 and status['composition']=='Direct3D11 GPU' and status['encoder']=='NVENC D3D11 texture')
        actual=decoded(target)
        if name in CREATIVE_NAMES or name.startswith('finishing-') or name=='retime-finishing':
            from PySide6.QtCore import QRectF
            from PySide6.QtGui import QImage
            from .preview_compositor import SceneContext,render as rasterize
            import copy
            context=SceneContext(copy.deepcopy(project),{},{},{},False,1.)
            expected=[]
            for number in range(math.ceil(project.duration*fps-1e-7)):
                context.project.playhead=number/fps
                image,_,_=rasterize(context,QRectF(0,0,320,180),(320,180),1.)
                image=image.convertToFormat(QImage.Format_RGBA8888)
                expected.append(np.frombuffer(image.constBits(),np.uint8).reshape(180,320,4)[:,:,:3].copy())
            expected=np.array(expected).astype(float)
        else:
            reference=directory/'cpu.mp4';export(project,str(reference),preset,True,'CPU',export_audio=False)
            expected=decoded(reference)
        check(name+' preserves frame count',len(actual)==math.ceil(project.duration*fps-1e-7) and actual.shape==expected.shape)
        error=float(np.abs(actual-expected).mean());check(name+' preserves visual output',error<5.)
        check(name+' uses expected preparation',bool(job['cpu_islands'])==(name in ('titles','finishing-animation','retime-finishing')))
        if name.startswith('video-'):check(name+' retains hardware decoder textures',status['decoded_gpu']>0 and status['decoded_cpu']==0)
        results.append(dict(name=name,mean_pixel_error=error,diagnostics=status))
    from .transition_diagnostics import export_checks
    results.extend(export_checks(out,check))
    # Exercise the actual transactional export entry point, not just its helper.
    project.timeline=[TimelineItem('cancel','m','video_1',0,300,transform=Transform(x=.5,y=.5))];project.captions=[]
    target=out/'previous-output.mp4';target.write_bytes(b'previous output')
    cancel=threading.Event();timer=threading.Timer(.3,cancel.set);timer.start()
    try:
        try:export(project,str(target),preset,False,'NVIDIA',cancel=cancel,export_audio=False)
        except RuntimeError as error:check('cancel reports cancellation','cancel' in str(error).lower())
        else:check('cancel reports cancellation',False)
    finally:timer.cancel();timer.join()
    check('cancel preserves previous output',target.read_bytes()==b'previous output')
    check('cancel removes pending export directories',not list(out.glob('.kinetic-export-*')))
    report.update(passed=True,cases=results)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0
