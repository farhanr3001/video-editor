"""Actual native GPU pixels for the creative effect stack; disposable media only."""
def preview_checks(window,out,check,wait):
    import time,copy
    import numpy as np
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage,QColor,QPainter
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Crop
    from .creative_effects import NAMES,default_effect
    from .preview_compositor import SceneContext,render
    image=QImage(320,180,QImage.Format_RGBA8888);image.fill(QColor('#285d80'))
    paint=QPainter(image);paint.fillRect(0,0,160,90,QColor('#ef3030'));paint.fillRect(160,90,160,90,QColor('#20d050'));paint.end()
    path=out/'creative-pattern.png';image.save(str(path))
    item=TimelineItem('creative','creative-photo','video_1',0,4)
    project=Project(settings=ProjectSettings(width=320,height=180,fps=60),media=[MediaItem('creative-photo',str(path),'image','Creative effects',4,320,180)],timeline=[item])
    window.set_project(project);window.preview.set_transform_controls_visible(False)
    def parity(name,at=.17):
        window.project.touch();window.transport.sync(True);window.seek(at)
        gpu=window.preview.gpu;previous=gpu.frames;gpu.signature=None;gpu.schedule();deadline=time.monotonic()+8
        while gpu.frames<=previous and time.monotonic()<deadline:wait(40)
        wait(180)
        frame=window.preview.composition_rect();picture=gpu.view.grabWindow().copy(frame.toRect()).convertToFormat(QImage.Format_RGBA8888)
        check(name+' has a rendered preview frame',not picture.isNull())
        context=SceneContext(copy.deepcopy(window.project),{},{},{},True,1.)
        # Preserve the real fractional canvas geometry before cropping. Replacing
        # it with the rounded screenshot dimensions changes the phase of fine
        # patterns and tests a different layout from the native player.
        reference,_,_=render(context,frame,(window.preview.width(),window.preview.height()),1.)
        reference=reference.copy(frame.toRect()).convertToFormat(QImage.Format_RGBA8888)
        actual=np.frombuffer(picture.constBits(),np.uint8).reshape(picture.height(),picture.width(),4).astype(float)
        expected=np.frombuffer(reference.constBits(),np.uint8).reshape(reference.height(),reference.width(),4).astype(float)
        error=float(np.abs(actual[:,:,:3]-expected[:,:,:3]).mean())
        picture.save(str(out/f'{name}-gpu.png'));reference.save(str(out/f'{name}-reference.png'))
        check(name+f' GPU pixel parity ({error:.2f})',error<5)
        return picture
    for name in NAMES:
        item.effects=[default_effect(name,item)];parity('creative-'+name.replace(' ','-'))
    from .finishing_effects import ANIMATED
    for name in sorted(ANIMATED):
        effect=default_effect(name,item)
        if name=='Scanlines':effect['speed']=1
        item.effects=[effect]
        first=parity('animated-'+name.replace(' ','-')+'-first',.17)
        second=parity('animated-'+name.replace(' ','-')+'-second',.43)
        check(name+' animates without changing the source texture',first!=second)
    item.transform=Transform(.5,.5,.8,rotation=15,flip_horizontal=True,flip_vertical=True)
    item.effects=[default_effect('Lens Distortion',item),default_effect('Vignette',item)];parity('finishing-flipped-rotated')
    item.transform=Transform()
    item.effects=[default_effect('Color Flash',item)];a=parity('flash-bright',0);b=parity('flash-clear',.25)
    check('flash animates an unchanged still-image texture',a!=b)
    item.effects=[default_effect('Duotone',item),dict(name='Gaussian Blur',horizontal=8,vertical=8,blend=65),default_effect('Color Tint',item),default_effect('Invert Colors',item)]
    parity('creative-ordered-blur-stack')
    item.transform=Transform(.5,.5,.7,rotation=20);item.crop=Crop(.1,.1,.8,.8);item.opacity=65
    item.effects=[default_effect('Color Tint',item),default_effect('Posterize',item)];parity('creative-crop-rotation-opacity')
    item.effects[0]['enabled']=False;parity('creative-disable')
    item.effects=[];parity('creative-removed')
    item.effects=[default_effect('Color Flash',item)];window.model_changed();window.timeline.selected_id=item.id;window.timeline.selected_ids={item.id};window.inspector.select(item.id);window.inspector.tabs.setCurrentIndex(2)
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        window.apply_theme(theme,save=False);wait(100)
        window.inspector.grab().save(str(out/f'creative-inspector-{theme}.png'))
        check('creative controls visible in '+theme,window.inspector.creative_panel.isVisible())
    window.apply_theme('default',save=False)
