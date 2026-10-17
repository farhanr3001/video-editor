"""Opt-in native, isolated editing-assistance and decoded audio/export checks."""
def run(output,speech_fixture):
    import os,sys,json,time,threading,traceback,copy,shutil,hashlib,wave
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    import numpy as np,av
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QEventLoop,QTimer
    from .ui import MainWindow
    from .model import Project,TimelineItem,MediaItem,Caption,Transform,Crop
    from .media import probe
    from .process import run as run_process
    from .motion_presets import build
    from .assistant_client import Client
    from .caption_fonts import load_fonts
    from .assistant_api import revision
    from .motion_editor import MotionEditor
    app=QApplication([]); app.setStyle('Fusion'); app.setQuitOnLastWindowClosed(False); app.setProperty('kineticTestDiscardUnsaved',True); load_fonts()
    w=MainWindow(); w.resize(1480,920); w.show(); w.autosave_timer.stop()
    report=dict(frozen=bool(getattr(sys,'frozen',False)),passed=False,themes=[]); done=threading.Event()
    def settle(ms=80):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def until(predicate,seconds=90):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return
            settle(40)
        raise AssertionError('Native condition did not settle within deadline.')
    source=Path(speech_fixture).resolve(); source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        speech=out/'speech.wav'; shutil.copy2(source,speech)
        video=out/'moving.mp4'
        run_process([w.settings['ffmpeg'],'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=3','-c:v','libx264','-g','15','-bf','0','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
        sound=out/'cash-fixture.wav'; samples=np.zeros(8000,dtype=np.float32); samples[1600:4400]=.3*np.sin(2*np.pi*1000*np.arange(2800)/8000)
        with wave.open(str(sound),'wb') as stream:stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000); stream.writeframes((samples*32767).astype('<i2').tobytes())
        vm=probe(video,w.settings['ffprobe'],w.settings['ffmpeg']); vm.id='video'
        sm=probe(speech,w.settings['ffprobe'],w.settings['ffmpeg']); sm.id='speech'
        graphic=TimelineItem('graphic','','video_3',0,3,role='graphic',graphic_type='Motion Composition',graphic_data=build('Chapter Title',(320,568),3),transform=Transform(.5,.5))
        caption=Caption('caption',.4,1.2,'WATCH PRICE'); caption.style.size=15
        p=Project(name='Editing assistance fixture',media=[vm,sm],video_tracks=['video_1','video_2','video_3'],timeline=[TimelineItem('background','video','video_1',0,3),TimelineItem('webcam','video','video_2',0,3,crop=Crop(0,0,.5,.35),transform=Transform(.5,.2,.4),role='facecam'),graphic],captions=[caption])
        p.settings.width=320; p.settings.height=568; p.settings.fps=30; p.subtitle_style.size=15
        from .icons import resource_path
        model=resource_path('assets','caption-models','base.en')
        if not (model/'model.bin').is_file():model=Path.cwd()/'dist/KineticCut/_internal/assets/caption-models/base.en'
        assert (model/'model.bin').is_file(),'Native diagnostic requires the existing bundled speech model; never download a test model.'
        w.settings['whisper_model']=str(model.resolve()); os.environ['HF_HUB_OFFLINE']='1'; w.set_project(p)
        connection=w.assistant_connection; connection.config['port']=0; connection.start(); assert connection.server
        def client_work():
            try:
                client=Client(connection.server.url,connection.config['token']); client.initialize('Editing assistance native verification')
                names={t['name'] for t in client.request('tools/list')['tools']}
                assert {'search_transcripts','anchor_captions_to_video','add_motion_sound_cue','create_edit_contact_sheet'}<=names
                def wait_job(job):
                    end=time.monotonic()+100
                    while time.monotonic()<end:
                        latest=next(j for j in client.value('get_jobs')['tasks'] if j['id']==job['id'])
                        if latest['state'] not in ('Running','Cancelling'):
                            assert latest['state']=='Complete',latest; return latest
                        time.sleep(.06)
                    raise AssertionError('MCP job deadline')
                before=client.value('get_state',section='summary')['revision']
                transcript=wait_job(client.value('generate_source_transcripts',media_ids=['speech']))
                search=client.value('search_transcripts',media_ids=['speech']); assert search['total']>0,search
                term=search['matches'][0]['text'].split()[0]
                assert client.value('search_transcripts',query=term.lower(),media_ids=['speech'])['total']>0
                assert client.value('get_state',section='summary')['revision']==before
                report['transcript']=dict(backend=transcript['result'][0]['backend'],timing=transcript['result'][0]['timing'],passages=search['total'],text=[r['text'] for r in search['matches']])
                placed=client.value('anchor_captions_to_video',revision=before,track='video_2',caption_ids=['caption'],margin=4)
                assert placed['placements']; client.value('history',direction='undo'); assert client.value('get_state',section='summary')['revision']==before
                client.value('history',direction='redo'); state=client.value('get_state',section='summary')
                sound_job=wait_job(client.value('add_motion_sound_cue',revision=state['revision'],item_id='graphic',path=str(sound),time=.6,gain_db=-3))
                assert .15<sound_job['cue']['in_point']<.21,sound_job
                report['sound_cue']=sound_job['cue']
                review=client.value('review_edit'); assert not any(i['kind']=='missing_media' for i in review['issues'])
                report['structural']=review
                sheet=wait_job(client.value('create_edit_contact_sheet',timestamps=[.2,.8,1.5,2.8],width=320)); report['contact_sheet']=sheet['result']
                returned=client.call('get_edit_contact_sheet',job_id=sheet['id']); assert returned['content'][1]['type']=='image'
                queued=client.value('queue_export',path=str(out/'verified.mp4'),encoder='CPU',start=True)
                end=time.monotonic()+100
                while time.monotonic()<end:
                    renders=client.value('get_jobs')['renders']
                    if renders and renders[-1]['state'] not in ('Queued','Rendering'):break
                    time.sleep(.1)
                assert renders[-1]['state']=='Complete',renders
                with av.open(str(out/'verified.mp4')) as movie:
                    video_frames=list(movie.decode(video=0)); assert len(video_frames)==90
                result=run_process([w.settings['ffmpeg'],'-hide_banner','-loglevel','error','-i',str(out/'verified.mp4'),'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'],check=True,capture_output=True)
                values=np.frombuffer(result.stdout,dtype='<f4')
                def rms(a,b):return float(np.sqrt(np.mean(values[round(a*8000):round(b*8000)]**2)))
                report['export_audio']=dict(before=rms(.1,.4),cue=rms(.68,.85),after=rms(1.2,1.5),frames=len(video_frames))
                assert report['export_audio']['before']<.003 and report['export_audio']['cue']>.05 and report['export_audio']['after']<.003,report['export_audio']
                report['mcp_verified']=True
            except Exception:report['error']=traceback.format_exc()
            finally:done.set()
        thread=threading.Thread(target=client_work,daemon=True); thread.start(); until(done.is_set,240); thread.join(1)
        if report.get('error'):raise AssertionError(report['error'])
        from .workspace import set_page
        set_page(w,0)
        panel=w.inspector.transcript_panel; w.inspector.tabs.setCurrentIndex(1); w.inspector.audio_subtabs.setCurrentWidget(panel)
        panel.query.setText(''); until(lambda:panel.rows.count()>0)
        panel.activate(panel.rows.item(0)); source_dialog=panel._source_dialog; settle(180)
        assert source_dialog.parentWidget() is w.inspector
        source_dialog.reject(); settle(); report['unplaced_source_preview']=True
        # UI search seeks an existing retimed cut without dirtying the project.
        from . import transcripts
        data=transcripts.load(w.project.media_by_id('speech'),w.settings); row=data['segments'][0]
        clip=TimelineItem('speech-cut','speech','audio_1',1,.5,row['start'],speed=1)
        w.project.timeline.append(clip); w.model_changed(); w.timeline.select_ids({'speech-cut'},'speech-cut'); w.inspector.select('speech-cut')
        for index in range(3):
            w.inspector.audio_subtabs.setCurrentIndex(index)
            w.inspector.select('background'); w.inspector.select(''); w.inspector.select('speech-cut')
            assert w.inspector.tabs.currentIndex()==1 and w.inspector.audio_subtabs.currentIndex()==index
        report['audio_subtab_memory']=True
        panel=w.inspector.transcript_panel; w.inspector.tabs.setCurrentIndex(1); w.inspector.audio_subtabs.setCurrentWidget(panel)
        assert panel.isVisibleTo(w)
        panel.query.setText(row['text'].split()[0]); until(lambda:panel.rows.count()>0)
        before=revision(w.project); panel.activate(panel.rows.item(0)); assert abs(w.project.playhead-1)<.001
        assert revision(w.project)==before
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False); settle(160); w.inspector.tabs.setCurrentIndex(1)
            assert w.grab().save(str(out/f'transcript-{theme}.png'))
            d=MotionEditor(w,w.project.item_by_id('graphic')); d.show(); d.property_tabs.setCurrentWidget(d.sound_panel); d.seek(.7); settle(140)
            d.timeline.verticalScrollBar().setValue(d.timeline.verticalScrollBar().maximum())
            assert d.sound_panel.rows.count()==1; assert any(channel=='sound' for _,channel in d.timeline.rows)
            d.sound_panel.preview_sound(); settle(140); assert d.sound_panel.audition.players
            until(lambda:bool(d.sound_panel.wave.peaks),10)
            assert d.grab().save(str(out/f'sound-{theme}.png'))
            from .sound_picker import SoundBinPicker
            from dataclasses import asdict
            cue_media=probe(sound,w.settings['ffprobe'],w.settings['ffmpeg']); cue_media.id='cash'
            old_power=w.media_panel.power.data
            w.media_panel.power.data={'folders':['Master','Master/Sounds','Master/Sounds/Cash'],'media':[{'folder':'Master/Sounds/Cash','media':asdict(cue_media)}]}
            before=copy.deepcopy(w.project.to_dict())
            picker=SoundBinPicker(w,'power',d); picker.show(); settle()
            try:
                folder=picker.tree.topLevelItem(1).child(0).child(0).child(0); picker.tree.setCurrentItem(folder)
                assert picker.rows.topLevelItemCount()==1 and not picker.confirm.isEnabled()
                picker.rows.setCurrentItem(picker.rows.topLevelItem(0)); assert picker.confirm.isEnabled()
                until(lambda:not picker.thumbnail_rows,15)
                assert picker.rows.topLevelItem(0).text(1)=='0:01'
                for width,height in ((660,420),(440,300)):
                    picker.resize(width,height); settle(); assert picker.grab().save(str(out/f'sound-picker-{theme}-{width}.png'))
                    assert picker.confirm.isVisible() and picker.confirm.mapTo(picker,picker.confirm.rect().bottomRight()).y()<picker.height()
                picker.confirm.click(); assert picker.path==str(sound)
                from PySide6.QtWidgets import QDialog
                after=w.project.to_dict()
                # Autosave may update only the document's modification timestamp
                # while an asynchronous waveform is being generated.
                before.pop('modified_at',None); after.pop('modified_at',None)
                assert picker.result()==QDialog.Accepted and after==before,[key for key in after if after[key]!=before.get(key)]
                count=d.sound_panel.rows.count(); d.sound_panel.add_path(picker.path)
                until(lambda:d.sound_panel.pending is None,15); assert d.sound_panel.rows.count()==count+1
                d.local_history(-1); assert d.sound_panel.rows.count()==count
            finally:picker.close(); picker.deleteLater(); w.media_panel.power.data=old_power
            d.reject(); settle()
            report['themes'].append(theme)
        w.project.timeline=[i for i in w.project.timeline if i.id!='speech-cut']; w.seek(.65); w.transport.play(); settle(180)
        assert any(key[0].startswith('__cue_source__') for key in w.transport.decoders)
        w.transport.pause(); report['main_cue_decoder']=True
        portable=copy.deepcopy(w.project); portable.portable_media=True; portable.save(out/'portable.kcut'); restored=Project.load(out/'portable.kcut')
        assert restored.item_by_id('graphic').graphic_data['scene']['sound_cues'][0]['source']==str(sound)
        if os.environ.get('KINETIC_ARROW_PROJECT'):report['arrow_export']=verify_arrow_exports(out,w.settings,os.environ['KINETIC_ARROW_PROJECT'])
        report.update(passed=True,source_fixture_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==source_sha)
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        w.close(); settle(120)
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1


