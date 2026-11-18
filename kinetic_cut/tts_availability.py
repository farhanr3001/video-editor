"""One cancellable free-service check when a speech dialog is opened."""
import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from threading import Event
from PySide6.QtCore import QObject,Signal,Slot,QEvent,Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton
from PySide6.QtMultimedia import QMediaPlayer
from .dialog_jobs import RetainedThread
from .theme_widgets import set_ui_style
from .tts import VOICES,_await_cancellable,_retry_speech_request,_ensure_windows_asyncio,check_speech_client,speech_connection_error


@dataclass(frozen=True)
class Availability:
    available:bool
    message:str='Voices ready'
    voices:frozenset|None=None


def backend_voice(voice):
    return 'en-US-AndrewNeural' if voice.startswith('adam') else voice


async def _probe():
    import edge_tts
    check_speech_client()
    catalog=await edge_tts.list_voices()
    ids=frozenset(v['ShortName'] for v in catalog)
    candidates=[backend_voice(v) for _,v in VOICES if backend_voice(v) in ids]
    if not candidates:return Availability(False,'These voices are no longer listed. Check for a Kinetic Cut update.',ids)
    # Voice listing alone can succeed while synthesis handshakes are rejected.
    # Probe a tiny fixed phrase, never the user's text; discard audio silently.
    async def request():
        com=edge_tts.Communicate('Hello.',candidates[0],connect_timeout=4,receive_timeout=6)
        async with aclosing(com.stream()) as stream:
            async for chunk in stream:
                if chunk['type']=='audio' and chunk.get('data'):return Availability(True,voices=ids)
        raise edge_tts.exceptions.NoAudioReceived('Empty voice availability response')
    return await _retry_speech_request(request)


def probe_service(cancel_check=None):
    try:
        _ensure_windows_asyncio()
        return asyncio.run(_await_cancellable(asyncio.wait_for(_probe(),12),cancel_check))
    except InterruptedError:raise
    except Exception as error:return Availability(False,str(speech_connection_error(error)))


class CheckWorker(QObject):
    result=Signal(object,object)
    settled=Signal()
    def __init__(self):super().__init__();self._cancel=Event()
    def cancel(self):self._cancel.set()
    @Slot()
    def run(self):
        try:
            result=probe_service(self._cancel.is_set)
            if not self._cancel.is_set():self.result.emit(result,self._cancel)
        except InterruptedError:pass
        except Exception as error:
            if not self._cancel.is_set():
                self.result.emit(Availability(False,str(speech_connection_error(error))),self._cancel)
        finally:self.settled.emit()


class VoiceAvailability(QObject):
    def __init__(self,dialog,form):
        super().__init__(dialog);self.dialog=dialog;self.started=False;self.closed=False
        self.checking=False;self.result=None;self.job=None;self.token=None
        self.names={v:n for n,v in VOICES}
        self.panel=QWidget();row=QHBoxLayout(self.panel);row.setContentsMargins(0,0,0,0)
        self.label=QLabel('');self.label.setWordWrap(True)
        set_ui_style(self.label,'color: @text_sub; font-size: 11px;')
        self.retry=QPushButton('Retry');self.retry.setToolTip('Check voice availability again')
        self.retry.clicked.connect(self.start);self.retry.hide()
        row.addWidget(self.label,1);row.addWidget(self.retry)
        form.addRow(self.panel)
        self.offline=QPushButton('Download offline voice…');self.offline.clicked.connect(self.download_offline);form.addRow(self.offline)
        from .component_ui import events
        events().changed.connect(self.refresh)
        dialog.voice_combo.currentIndexChanged.connect(self.refresh)
        dialog.installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and not self.started:self.start()
        return False
    @Slot()
    def start(self):
        if self.closed or self.checking or self.busy():return
        self.started=True;self.checking=True;self.label.setText('Checking voice service…');self.refresh()
        worker=CheckWorker();self.token=worker._cancel
        self.dialog.destroyed.connect(worker._cancel.set)
        self.job=RetainedThread(worker);worker.result.connect(self.received,Qt.QueuedConnection);self.job.start()
    @Slot(object,object)
    def received(self,result,token):
        if self.closed or token is not self.token:return
        self.job=None;self.checking=False;self.result=result;self.refresh()
    def busy(self):
        return self.dialog._is_generating or self.dialog._preview_worker is not None
    def allowed(self):
        if self.closed:return False
        from .offline_speech import VOICE,ready
        if self.dialog.voice_combo.currentData()==VOICE:return ready()
        if not self.started:return True  # Unshown programmatic fixture; show always starts a check.
        if self.closed or self.checking or not self.result or not self.result.available:return False
        return self.result.voices is None or backend_voice(self.dialog.voice_combo.currentData() or '') in self.result.voices
    def refresh(self,*_):
        if self.closed:return
        combo=self.dialog.voice_combo
        from .offline_speech import VOICE,ready
        offline_ready=ready();selected_offline=combo.currentData()==VOICE
        missing=False
        for i in range(combo.count()):
            voice=combo.itemData(i);name=self.names.get(voice,combo.itemText(i).split(' — ')[0])
            available=self.result is None or (self.result.available and (self.result.voices is None or backend_voice(voice) in self.result.voices))
            if voice==VOICE:
                combo.setItemText(i,'Offline English · Female'+('' if offline_ready else ' (download)'));combo.model().item(i).setEnabled(True);continue
            combo.setItemText(i,name+(' — Temporarily unavailable' if not available else ''))
            combo.model().item(i).setEnabled(available)
            missing|=not available
        if not self.checking and self.result:
            message=self.result.message
            if self.result.available:
                if not self.allowed():message='This voice is temporarily unavailable. Choose another voice or retry.'
                elif missing:message='Some voices are temporarily unavailable.'
            self.label.setText(message)
        self.retry.setVisible(bool(self.result and (missing or not self.result.available)))
        self.retry.setEnabled(not self.checking and not self.busy())
        self.offline.setVisible(not offline_ready)
        self.offline.setEnabled(not self.busy())
        if selected_offline:self.label.setText('Offline voice ready. Your text stays on this computer.' if offline_ready else 'Download the optional English voice to use narration without an internet connection.')
        self.dialog.generate_btn.setEnabled(self.allowed() and not self.dialog._is_generating)
        playing=self.dialog._preview_player.playbackState()==QMediaPlayer.PlayingState
        self.dialog.preview_btn.setEnabled((self.allowed() or playing) and not self.busy())
    def download_offline(self):
        from .component_ui import offer
        offer(self.dialog,'offline-speech');self.refresh()
    def failure(self,message):
        if 'voice service' in message or 'voice component is out of date' in message:
            self.started=True;self.result=Availability(False,message);self.refresh()
    def close(self):
        self.closed=True
        if self.job:self.job.cancel()
        self.token=None
