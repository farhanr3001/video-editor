"""Packaged media-pool smoke check using only generated media and an isolated home."""
def run(output):
    import os,sys,json,traceback,wave
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop,QTimer,QThreadPool,QMimeData
    from PySide6.QtGui import QImage,QColor,QFont
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem,Caption
    from .pool_tools import set_view,SourcePreview
    from .theme import STYLESHEET
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET); app.setFont(QFont('Segoe UI',9))
    w=MainWindow(); w.resize(1600,900); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False))}
    def settle(ms=100):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        image=QImage(640,360,QImage.Format_RGB32); image.fill(QColor('#487e95')); image.save(str(output/'sample.png'))
        t=np.arange(48000*3)/48000; data=(np.sin(t*2*np.pi*440)*(.1+.89*np.sin(t*3)**2)*32760).astype('<i2')
        with wave.open(str(output/'sample.wav'),'wb') as f:f.setnchannels(1); f.setsampwidth(2); f.setframerate(48000); f.writeframes(data.tobytes())
        media=[MediaItem('i',str(output/'sample.png'),'image','Apartment reference',5,640,360),MediaItem('a',str(output/'sample.wav'),'audio','Doorbell sound effect',3,has_audio=True)]
        w.set_project(Project(media=media,timeline=[TimelineItem('v','i','video_1',0,5)],captions=[Caption('c',0,5,'Hello there')]))
        panel=w.media_panel; w.workspace_split.setSizes([690,910]); settle(1500); QThreadPool.globalInstance().waitForDone(15000); settle()
        assert panel.audio_thumbnails.cache; report['audio_waveform']=True
        set_view(panel,False,False); settle(); w.grab().save(str(output/'gallery.png'))
        set_view(panel,True); settle()
        rects=[panel.grid.visualItemRect(panel.grid.item(n)) for n in range(panel.grid.count())]
        assert rects[0].bottom()<rects[1].top() and panel.column_header.height()==26
        from .config import load_settings
        assert load_settings()['media_pool_list_view']; report['list_layout_and_preference']=True
        w.grab().save(str(output/'list.png'))
        for folder in ('Master/Source','Master/Destination'):panel.power.add_folder(folder)
        for m in media:panel.power.add(m,'Master/Source')
        panel.folder='Master/Source'; mime=QMimeData(); mime.setData('application/x-kinetic-media-id',b'i')
        mime.setData('application/x-kinetic-power-source',b'{"folder":"Master/Source","ids":["i","a"]}')
        assert panel.move_drop(mime,'Master/Destination') and panel.folder=='Master/Source'
        assert all(e['folder']=='Master/Destination' for e in panel.power.data['media']); report['batch_move_without_navigation']=True
        w.seek(1.25); w.split_at('v',2.5); assert w.project.playhead==1.25
        w.seek(3.5); w.undo(); assert w.project.playhead==3.5
        w.split_caption_at('c',2.5); assert w.project.playhead==3.5; report['cuts_and_undo_preserve_playhead']=True
        before=w.project.to_dict(); w.monitor_control.set_level(35); w.monitor_control.toggle()
        assert w.transport.monitor_gain==0 and w.project.to_dict()==before
        w.resize(1100,750); settle(); assert w.monitor_control.slider.isHidden(); w.monitor_control.popup(); settle()
        w.monitor_control._menu.grab().save(str(output/'monitor.png')); w.monitor_control._menu.close(); report['monitor_only_and_compact']=True
        preview=SourcePreview(panel,media[1]); preview.show(); preview.player.play(); settle(700)
        assert preview.player.duration()>0; preview.close(); assert preview.player.source().isEmpty(); report['audio_preview_and_cleanup']=True
        report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
