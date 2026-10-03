"""Packaged waveform/zoom check, optionally using a sample of a real recording."""
def run(output,source=None):
    import os,json,time,traceback,sys
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(output/'home')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase,QWheelEvent
    from PySide6.QtCore import QPoint,Qt
    from .process import run as process
    from .model import Project,MediaItem,TimelineItem,Caption
    from .timeline import TimelineWidget
    from .waveforms import waveform
    app=QApplication([])
    for name in ('segoeui.ttf','arial.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    t=TimelineWidget(); t.resize(1180,360); t.show(); report={'frozen':bool(getattr(sys,'frozen',False))}
    try:
        audio=output/'sample.wav'
        input_args=['-i',str(source)] if source else ['-f','lavfi','-i','aevalsrc=0.5*sin(2*PI*440*t)*sin(2*PI*1.7*t)^8:s=24000:d=20']
        process(['ffmpeg','-v','error','-y',*input_args,'-t','20','-vn','-ac','2','-ar','24000','-c:a','pcm_s16le',str(audio)],capture_output=True,check=True)
        started=time.monotonic(); data=waveform(str(audio)); report['decode_seconds']=time.monotonic()-started
        report['peak_bins']=len(data); report['peak_memory_bytes']=sum(level.nbytes for level in data.levels)
        assert len(data)>1000,'Detail was still capped by clip length'
        duration=len(data)/1000; media=MediaItem('audio',str(audio),'audio',Path(source).name if source else 'Waveform detail',duration)
        p=Project(media=[media],timeline=[TimelineItem('audio_clip','audio','audio_1',0,duration)])
        p.captions=[Caption('cap',1,2,'Track height test')]; p.playhead=0
        t.set_project(p); t.set_waveform(media.id,data); t.set_zoom(950/duration); app.processEvents()
        t.viewport().grab().save(str(output/'timeline.png'))
        r=t.item_rect(p.timeline[0]).adjusted(-2,-2,2,2).toRect(); t.viewport().grab().copy(r).save(str(output/'waveform.png'))
        started=time.monotonic()
        for _ in range(20):t.viewport().grab()
        report['mean_paint_ms']=(time.monotonic()-started)/20*1000
        heights={name:t._track_height(name+'_1') for name in ('video','audio','subtitle')}
        pos=t._sections()['audio'].center(); event=QWheelEvent(pos,pos,QPoint(),QPoint(0,120),Qt.NoButton,Qt.ShiftModifier,Qt.NoScrollPhase,False)
        QApplication.sendEvent(t.viewport(),event)
        assert t._track_height('audio_1')==heights['audio']+8
        assert all(t._track_height(name+'_1')==heights[name] for name in ('video','subtitle'))
        report['section_zoom_isolated']=True; report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:t.close(); (output/'report.json').write_text(json.dumps(report,indent=2)); app.processEvents()
    return 0 if report.get('passed') else 1
