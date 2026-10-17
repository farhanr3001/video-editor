"""Transactional sound-cue authoring and independent dialog audition."""
import copy
import threading
from pathlib import Path
from PySide6.QtCore import Qt,QUrl,QTimer
from PySide6.QtGui import QPainter,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QListWidget,QListWidgetItem,QPushButton,QLabel,QComboBox,QFileDialog,QCheckBox,QMenu,QDialog
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .controls import SafeDoubleSpinBox
from .media_source import set_media_source
from .motion_audio import at,validate
from .model import uid


def inspect_sound(path,settings,cancel):
    import numpy as np
    from .media import probe
    from .process import run_cancellable
    media=probe(path,settings.get('ffprobe','ffprobe'),settings.get('ffmpeg','ffmpeg'),timeout=30)
    if not media.has_audio or not .01<media.duration<=60:raise ValueError('Choose a sound containing audio, up to 60 seconds long.')
    output=run_cancellable([settings.get('ffmpeg','ffmpeg'),'-hide_banner','-loglevel','error','-i',path,'-vn','-t','60','-ac','1','-ar','8000','-f','f32le','pipe:1'],cancel_check=cancel.is_set,check=True,capture_output=True)
    samples=np.frombuffer(output.stdout,dtype='<f4'); active=np.flatnonzero(np.abs(samples)>.0032)
    if not len(active):raise ValueError('This sound is effectively silent; choose an audible sound cue.')
    start=max(0,active[0]/8000-.03); end=min(media.duration,(active[-1]+1)/8000+.05)
    peaks=[float(np.max(np.abs(block))) if len(block) else 0 for block in np.array_split(samples,240)]
    return dict(source=str(Path(path).resolve()),source_duration=media.duration,in_point=float(start),duration=max(.01,float(end-start)),peaks=peaks)


class CueWave(QWidget):
    def __init__(self,parent):super().__init__(parent); self.peaks=[]; self.cue={}; self.setFixedHeight(48); self.setToolTip('Full source waveform. Vertical markers show the audible cue range.')
    def paintEvent(self,event):
        from .theme_widgets import ui_color
        painter=QPainter(self); painter.fillRect(self.rect(),ui_color('bg_panel')); painter.setPen(QPen(ui_color('accent'),1))
        for n,peak in enumerate(self.peaks):
            x=round(n*self.width()/max(1,len(self.peaks))); h=max(1,round(peak*20)); painter.drawLine(x,24-h,x,24+h)
        if self.cue:
            duration=max(.01,self.cue.get('source_duration',1)); a=self.cue.get('in_point',0)/duration*self.width(); b=(self.cue.get('in_point',0)+self.cue.get('duration',0))/duration*self.width()
            color=ui_color('bg_main'); color.setAlpha(180); painter.fillRect(0,0,round(a),self.height(),color); painter.fillRect(round(b),0,max(0,self.width()-round(b)),self.height(),color)
            painter.setPen(QPen(ui_color('text_main'),1)); painter.drawLine(round(a),0,round(a),self.height()); painter.drawLine(round(b),0,round(b),self.height())


class CuePlayback:
    def __init__(self,parent):self.parent=parent; self.players={}; self.signature=None
    def close(self):
        for player,output in self.players.values():player.stop(); set_media_source(player,QUrl()); player.deleteLater(); output.deleteLater()
        self.players={}; self.signature=None
    def sync(self,scene,position,playing,speed=1):
        cues=scene.get('sound_cues',[]); signature=repr(cues)
        if signature!=self.signature:self.close(); self.signature=signature
        needed=set()
        for cue in cues:
            stamp=at(cue,scene)
            if not playing or not cue.get('enabled',True) or stamp is None or not stamp<=position<stamp+cue['duration']:continue
            identifier=cue['id']; needed.add(identifier)
            desired=round((cue['in_point']+position-stamp)*1000)
            if identifier not in self.players:
                player=QMediaPlayer(self.parent); output=QAudioOutput(self.parent); player.setAudioOutput(output)
                player.setProperty('cue_target',desired)
                def loaded(state,p=player):
                    if state==QMediaPlayer.LoadedMedia and p.property('cue_active'):
                        p.setPosition(p.property('cue_target')); p.play()
                player.mediaStatusChanged.connect(loaded)
                self.players[identifier]=(player,output); set_media_source(player,QUrl.fromLocalFile(cue['source']))
            player,output=self.players[identifier]; was_active=bool(player.property('cue_active')); player.setProperty('cue_active',True); player.setProperty('cue_target',desired)
            output.setVolume(min(1,10**(cue['gain_db']/20))); player.setPlaybackRate(speed)
            if not was_active or abs(player.position()-desired)>180:player.setPosition(desired)
            if player.mediaStatus() not in (QMediaPlayer.LoadingMedia,QMediaPlayer.NoMedia) and player.playbackState()!=QMediaPlayer.PlayingState:player.play()
        for identifier,(player,_) in self.players.items():
            if identifier not in needed:player.setProperty('cue_active',False); player.pause()


