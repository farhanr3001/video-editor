"""Optional downloads accessible without changing any editing project."""
import threading
from PySide6.QtCore import QThreadPool, QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QProgressBar, QMessageBox,QCheckBox
from . import feature_packs

SPEECH_INFO = ("A larger, more accurate speech model for generating captions. It hears words more reliably than the built-in "
               "base.en, including fast speech, accents and background noise, and can recognise other languages. It runs on this computer; "
               "captions take longer than with base.en (much faster with an NVIDIA GPU).\n\n"
               "To use it: after the download, open Workflow > Settings > Advanced > Speech model and choose large-v3-turbo. "
               "Switch back to base.en there at any time. Already have this model on your computer? Choose "
               "\"Custom model folder\u2026\" in the same place instead of downloading.")


class ComponentEvents(QObject):
    changed = Signal()

_events = None
active_downloads = set()
_jobs={}
_installer_jobs=set()


def cancel_component_downloads():
    for job in tuple(_jobs.values()):job.cancel.set()
    for job in tuple(_installer_jobs):job.cancel.set()


class _ComponentJob(QObject):
    """Own installation completion independently of a disposable popup."""
    progress=Signal(object)
    result=Signal(object)
    error=Signal(str)

    def __init__(self,key,cancel,acceleration=None):
        super().__init__(); self.key=key; self.cancel=cancel; self.worker=None;self.acceleration=acceleration

    def start(self,owner):
        from .ui import Worker
        if self.key=='enhance':
            from .enhance_component import install
            worker=Worker(install,self.progress.emit,self.cancel,acceleration=self.acceleration)
        else:worker=Worker(feature_packs.install,self.key,self.progress.emit,self.cancel)
        self.worker=worker; _jobs[self.key]=self; active_downloads.add(self.key)
        worker.signals.result.connect(self.complete,Qt.QueuedConnection)
        worker.signals.error.connect(self.failed,Qt.QueuedConnection)
        worker.signals.finished.connect(self.retire,Qt.QueuedConnection)
        if owner:owner.start_worker(worker)
        else:QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def complete(self,result):
        events().changed.emit(); self.result.emit(result)

    @Slot(str)
    def failed(self,detail):self.error.emit(detail)

    @Slot()
    def retire(self):
        if _jobs.get(self.key) is self:_jobs.pop(self.key,None); active_downloads.discard(self.key)
        if self.worker:self.worker.signals.deleteLater()
        self.worker=None; self.deleteLater()

def events():
    global _events
    if _events is None:_events = ComponentEvents()
    return _events


