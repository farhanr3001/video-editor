"""Optional read-only native responsiveness check on the owner's 4x project."""
def run(window,path,out,settle):
    import time,hashlib,statistics
    from pathlib import Path
    from unittest.mock import patch
    from PySide6.QtCore import Qt,QTimer,QPoint,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .model import Project
    from .widgets import PreviewCanvas
    from . import enhance
    path=Path(path);before=hashlib.sha256(path.read_bytes()).hexdigest();fixture=window.project
    project=Project.load(path);item=next(i for i in project.timeline if enhance.active(i));original=PreviewCanvas.paintEvent
    from contextlib import ExitStack
    from platformdirs import user_cache_dir
    from . import config
    normal_cache=Path(user_cache_dir('KineticCut'));private_cache=config.CACHE_DIR
    # Read-only hardlinks let the isolated composition subprocess see the same
    # prepared pixels without copying gigabytes or touching owner cache data.
    import os,shutil
    records=[]
    with patch.object(config,'CACHE_DIR',normal_cache):
        for index,_ in enhance.active(item):records.extend(enhance.ranges(project,project.media_by_id(item.media_id),item,index))
    assert records,'Owner cache missing'
    for record in records:
        source=Path(record['root']);target=private_cache/'ai-enhance'/record['key']
        if target.exists():continue
        target.mkdir(parents=True)
        for folder in ('frames','original','alpha'):
            (target/folder).mkdir()
            if (source/folder).exists():
                for file in (source/folder).glob('*.png'):os.link(file,target/folder/file.name)
        shutil.copy2(source/'info.json',target/'info.json')
    enhance._range_indexes.clear()
    stack=ExitStack();stack.enter_context(patch.object(window.preview_quality,'request'))
    paints=[];beats=[];presentations=[];pan_fallbacks=[];audit=[]
    from .preview_compositor import CompositionCache
    request=CompositionCache.request
    def audited(cache,rect):
        result=request(cache,rect)
        if cache.canvas is window.preview and window.preview.pan_origin is not None:
            if result:
                key=next((key for key,image in cache.images._images.items() if image.cacheKey()==result[0].cacheKey()),None)
                assert key is not None,'Unidentified displayed composition'
                presentations.append(key[1])
                import ast
                inputs={}
                for source,identity in key[2]:
                    try:
                        stamp=ast.literal_eval(identity) if isinstance(identity,str) else None
                        if isinstance(stamp,tuple) and len(stamp)==3 and isinstance(stamp[1],int):inputs[source]=stamp[1]
                    except (SyntaxError,ValueError,TypeError):pass
                audit.append(dict(requested=round(project.playhead*project.settings.fps),displayed=key[1],source_pts=inputs))
            else:pan_fallbacks.append(project.playhead)
        return result
    stack.enter_context(patch.object(CompositionCache,'request',audited))
    def measured():
        if not window.transport.playing:return
        started=time.perf_counter();window.preview.repaint();paints.append((time.perf_counter()-started)*1000)
    paint_timer=QTimer();paint_timer.setInterval(16);paint_timer.timeout.connect(measured)
    timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:beats.append(time.perf_counter()))
    try:
        window.set_project(project);window.timeline.select_ids({item.id},item.id);window.select_item(item.id);window.preview.transform_controls_visible=True
        window.preview_quality.setCurrentIndex(0)
        assert enhance.range_at(project,project.media_by_id(item.media_id),item,enhance.active(item)[0][0],5.3),'Owner cache missing'
        window.seek(5.3);settle(1200)
        timer.start();paint_timer.start();window.transport.play();settle(3000);paint_timer.stop();window.transport.pause();timer.stop();settle(350)
        assert paints and project.playhead>7,'Actual playback did not advance'
        from .preview_compositor import CompositionCache
        window.preview.transform_controls_visible=False
        settle(350)
        before_compositions=window.preview.composition_cache.completed
        window.transport.play();settle(3000);window.transport.pause();settle(350)
        compositions=window.preview.composition_cache.completed-before_compositions
        if compositions<=5:
            import json
            (out/'composition-stall.json').write_text(json.dumps(dict(completed=compositions,playing=window.transport.playing,playhead=project.playhead,closed=window.preview.composition_cache.closed,pending=repr(window.preview.composition_cache.pending),workers=len(window._workers)),indent=2))
        assert compositions>5,'Composited playback did not advance'
        window.preview.transform_controls_visible=True;settle(250)
        window.seek(12.0);settle(500);window.transport.play();settle(500)
        pan_start=project.playhead
        canvas=window.preview;center=canvas.rect().center();QTest.mousePress(canvas,Qt.MiddleButton,pos=center);samples=[]
        for n in range(120):
            step=n%40 if (n//40)%2==0 else 40-n%40
            pos=QPointF(center)+QPointF(step*3.125,(n%40)*1.75);event=QMouseEvent(QEvent.MouseMove,pos,pos,Qt.NoButton,Qt.MiddleButton,Qt.NoModifier)
            started=time.perf_counter();QApplication.sendEvent(canvas,event);canvas.repaint();samples.append((time.perf_counter()-started)*1000);settle(20)
        QTest.mouseRelease(canvas,Qt.MiddleButton,pos=center+QPoint(122,68));window.transport.pause();assert project.playhead>pan_start;canvas.grab().save(str(out/'owner-4x-preview.png'))
        assert presentations and all(b>=a for a,b in zip(presentations,presentations[1:])), 'Displayed composition jumped backwards'
        assert all(b['source_pts'][k]>=a['source_pts'][k] for a,b in zip(audit,audit[1:]) for k in a['source_pts'].keys()&b['source_pts'].keys()),'Displayed source frame jumped backwards'
        assert len(set(presentations))>5,'Panning froze the displayed footage'
        assert not pan_fallbacks,'Panning invalidated prepared composition and used GUI fallback'
        for at in (1.2,9.1,3.4):window.seek(at);settle(300)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
        intervals=[(b-a)*1000 for a,b in zip(beats,beats[1:])]
        return dict(passed=True,project_unchanged=True,playing_paints=len(paints),paint_median_ms=statistics.median(paints),paint_p95_ms=sorted(paints)[int((len(paints)-1)*.95)],paint_max_ms=max(paints),heartbeat_p95_ms=sorted(intervals)[int((len(intervals)-1)*.95)],pan_while_playing=True,pan_presentations=len(presentations),pan_distinct_frames=len(set(presentations)),pan_backwards_frames=sum(b<a for a,b in zip(presentations,presentations[1:])),pan_source_samples=sum(bool(a['source_pts']) for a in audit),pan_backwards_source_frames=sum(b['source_pts'][k]<a['source_pts'][k] for a,b in zip(audit,audit[1:]) for k in a['source_pts'].keys()&b['source_pts'].keys()),pan_gui_fallbacks=len(pan_fallbacks),pan_events=len(samples),pan_median_ms=statistics.median(samples),pan_max_ms=max(samples),manual_seeks=3,transform_controls_during_pan=False,compositions_without_transform_boxes=compositions)
    finally:
        import json
        (out/'pan-frame-audit.json').write_text(json.dumps(dict(frames=audit,gui_fallbacks=pan_fallbacks),indent=2))
        paint_timer.stop();timer.stop();window.transport.pause();stack.close();window.set_project(fixture)