def verify_arrow_exports(out,settings,project_path):
    import copy,hashlib
    from pathlib import Path
    import av,numpy as np
    from .model import Project
    from .native_animation import frame,required
    from .exporter import export,ExportPreset
    path=Path(project_path); original=hashlib.sha256(path.read_bytes()).hexdigest(); source=Project.load(path)
    arrows=[item for item in source.timeline if item.role=='graphic' and 'arrow' in item.graphic_type.lower()]
    assert arrows,'Expected owner arrow fixtures'; results=[]
    # Distinct source transforms/styles only; repeated cuts need no duplicate render.
    seen=set()
    for item in arrows:
        signature=repr((item.transform,item.graphic_data))
        if signature in seen:continue
        seen.add(signature); project=Project(); project.settings=copy.deepcopy(source.settings)
        arrow=copy.deepcopy(item); arrow.start=0; arrow.duration=2/project.settings.fps; arrow.fade_in=arrow.fade_out=0
        project.video_tracks=[arrow.track]; project.timeline=[arrow]; assert required(arrow)
        expected=frame(project,arrow,0); expected.save(str(out/'arrow-preview.png'))
        pixels=np.frombuffer(expected.constBits(),np.uint8).reshape(expected.height(),expected.bytesPerLine()//4,4)[:,:expected.width()]
        expected_mask=(pixels[:,:,0]>150)&(pixels[:,:,1]<80)&(pixels[:,:,3]>180)
        target=out/f'arrow-export-{len(results)}.mp4'
        export(project,str(target),ExportPreset('Arrow parity','h264',16,128,'test'),False,'CPU',ffmpeg=settings['ffmpeg'],export_audio=False)
        with av.open(str(target)) as video:actual=np.ascontiguousarray(next(video.decode(video=0)).to_ndarray(format='rgb24'))
        from PySide6.QtGui import QImage
        QImage(actual.data,actual.shape[1],actual.shape[0],actual.strides[0],QImage.Format_RGB888).copy().save(str(out/'arrow-export.png'))
        mask=(actual[:,:,0]>150)&(actual[:,:,1]<80)&(actual[:,:,2]<80)
        intersection=np.count_nonzero(mask&expected_mask); union=np.count_nonzero(mask|expected_mask); iou=intersection/max(1,union)
        ey,ex=np.where(expected_mask); ay,ax=np.where(mask)
        assert len(ax)>0 and iou>.94,(iou,len(ex),len(ax))
        bounds=lambda x,y:[int(x.min()),int(y.min()),int(x.max()),int(y.max())]
        expected_bounds=bounds(ex,ey); actual_bounds=bounds(ax,ay)
        assert max(abs(a-b) for a,b in zip(expected_bounds,actual_bounds))<=2,(expected_bounds,actual_bounds)
        results.append(dict(item=item.id,mask_iou=iou,preview_bounds=expected_bounds,export_bounds=actual_bounds))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    return dict(passed=True,project_unchanged=True,source_sha=original,arrows=len(arrows),distinct_exports=results)