class InstallComponentDialog(QDialog):
    def __init__(self, parent, key):
        super().__init__(parent); self.key = key; self.cancel = threading.Event(); self.running = False; self._closed=False; self._job=None
        item = feature_packs.manifest().get(key, {})
        name = item.get('name', {
                                 'vision':'Face / background tools','vocals':'Vocal separation','enhance':'AI Enhance','speech':'Caption model (large-v3-turbo)'}[key])
        self.setWindowTitle('Download ' + name); self.resize(510,260)
        layout = QVBoxLayout(self)
        self.status = QLabel(name + ' is an optional download.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        if item:
            info = f"Download: {item['download_bytes']/1e6:.1f} MB\nInstalled size: {item['installed_bytes']/1e6:.1f} MB"
        else:info = 'Installed size: about ' + size_label(estimated_bytes(key))
        if key=='speech':info='Download and installed size: about '+size_label(estimated_bytes('speech'))+'\n\n'+SPEECH_INFO
        if key=='enhance':info='Download: approximately 350-450 MB\n'+info+'\nLocal GPU restoration with motion-aware stabilization; playback uses cached frames.'
        details = QLabel(info + '\nYour projects, sources and Power Bin are preserved.'); details.setWordWrap(True); layout.addWidget(details)
        self.cuda=None
        if key=='enhance':
            from .enhance_component import default_acceleration,runtime_ready,component_root
            reuse=runtime_ready(component_root())
            self.cuda=QCheckBox('NVIDIA CUDA acceleration (larger download)');self.cuda.setChecked(default_acceleration()=='CUDA');layout.addWidget(self.cuda)
            self.cuda.setVisible(not reuse)
            def update_estimate():
                estimate='Download: approximately 10 MB of lightweight models.\nYour existing GPU runtime will be reused.' if reuse else 'Download: approximately 2.5 GB\nInstalled: approximately 5 GB; allow 12 GB free for setup.' if self.cuda.isChecked() else 'Download: approximately 350-450 MB\nInstalled: approximately 1.6 GB; allow 4 GB free for setup.'
                details.setText(estimate+'\nAll processing is local. Preparation can take time; playback uses cached frames. No download starts until you confirm.')
            self.cuda.toggled.connect(update_estimate);update_estimate()
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.setFormat('%p%'); layout.addWidget(self.progress)
        row = QHBoxLayout(); layout.addLayout(row); row.addStretch()
        self.cancel_button = QPushButton('Cancel'); self.cancel_button.clicked.connect(self.reject); row.addWidget(self.cancel_button)
        self.confirm = QPushButton('Confirm download'); self.confirm.clicked.connect(self.begin); row.addWidget(self.confirm)

    def begin(self):
        if self._closed or self.running:return
        if self.key in active_downloads:
            self.status.setText('This component is already downloading. Wait for it to finish.'); return
        self.running = True; self.confirm.setEnabled(False)
        acceleration=('CUDA' if self.cuda.isChecked() else 'DirectML') if self.cuda else None
        self._job=_ComponentJob(self.key,self.cancel,acceleration)
        self._job.progress.connect(self.update_progress,Qt.QueuedConnection)
        self._job.result.connect(self.complete,Qt.QueuedConnection)
        self._job.error.connect(self.failed,Qt.QueuedConnection)
        owner=self.parentWidget()
        while owner and not hasattr(owner,'start_worker'):owner=owner.parentWidget()
        self.destroyed.connect(self.cancel.set)
        self._job.start(owner)

    @Slot(object)
    def update_progress(self,event):
        if self._closed or self.cancel.is_set():return
        self.progress.setValue(round(event[0])); self.status.setText(event[1])

    @Slot(object)
    def complete(self, result):
        self.running = False
        if not self._closed and not self.cancel.is_set():self.accept()

    @Slot(str)
    def failed(self, error):
        self.running = False
        if self._closed or self.cancel.is_set():return
        self.status.setText(error.splitlines()[-1]); self.confirm.setEnabled(True)

    def reject(self):
        self._closed=True; self.cancel.set(); super().reject()

    def closeEvent(self, event):
        self._closed=True; self.cancel.set(); super().closeEvent(event)


def offer(parent, key):
    if feature_packs.available(key):return True
    dialog = InstallComponentDialog(parent,key); dialog.exec()
    return feature_packs.available(key)


class _InstallerDownloadsJob(QObject):
    """Retain the batch independently of its closable installer popup."""
    progress=Signal(object)
    finished=Signal(int)

    def __init__(self,keys,local_source,cancel):
        super().__init__(); self.keys=tuple(keys); self.local_source=local_source
        self.cancel=cancel; self.worker=None; self.code=1; self.settled=False

    def start(self):
        from .ui import Worker
        self.worker=Worker(self.work); self.worker.cancel_callback=self.cancel.set
        self.worker.signals.result.connect(self.complete,Qt.QueuedConnection)
        self.worker.signals.error.connect(self.failed,Qt.QueuedConnection)
        self.worker.signals.finished.connect(self.retire,Qt.QueuedConnection)
        _installer_jobs.add(self)
        QThreadPool.globalInstance().start(self.worker)

    def work(self):
        from .config import DATA_DIR
        with (DATA_DIR/'component-install.log').open('w',encoding='utf-8') as stream:
            for index,key in enumerate(self.keys):
                if self.cancel.is_set():raise InterruptedError('Component installation cancelled')
                if key not in feature_packs.ROOTS:raise ValueError('Unknown component: '+key)
                def progress(event):
                    stream.write(str(event)+'\n'); stream.flush()
                    self.progress.emit((round((index+event[0]/100)/len(self.keys)*100),event[1]))
                feature_packs.install(key,progress,self.cancel,self.local_source)
            if self.cancel.is_set():raise InterruptedError('Component installation cancelled')
        return 0

    @Slot(object)
    def complete(self,code):
        if not self.cancel.is_set():self.code=code

    @Slot(str)
    def failed(self,error):
        from .config import DATA_DIR
        self.code=1
        try:
            with (DATA_DIR/'component-install.log').open('a',encoding='utf-8') as stream:stream.write('FAILED: '+error)
        except OSError:
            import logging
            logging.exception('Could not write optional-install failure log')

    @Slot()
    def retire(self):
        self.settled=True
        if self.cancel.is_set():self.code=1
        if self.worker:self.worker.signals.deleteLater()
        self.worker=None; _installer_jobs.discard(self)
        self.finished.emit(self.code)


class _InstallerDownloadsDialog(QDialog):
    def __init__(self,cancel):
        super().__init__(); self.cancel=cancel; self._closed=False
        self.setWindowTitle('Installing optional downloads'); self.resize(520,220)
        layout=QVBoxLayout(self)
        self.status=QLabel('Preparing selected optional tools…'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.bar=QProgressBar(); self.bar.setRange(0,100); self.bar.setFormat('%p%'); layout.addWidget(self.bar)
        self.button=QPushButton('Cancel'); layout.addWidget(self.button); self.button.clicked.connect(self.request_cancel)
        self.destroyed.connect(cancel.set)

    @Slot()
    def request_cancel(self):
        self.cancel.set(); self.button.setEnabled(False); self.status.setText('Cancelling…')

    @Slot(object)
    def update_progress(self,event):
        if self._closed or self.cancel.is_set():return
        self.bar.setValue(event[0]); self.status.setText(event[1])

    @Slot(int)
    def job_finished(self,code):
        if self._closed:return
        self._closed=True; super().done(QDialog.Accepted if code==0 else QDialog.Rejected)

    def reject(self):
        self._closed=True; self.cancel.set(); super().reject()

    def closeEvent(self,event):
        self._closed=True; self.cancel.set(); super().closeEvent(event)


def installer_downloads(keys, local_source=None):
    """Keep processing GUI events until our own optional-install batch settles."""
    import sys
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication
    if not keys:return 0
    app=QApplication.instance() or QApplication(sys.argv)
    quit_policy=app.quitOnLastWindowClosed(); app.setQuitOnLastWindowClosed(False)
    cancel=threading.Event(); dialog=_InstallerDownloadsDialog(cancel)
    job=_InstallerDownloadsJob(keys,local_source,cancel); loop=QEventLoop()
    job.progress.connect(dialog.update_progress,Qt.QueuedConnection)
    job.finished.connect(dialog.job_finished,Qt.QueuedConnection)
    job.finished.connect(loop.quit,Qt.QueuedConnection)
    try:
        dialog.show(); job.start()
        if not job.settled:loop.exec()
        return job.code
    finally:
        import shiboken6
        cancel.set()
        if shiboken6.isValid(dialog):dialog.deleteLater()
        loop.deleteLater()
        if job.settled:job.deleteLater()
        else:job.finished.connect(job.deleteLater,Qt.QueuedConnection)
        app.setQuitOnLastWindowClosed(quit_policy)


from .feature_packs import size_label


def estimated_bytes(key):
    """Installed size measured from real installs (Nov 2026); a manifest value wins when present."""
    item = feature_packs.manifest().get(key, {})
    if item.get('installed_bytes'):
        return int(item['installed_bytes'])
    if key == 'enhance':
        from .enhance_component import default_acceleration
        return 4_950_000_000 if default_acceleration() == 'CUDA' else 1_700_000_000
    return {'vision': 354_000_000, 'vocals': 1_167_000_000, 'speech': 1_621_670_079}[key]


CATALOG = (
    ('speech', 'Caption model (large-v3-turbo)', 'captions',
     'More accurate speech recognition for generated captions.'),
    ('vision', 'Face / background tools', 'smile',
     'Background removal and face effects (masks, big eyes, face twist).'),
    ('vocals', 'Vocal separation', 'audio-waveform',
     'Separates voices from music and noise for the Vocal Only effect.'),
    ('enhance', 'AI Enhance', 'sparkles',
     'Local video restoration: denoise, deblur, sharpen and upscale.'),
)

_STYLE = """
QFrame#componentCard { background: @bg_panel; border: 1px solid @border_subtle; border-radius: 8px; }
QLabel#componentHeading { color: @text_main; font-size: 15px; font-weight: 600; background: transparent; }
QLabel#componentIntro, QLabel#componentBlurb, QLabel#componentTotal { color: @text_sub; background: transparent; border: 0; }
QLabel#componentTitle { color: @text_main; font-weight: 600; background: transparent; border: 0; }
QLabel#componentIcon { background: transparent; border: 0; }
QLabel#componentState { color: @text_sub; background: transparent; border: 0; }
QLabel#componentState[installed="true"] { color: @success; }
QPushButton#componentInfo { background: #3d9ae8; color: #ffffff; border: 0; border-radius: 9px; padding: 0;
    min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    font-family: Georgia, "Times New Roman", serif; font-size: 12px; font-weight: 700; font-style: italic; }
QPushButton#componentInfo:hover { background: #63b0f2; }
QPushButton#componentInfo:pressed { background: #2b7fc7; }
"""


class ComponentsDialog(QDialog):
    NAMES = tuple((key, name, 0) for key, name, _icon, _blurb in CATALOG)

    def __init__(self, window):
        super().__init__(window); self.window = window
        from PySide6.QtWidgets import QFrame
        from PySide6.QtCore import QTimer
        from .theme_widgets import set_ui_style, set_ui_icon
        self.setWindowTitle("Optional downloads"); self.setMinimumWidth(680)
        set_ui_style(self, _STYLE)
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 16, 18, 16); layout.setSpacing(8)
        heading = QLabel('Optional downloads'); heading.setObjectName('componentHeading'); layout.addWidget(heading)
        intro = QLabel('Editing and standard captions work without these. Each tool downloads once, runs on this computer and can be removed at any time.')
        intro.setObjectName('componentIntro'); intro.setWordWrap(True); layout.addWidget(intro); layout.addSpacing(4)
        self.rows = {}; self.info_buttons = {}; self.states = {}; self.sizes = {}
        for key, name, icon, blurb in CATALOG:
            card = QFrame(); card.setObjectName('componentCard'); layout.addWidget(card)
            row = QHBoxLayout(card); row.setContentsMargins(12, 10, 12, 10); row.setSpacing(12)
            glyph = QLabel(); glyph.setObjectName('componentIcon'); set_ui_icon(glyph, icon, None, 22)
            glyph.setFixedWidth(26); row.addWidget(glyph, 0, Qt.AlignTop)
            text = QVBoxLayout(); text.setSpacing(2); row.addLayout(text, 1)
            title_row = QHBoxLayout(); title_row.setSpacing(6); text.addLayout(title_row)
            title = QLabel(name); title.setObjectName('componentTitle'); title_row.addWidget(title)
            if key == 'speech':
                info = QPushButton('i'); info.setObjectName('componentInfo'); info.setCursor(Qt.PointingHandCursor)
                info.setToolTip(SPEECH_INFO); info.setAccessibleName('About the large-v3-turbo caption model')
                info.clicked.connect(lambda checked=False: QMessageBox.information(self, 'Caption model: large-v3-turbo', SPEECH_INFO))
                title_row.addWidget(info, 0, Qt.AlignVCenter); self.info_buttons[key] = info
            title_row.addStretch()
            description = QLabel(blurb); description.setObjectName('componentBlurb'); description.setWordWrap(True); text.addWidget(description)
            state = QLabel(); state.setObjectName('componentState'); text.addWidget(state); self.states[key] = state
            button = QPushButton("Download"); button.setObjectName('componentDownload'); button.setMinimumWidth(96)
            button.clicked.connect(lambda checked=False, k=key: self.download(k)); row.addWidget(button, 0, Qt.AlignVCenter)
            remove = QPushButton("Uninstall"); remove.setObjectName('componentUninstall'); remove.setMinimumWidth(88)
            remove.clicked.connect(lambda checked=False, k=key, n=name: self.uninstall(k, n)); row.addWidget(remove, 0, Qt.AlignVCenter)
            self.rows[key] = (button, remove)
        layout.addStretch(1)
        footer = QHBoxLayout(); layout.addLayout(footer)
        self.total = QLabel(); self.total.setObjectName('componentTotal'); footer.addWidget(self.total, 1)
        close = QPushButton("Close"); close.setMinimumWidth(96); close.clicked.connect(self.accept); footer.addWidget(close)
        self._measure_timer = QTimer(self); self._measure_timer.setInterval(150); self._measure_timer.timeout.connect(self._apply_sizes)
        self._measured = {}; self._measuring = None
        self.refresh_rows()

    def _root(self, key):
        if key == 'speech':
            from .caption_runtime import app_model_root
            return app_model_root()
        return feature_packs.component_root(key)

    def _measure(self, keys):
        """Folder sizes off the UI thread; a 5 GB runtime has tens of thousands of files."""
        from .cache_manager import tree_size
        result = {}
        for key in keys:
            try:result[key] = tree_size(self._root(key))
            except (OSError, ValueError, KeyError):pass
        self._measuring = result

    def _apply_sizes(self):
        if self._measuring is None:return
        self._measure_timer.stop(); self._measured.update(self._measuring); self._measuring = None
        self.refresh_rows(measure=False)

    def refresh_rows(self, measure=True):
        ready_keys = []
        for key, (button, remove) in self.rows.items():
            ready = feature_packs.available(key, getattr(self.window, 'settings', {}))
            busy = key in active_downloads
            button.setText("Installed" if ready else "Downloading\u2026" if busy else "Download")
            button.setEnabled(not ready and not busy)
            remove.setEnabled(ready and not busy)
            state = self.states[key]
            if ready:
                ready_keys.append(key)
                size = self._measured.get(key)
                state.setText('\u2713 Installed' + (f' \u00b7 {size_label(size)} on disk' if size else ''))
            else:
                self._measured.pop(key, None)
                state.setText(f'About {size_label(estimated_bytes(key))}')
            state.setProperty('installed', ready); state.style().unpolish(state); state.style().polish(state)
        used = sum(self._measured.get(k, 0) for k in ready_keys)
        self.total.setText(f'{len(ready_keys)} of {len(self.rows)} installed' + (f' \u00b7 {size_label(used)} used' if used else ''))
        pending = [k for k in ready_keys if k not in self._measured]
        if measure and pending and self._measuring is None and not self._measure_timer.isActive():
            import threading
            threading.Thread(target=self._measure, args=(pending,), daemon=True).start()
            self._measure_timer.start()

    def download(self, key):
        offer(self, key); self.refresh_rows()

    def uninstall(self, key, name):
        from .cache_manager import removal_blocked
        if removal_blocked(self.window):
            QMessageBox.information(self, 'Optional tool busy', 'Stop playback, transfers and rendering, and wait for background jobs to finish before uninstalling tools.')
            return
        extra = ''
        if key == 'speech' and str(getattr(self.window, 'settings', {}).get('whisper_model', '')) == 'large-v3-turbo':
            extra = ' Captions are currently set to use this model; it will download again the next time you generate captions unless you switch back to base.en in Settings > Advanced.'
        if QMessageBox.question(self, f'Uninstall {name}?', f'Remove {name} from this computer? Your projects, sources and Power Bin are not deleted, and you can download it again later.' + extra) != QMessageBox.Yes:
            return
        try:
            feature_packs.remove(key)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, 'Uninstall not completed', str(error))
        self._measured.pop(key, None)
        events().changed.emit(); self.refresh_rows()

    def done(self, result):
        if hasattr(self, '_cancel'): self._cancel.set()
        self._measure_timer.stop()
        super().done(result)
