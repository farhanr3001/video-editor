"""Opt-in native inspector/graphics and live Windows file-removal checks."""
def run(output):
    import os,sys,json,time,traceback,shutil,ctypes
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QEventLoop,QTimer,QThreadPool,QUrl
    from PySide6.QtGui import QMouseEvent,QImage
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .model import Project,MediaItem,TimelineItem
    from .ui import MainWindow
    from .graphics import GRAPHICS_CATALOG,default_graphic_data
    from .theme_widgets import apply_application_theme
    from .media_source import set_media_source
    from .pool_tools import SourcePreview
    from . import missing_media
    from .process import run as process
    app=QApplication([]); w=MainWindow(); w.autosave_timer.stop(); w.resize(1480,900); w.show()
    report={'frozen':bool(getattr(sys,'frozen',False)),'native':os.name=='nt'}
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def move(widget,point):
        QApplication.sendEvent(widget,QMouseEvent(QEvent.MouseMove,QPointF(point),QPointF(widget.mapToGlobal(point)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
    try:
        fixture=output/'sample.mp4'
        process(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=5','-f','lavfi','-i','sine=frequency=440:duration=5','-c:a','aac','-c:v','libx264','-pix_fmt','yuv420p',str(fixture)],capture_output=True,check=True)
        p=Project(media=[MediaItem('m',str(fixture),'video','Fixture',5,320,180,30,True)],timeline=[TimelineItem('v','m','video_1',0,4)])
        w.set_project(p); w.timeline.select_ids({'v'},'v'); wait(500)
        spin=w.inspector.zoom_x.spin; line=spin.lineEdit()
        for value,key in [('1.234',Qt.Key_Return),('1.456',Qt.Key_Enter)]:
            QTest.mouseDClick(line,Qt.LeftButton); focused=app.focusWidget()
            assert focused in (spin,line),repr(focused)
            QTest.keyClicks(focused,value); QTest.keyClick(app.focusWidget(),key); wait(30)
            assert abs(p.timeline[0].transform.scale-float(value))<.001
            assert not line.hasFocus() and not line.hasSelectedText() and not spin._typing
            QTest.mousePress(line,Qt.LeftButton,pos=QPoint(10,10)); assert spin._drag_start is not None
            # Real captured mouse input on Windows; use the current cursor anchor.
            move(line,QPoint(20,10)); QTest.mouseRelease(line,Qt.LeftButton,pos=QPoint(20,10)); assert spin.value()>float(value)
        report['native_focus_target_enter_and_repeated_drag']=True
        captures=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            for name in GRAPHICS_CATALOG:
                item=TimelineItem('g','','video_1',0,5,role='graphic',graphic_type=name,graphic_data=default_graphic_data(name))
                p=Project(timeline=[item]); p.playhead=.5; w.set_project(p); w.timeline.select_ids({'g'},'g'); wait(30)
                preview=w.preview; rect=preview._visible_items()[0][2]; anchor,corners,sides,handle,_=preview._transform_geometry(item,rect)
                corner=corners[1].toPoint(); dest=(anchor+(corners[1]-anchor)*1.3).toPoint()
                QTest.mousePress(preview,Qt.LeftButton,pos=corner); assert preview.drag_mode=='scale',(name,preview.drag_mode)
                move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest)
                assert item.transform.scale>1 and abs(w.inspector.gtr_scale.spin.value()-item.transform.scale)<.001
                rect=preview._visible_items()[0][2]; anchor,_,_,handle,_=preview._transform_geometry(item,rect)
                dest=(anchor+QPointF(50,0)).toPoint(); QTest.mousePress(preview,Qt.LeftButton,pos=handle.toPoint()); assert preview.drag_mode=='rotate'
                move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest); assert abs(item.transform.rotation-90)<2
                assert abs(w.inspector.gtr_rot.spin.value()-item.transform.rotation)<1
                rect=preview._visible_items()[0][2]; anchor,_,sides,_,_=preview._transform_geometry(item,rect)
                before=item.transform.scale; dest=(anchor+(sides[1]-anchor)*1.2).toPoint()
                QTest.mousePress(preview,Qt.LeftButton,pos=sides[1].toPoint()); assert preview.drag_mode=='scale_x'
                move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest); assert item.transform.scale>before
                assert abs(w.inspector.gtr_scale_y.spin.value()-item.transform.effective_scale_y)<.001
                filename=theme+'-'+name.split('/')[0].strip().lower().replace(' ','_')+'.png'; preview.grab().save(str(output/filename)); captures.append(filename)
            from PySide6.QtWidgets import QScrollArea
            area=w.inspector.gtr_scale.parentWidget()
            while area and not isinstance(area,QScrollArea):area=area.parentWidget()
            if area:area.ensureWidgetVisible(w.inspector.gtr_rot); wait(30)
            w.grab().save(str(output/(theme+'-graphic-inspector.png')))
        report['all_eight_graphics_three_themes_resize_rotate_inspector']=True; report['screenshots']=captures
        removals=[]
        if os.name=='nt':
            from ctypes import wintypes
            class FileOperation(ctypes.Structure):
                _fields_=[('hwnd',wintypes.HWND),('wFunc',wintypes.UINT),('pFrom',wintypes.LPCWSTR),('pTo',wintypes.LPCWSTR),('fFlags',wintypes.WORD),('fAnyOperationsAborted',wintypes.BOOL),('hNameMappings',wintypes.LPVOID),('lpszProgressTitle',wintypes.LPCWSTR)]
            recycle=ctypes.windll.shell32.SHFileOperationW; recycle.argtypes=[ctypes.POINTER(FileOperation)]; recycle.restype=ctypes.c_int
            for playing in (False,True):
                source=output/('playing-recycle.mp4' if playing else 'paused-rename.mp4'); shutil.copyfile(fixture,source)
                media=MediaItem('m',str(source),'video','Disposable removal fixture',5,320,180,30,True)
                p=Project(media=[media],timeline=[TimelineItem('v','m','video_1',0,4),TimelineItem('a','m','audio_1',0,4)])
                w.set_project(p); w.seek(.4); dialog=SourcePreview(w.media_panel,media); dialog.show()
                set_media_source(w.player,QUrl.fromLocalFile(str(source))); w.player.pause()
                if playing:w.transport.play()
                wait(1000); QThreadPool.globalInstance().waitForDone(10000); wait(30)
                assert w.transport.decoders and w.preview.frames,'Actual timeline video/audio did not decode'
                assert dialog.player.sourceDevice() is not None and w.player.sourceDevice() is not None
                if playing:
                    # Only our generated disposable fixture is sent to the Recycle Bin.
                    assert source.parent==output and source.name=='playing-recycle.mp4'
                    operation=FileOperation(); operation.wFunc=3; operation.pFrom=str(source)+'\0\0'; operation.fFlags=0x4|0x10|0x40|0x400
                    result=recycle(ctypes.byref(operation)); assert result==0 and not operation.fAnyOperationsAborted,(result,operation.fAnyOperationsAborted)
                else:
                    moved=source.with_suffix('.renamed.mp4'); source.rename(moved); moved.unlink()
                assert not source.exists()
                deadline=time.monotonic()+7
                while not missing_media.is_missing(media) and time.monotonic()<deadline:wait(50)
                assert missing_media.is_missing(media),'Automatic missing-media monitor did not publish removal'
                wait(100); assert not any(key[0]=='m' for key in w.transport.decoders)
                assert w.player.source().isEmpty() and dialog.player.source().isEmpty()
                w.transport.pause(); dialog.close(); wait(100)
                removals.append({'playing':playing,'timeline_video_audio_source_preview':True,'operation':'recycle' if playing else 'rename_delete','missing_detected':True})
        report['live_media_removals']=removals
        # Decode an actual export and compare resize/rotation extents to identity.
        from .exporter import write_ass
        from PIL import Image
        bounds=[]
        for transformed in (False,True):
            item=TimelineItem('g','','video_1',0,1,role='graphic',graphic_type='Rectangle',graphic_data={'width':140,'height':60,'thickness':8,'color':'#00e5ff','fill_enabled':True,'fill_color':'#00e5ff','fill_opacity':100})
            p=Project(timeline=[item]); p.settings.width=640; p.settings.height=360
            if transformed:item.transform.scale=1.6; item.transform.scale_y=.8; item.transform.rotation=90
            ass=output/('transformed.ass' if transformed else 'identity.ass'); write_ass(p,ass)
            video=ass.with_suffix('.mp4'); frame=ass.with_suffix('.png'); ass_filter=str(ass).replace('\\','/').replace(':','\\:')
            process(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:s=640x360:r=30:d=1','-vf',"ass='"+ass_filter+"'",'-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
            process(['ffmpeg','-v','error','-y','-ss','0.5','-i',str(video),'-frames:v','1',str(frame)],capture_output=True,check=True)
            image=Image.open(frame).convert('RGB'); pixels=image.load(); points=[(x,y) for y in range(image.height) for x in range(image.width) if pixels[x,y][1]>90 and pixels[x,y][2]>90]
            assert points; bounds.append((max(x for x,y in points)-min(x for x,y in points),max(y for x,y in points)-min(y for x,y in points)))
        assert bounds[0][0]>bounds[0][1] and bounds[1][1]>bounds[1][0],bounds
        assert bounds[1][1]>bounds[0][0]*1.4 and bounds[1][0]<bounds[0][1],bounds
        report['decoded_graphic_export_bounds']=bounds; report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); app.sendPostedEvents(None,QEvent.DeferredDelete)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report.get('passed') else 1
