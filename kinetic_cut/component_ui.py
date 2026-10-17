"""Optional downloads accessible without changing any editing project."""
import threading
from PySide6.QtCore import QThreadPool, QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QProgressBar, QMessageBox,QCheckBox
from . import feature_packs

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
                                 'vision':'Face / background tools','vocals':'Vocal separation','enhance':'AI Enhance'}[key])
        self.setWindowTitle('Download ' + name); self.resize(510,260)
        layout = QVBoxLayout(self)
        self.status = QLabel(name + ' is an optional download.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        if item:
            info = f"Download: {item['download_bytes']/1e6:.1f} MB\nInstalled size: {item['installed_bytes']/1e6:.1f} MB"
        else:info = 'Installed size: approximately ' + ('350 MB' if key == 'vision' else '1.6 GB' if key=='enhance' else '1.2 GB')
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


class ComponentsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window); self.window = window
        self.setWindowTitle("Optional downloads"); self.resize(570, 310)
        layout = QVBoxLayout(self)
        title = QLabel("Editing and caption generation are included. Add optional tools when you need them.")
        title.setWordWrap(True); layout.addWidget(title)
        metadata = feature_packs.manifest()
        for key, name, estimate in (("vision", "Face / background tools", 350000000), ("vocals", "Vocal separation", 1200000000), ('enhance','AI Enhance',1600000000)):
            if key=='enhance':
                from .enhance_component import default_acceleration
                if default_acceleration()=='CUDA':estimate=5000000000
            row = QHBoxLayout(); layout.addLayout(row)
            size = metadata.get(key, {}).get("installed_bytes", estimate)
            label = QLabel(f"{name} · +{size / 1e6:.1f} MB" + (" estimated" if key not in metadata else ""))
            label.setWordWrap(True); row.addWidget(label, 1)
            button = QPushButton("Installed" if feature_packs.available(key, window.settings) else "Download")
            button.setEnabled(not feature_packs.available(key, window.settings))
            button.clicked.connect(lambda checked=False, k=key, b=button: self.download(k, b)); row.addWidget(button)
        close = QPushButton("Close"); close.clicked.connect(self.accept); layout.addWidget(close)

    def download(self, key, button):
        if offer(self,key):button.setEnabled(False); button.setText('Installed')

    def done(self, result):
        if hasattr(self, '_cancel'): self._cancel.set()
        super().done(result)
