"""Native preset/editor interactions and decoded preset export parity."""
def check(w,out,report,settle):
    import copy,json
    import numpy as np,av
    from PySide6.QtCore import Qt,QPoint,QThreadPool
    from PySide6.QtGui import QImage,QPainter,QColor
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem,Transform
    from .motion_presets import PRESETS,build
    from .motion_editor import MotionEditor
    from .motion import curve
    from .native_animation import frame
    from .exporter import export,PRESETS as EXPORT_PRESETS
    asset=out/'preset-product.png'; pic=QImage(80,220,QImage.Format_RGBA8888); pic.fill(Qt.transparent)
    paint=QPainter(pic); paint.fillRect(25,0,30,220,QColor('#ffe600')); paint.fillRect(5,65,70,80,QColor('#d4d9df')); paint.end(); pic.save(str(asset))
    data=build('Price Range Card',(480,854),1.4,{'image':str(asset)})
    item=TimelineItem('preset','','video_1',0,1.4,role='graphic',graphic_type='Motion Composition',graphic_data=data,transform=Transform(.5,.5))
    project=Project(timeline=[item]); project.settings.width=480; project.settings.height=854; project.settings.fps=30; w.set_project(project); settle(300)
    report['workbench']={'themes':[],'gestures':[],'presets':list(PRESETS),'export_errors':[]}
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        w.apply_theme(theme,save=False); d=MotionEditor(w,item); d.show(); d.seek(.6); d.select_node('heading'); settle()
        for size in ((1180,820),(950,720)):
            d.resize(*size); settle(); name=f'workbench-{theme}-{size[0]}.png'; assert d.grab().save(str(out/name)); report['workbench']['themes'].append(name)
            assert d.width()<=size[0]+2 and d.timeline.viewport().height()>=100
        original=copy.deepcopy(d.scene); preview=d.preview; entry=preview.geometry()[0]['heading']; point=preview.from_scene(entry['hit'].boundingRect().center()).toPoint()
        QTest.mousePress(preview,Qt.LeftButton,Qt.NoModifier,point); QTest.mouseMove(preview,point+QPoint(18,7)); QTest.mouseRelease(preview,Qt.LeftButton,Qt.NoModifier,point+QPoint(18,7))
        assert d.node_id=='heading' and d.scene!=original; d.local_history(-1); assert d.scene==original
        point=preview.handles(preview.geometry()[0]['heading'])['2'].toPoint(); old=curve(d.node(),'font_size',d.position)
        QTest.mousePress(preview,Qt.LeftButton,Qt.NoModifier,point); QTest.mouseMove(preview,point+QPoint(15,15)); QTest.mouseRelease(preview,Qt.LeftButton,Qt.NoModifier,point+QPoint(15,15)); assert curve(d.node(),'font_size',d.position)>old
        d.local_history(-1); assert d.scene==original
        d.select_node('card'); d.channel.setCurrentText('scale'); t=d.timeline; row=t.rows.index(('card','scale')); key=d.node()['keyframes']['scale'][-1]
        point=QPoint(round(t.x(key['time'])),round(t.row_rect(row).center().y()))
        QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.NoModifier,point); QTest.mouseMove(t.viewport(),point+QPoint(30,0)); QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.NoModifier,point+QPoint(30,0)); assert d.scene!=original
        value=d.node()['keyframes']['scale'][-1]['time']; assert abs(value*30-round(value*30))<1e-5
        d.local_history(-1); assert d.scene==original
        d.navigate('start'); d.navigate('key',1); assert abs(d.position-.35)<.001; d.navigate('frame',-1); assert abs(d.position-(.35-1/30))<.001
        d.zoom.setValue(3); assert t.horizontalScrollBar().maximum()>0
        d.preview_zoom.setValue(2); settle(); assert d.preview.view_scale==2
        assert d.grab().save(str(out/f'workbench-zoom-{theme}.png')); d.preview.fit(); assert d.preview.view_scale==1
        report['workbench']['gestures'].append(dict(theme=theme,move=True,resize=True,key_drag=True,undo=True,frame_step=True,zoom=True))
        from .motion_qol_diagnostics import check as check_qol
        report['workbench']['gestures'][-1]['qol']=check_qol(d,w,settle)
        d.reject(); settle(); assert item.graphic_data==data
    w.apply_theme('default',save=False)
    from .motion_qol_diagnostics import graphics_drop
    report['workbench']['graphic_drops']=graphics_drop(w)
    for name in PRESETS:
        for canvas in ((480,854),(854,480)):
            recipe=build(name,canvas,2,{'image':str(asset)} if name in ('Product Price Card','Price Range Card','Product Showcase') else {})
            from .motion import draw
            image=draw(recipe['scene'],1,(canvas[0],canvas[1]),30); assert image.save(str(out/(name.replace(' ','-')+f'-{canvas[0]}.png')))
    target=out/'preset-range.mp4'; export(project,str(target),EXPORT_PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
    with av.open(str(target)) as movie:frames=list(movie.decode(video=0))
    assert len(frames)==42
    for n in (6,15,30,39):
        image=frame(project,item,n/30).convertToFormat(QImage.Format_RGBA8888)
        pixels=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].astype(float)
        expected=pixels[:,:,:3]*pixels[:,:,3:]/255; error=float(np.abs(frames[n].to_ndarray(format='rgb24')-expected).mean())
        assert error<4,error; report['workbench']['export_errors'].append(error)
    api=w.assistant_connection.api; state=api.call_get_motion_composition(item.id,.6); assert state['parameters']['value']==375000
    result=api.call_configure_motion_preset(state['revision'],item.id,{'value':300000}); assert result['undoable']; w.undo(); assert w.project.timeline[0].graphic_data==data
    state=api.call_get_motion_composition(item.id,.6)
    result=api.call_edit_motion_composition(state['revision'],item.id,[dict(op='set_key',id='heading',channel='opacity',time=.5,value=70)])
    assert result['undoable']; w.undo(); assert w.project.timeline[0].graphic_data==data
    image=api.call_get_motion_preview(item.id,.6); assert image['_mcp_content'][1]['mimeType']=='image/png'
    project.portable_media=True; saved=out/'portable-preset.kcut'; project.save(saved)
    loaded=Project.load(saved); assert loaded.timeline[0].graphic_data['parameters']['image']==str(asset)
    # Representative cached software draw comparison, not an assertion about
    # whole-editor fps. Both use the same viewer size and source-time samples;
    # the recipes intentionally differ in layout and styling.
    from pathlib import Path
    import hashlib,time,statistics
    owner=Path('assets_xqc_wealth_series_20261014/xQc - Watch Collection.kcut')
    if owner.is_file():
        original_hash=hashlib.sha256(owner.read_bytes()).hexdigest(); legacy=Project.load(owner)
        candidates=[i for i in legacy.timeline if i.role=='graphic' and len(i.graphic_data.get('scene',{}).get('nodes',[]))>40]
        if candidates:
            old=max(candidates,key=lambda i:len(i.graphic_data['scene']['nodes'])); source=next((n.get('source','') for n in old.graphic_data['scene']['nodes'] if n['kind']=='image'),'')
            new=build('Price Range Card',old.graphic_data['scene']['canvas'],4,{'image':source})['scene']
            timings={}
            for label,scene in (('hand_built',old.graphic_data['scene']),('preset',new)):
                for n in range(3):draw(scene,.2+n/120,(360,640),30)
                samples=[]
                for n in range(30):
                    started=time.perf_counter(); draw(scene,.2+n/120,(360,640),30); samples.append((time.perf_counter()-started)*1000)
                timings[label]=dict(layers=len(scene['nodes']),mean_ms=statistics.mean(samples),median_ms=statistics.median(samples))
            assert hashlib.sha256(owner.read_bytes()).hexdigest()==original_hash
            report['workbench']['representative_draw_comparison']=timings
    from .motion_qol_diagnostics import fades
    report['workbench']['fades']=fades(w,out,settle)
    report['workbench'].update(mcp=True,portable=True,passed=True)