class SoundCuePanel(QWidget):
    def __init__(self,editor):
        super().__init__(editor); self.editor=editor; self.updating=False; self.closed=False; self.pending=None
        self.playback=CuePlayback(editor); self.audition=CuePlayback(editor); self.waves={}; self.wave_pending={}
        root=QVBoxLayout(self); root.setContentsMargins(8,8,8,8)
        note=QLabel('Sound cues move and trim with this composition. Times are composition source seconds. Leading/trailing silence is trimmed on import; adjust Source in to change it.',self); note.setWordWrap(True); root.addWidget(note)
        self.rows=QListWidget(self); root.addWidget(self.rows)
        buttons=QHBoxLayout(); self.add=QPushButton('Add sound…',self); self.remove=QPushButton('Remove',self); self.listen=QPushButton('Audition',self)
        for button in (self.add,self.remove,self.listen):buttons.addWidget(button)
        root.addLayout(buttons); self.wave=CueWave(self); root.addWidget(self.wave)
        self.status=QLabel(self); self.status.setWordWrap(True); root.addWidget(self.status)
        form=QFormLayout(); root.addLayout(form); self.enabled=QCheckBox('Enabled',self); form.addRow(self.enabled)
        self.event=QComboBox(self); self.event.addItems(('At time','Selected layer starts','Selected layer ends','Selected keyframe')); form.addRow('Sync to',self.event)
        self.binding=QLabel(self); self.binding.setWordWrap(True); form.addRow(self.binding)
        self.spins={}
        for name,label,low,high in [('time','Cue time',0,100000),('in_point','Source in',0,60),('duration','Duration',.01,60),('gain_db','Gain (dB)',-60,0)]:
            spin=SafeDoubleSpinBox(self); spin.setRange(low,high); spin.setDecimals(3); spin.setSingleStep(.01 if name!='gain_db' else 1); form.addRow(label,spin); self.spins[name]=spin
            spin.valueChanged.connect(lambda value,key=name:self.change(key,value))
            spin.scrubStarted.connect(self.editor.begin_edit); spin.scrubFinished.connect(self.editor.end_edit)
        self.enabled.toggled.connect(lambda value:self.change('enabled',value)); self.event.currentIndexChanged.connect(self.bind)
        menu=QMenu(self.add)
        menu.addAction('Media Bin…',lambda:self.choose_bin('project'))
        menu.addAction('Power Bin…',lambda:self.choose_bin('power'))
        menu.addSeparator(); menu.addAction('Local file…',self.choose)
        self.add.setMenu(menu)
        self.remove.clicked.connect(self.delete); self.listen.clicked.connect(self.preview_sound); self.rows.currentRowChanged.connect(self.selected)
        self.audition_timer=QTimer(self); self.audition_timer.setInterval(30); self.audition_timer.timeout.connect(self.audition_tick)
        root.addStretch(); self.refresh()

    def cue(self):
        key=self.rows.currentItem().data(Qt.UserRole) if self.rows.currentItem() else None
        return next((c for c in self.editor.scene.get('sound_cues',[]) if c['id']==key),None)
    def refresh(self):
        if hasattr(self.editor,'timeline'):self.editor.timeline.refresh()
        key=self.cue(); key=key['id'] if key else None; self.updating=True; self.rows.clear()
        for cue in self.editor.scene.get('sound_cues',[]):
            stamp=at(cue,self.editor.scene); label=f"{stamp:.3f}s" if stamp is not None else 'Missing event'
            row=QListWidgetItem(label+' · '+Path(cue['source']).name,self.rows); row.setData(Qt.UserRole,cue['id'])
            if cue['id']==key:self.rows.setCurrentItem(row)
        self.updating=False
        if self.rows.currentRow()<0 and self.rows.count():self.rows.setCurrentRow(0)
        self.selected()
    def selected(self,*_):
        if self.updating:return
        cue=self.cue(); self.updating=True
        self.wave.cue=cue or {}; self.wave.peaks=self.waves.get((cue or {}).get('id'),[]); self.wave.update()
        if cue and cue['id'] not in self.waves:self.load_wave(cue)
        for key,spin in self.spins.items():spin.setEnabled(bool(cue)); spin.setValue((cue or {}).get(key,0 if key!='duration' else 1))
        self.enabled.setEnabled(bool(cue)); self.enabled.setChecked((cue or {}).get('enabled',True))
        self.event.setEnabled(bool(cue)); self.event.setCurrentIndex(('time','layer_start','layer_end','keyframe').index((cue or {}).get('event','time')))
        self.binding.setText((cue or {}).get('node_id','Independent cue time')+(' · '+cue.get('channel','') if cue and cue.get('event')=='keyframe' else ''))
        self.spins['time'].setEnabled(bool(cue and cue.get('event','time')=='time'))
        self.remove.setEnabled(bool(cue)); self.listen.setEnabled(bool(cue)); self.updating=False
    def load_wave(self,cue):
        if self.closed or cue['id'] in self.wave_pending or not Path(cue['source']).is_file():return
        from .ui import Worker
        cancel=threading.Event(); key=cue['id']; self.wave_pending[key]=cancel; settings=copy.deepcopy(self.editor.owner.settings); path=cue['source']
        worker=Worker(lambda:inspect_sound(path,settings,cancel)); worker.cancel_callback=cancel.set; worker.maintenance=True
        def ready(result):
            if self.closed or cancel.is_set():return
            self.waves[key]=result['peaks']
            if self.cue() and self.cue()['id']==key:self.wave.peaks=result['peaks']; self.wave.update()
        def finished():self.wave_pending.pop(key,None)
        worker.signals.result.connect(ready); worker.signals.finished.connect(finished); self.editor.owner.start_worker(worker)
    def change(self,key,value):
        if self.updating or not self.cue():return
        cues=copy.deepcopy(self.editor.scene.get('sound_cues',[])); target=next(c for c in cues if c['id']==self.cue()['id']); target[key]=value
        try:cues=validate(cues)
        except ValueError as error:self.status.setText(str(error)); return
        owned=self.editor._edit_before is None
        if owned:self.editor.begin_edit()
        self.editor.scene['sound_cues']=cues
        if owned:self.editor.end_edit()
        self.playback.close(); self.refresh()
    def bind(self,index):
        if self.updating or not self.cue():return
        cue=self.cue(); event=('time','layer_start','layer_end','keyframe')[index]; node=self.editor.node(); key=self.editor.selected_key()
        if event!='time' and (not node or event=='keyframe' and not key):self.status.setText('Select the target layer/keyframe first.'); self.selected(); return
        if event=='layer_end' and 'end' not in node:self.status.setText('Set an explicit End time on the selected layer first.'); self.selected(); return
        self.editor.begin_edit(); cue['event']=event
        if event!='time':cue['node_id']=node['id']
        if event=='keyframe':cue.update(channel=self.editor.channel.currentText(),key_time=key['time'])
        self.editor.end_edit(); self.refresh()
    def delete(self):
        if not self.cue():return
        key=self.cue()['id']; self.editor.begin_edit(); self.editor.scene['sound_cues']=[c for c in self.editor.scene['sound_cues'] if c['id']!=key]; self.editor.end_edit(); self.playback.close(); self.refresh()
    def choose(self):
        path,_=QFileDialog.getOpenFileName(self,'Add composition sound','','Audio (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus)')
        if path:self.add_path(path)
    def choose_bin(self,initial):
        from .sound_picker import SoundBinPicker
        dialog=SoundBinPicker(self.editor.owner,initial,self)
        try:
            if dialog.exec()==QDialog.Accepted:self.add_path(dialog.path)
        finally:dialog.deleteLater()
    def add_path(self,path):
        if self.pending:return
        if len(self.editor.scene.get('sound_cues',[]))>=32:self.status.setText('Maximum 32 cues per composition.'); return
        from .ui import Worker
        cancel=threading.Event(); self.pending=cancel; self.add.setEnabled(False); self.status.setText('Reading audible sound region…')
        settings=copy.deepcopy(self.editor.owner.settings); position=self.editor.position
        worker=Worker(lambda:inspect_sound(path,settings,cancel)); worker.cancel_callback=cancel.set
        def ready(result):
            if self.closed or cancel.is_set():return
            peaks=result.pop('peaks'); cue=dict(id=uid(),time=position,gain_db=0,enabled=True,event='time',**result)
            self.editor.begin_edit(); self.editor.scene.setdefault('sound_cues',[]).append(cue); self.editor.end_edit()
            self.waves[cue['id']]=peaks; self.refresh(); self.rows.setCurrentRow(self.rows.count()-1)
            self.status.setText(f"Audible source region: {cue['in_point']:.3f}s–{cue['in_point']+cue['duration']:.3f}s")
        def failed(error):
            if not self.closed:self.status.setText(str(error)[-800:])
        def finished():
            self.pending=None
            if not self.closed:self.add.setEnabled(True)
        worker.signals.result.connect(ready); worker.signals.error.connect(failed); worker.signals.finished.connect(finished); self.editor.owner.start_worker(worker)
    def preview_sound(self):
        import time
        cue=copy.deepcopy(self.cue())
        if not cue:return
        self.editor.pause(); cue.update(time=0,event='time'); self.audition_scene={'sound_cues':[cue]}; self.audition_started=time.monotonic(); self.audition_timer.start(); self.audition_tick()
    def audition_tick(self):
        import time
        position=time.monotonic()-self.audition_started
        if position>=self.audition_scene['sound_cues'][0]['duration']:self.audition_timer.stop(); self.audition.close(); return
        self.audition.sync(self.audition_scene,position,True)
    def close_audio(self):
        self.closed=True
        if self.pending:self.pending.set()
        for cancel in self.wave_pending.values():cancel.set()
        self.audition_timer.stop(); self.audition.close(); self.playback.close()
