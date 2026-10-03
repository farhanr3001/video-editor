"""Optional downloads accessible without changing any editing project."""
import threading
from PySide6.QtCore import QThreadPool, QObject, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QProgressBar, QMessageBox
from . import feature_packs

class ComponentEvents(QObject):
    changed = Signal()

_events = None
active_downloads = set()

def events():
    global _events
    if _events is None:_events = ComponentEvents()
    return _events


class InstallComponentDialog(QDialog):
    def __init__(self, parent, key):
        super().__init__(parent); self.key = key; self.cancel = threading.Event(); self.running = False
        item = feature_packs.manifest().get(key, {})
        name = item.get('name', {'android':'Android mirroring','iphone':'iPhone mirroring',
                                 'vision':'Face / background tools','vocals':'Vocal separation'}[key])
        self.setWindowTitle('Download ' + name); self.resize(510,260)
        layout = QVBoxLayout(self)
        self.status = QLabel(name + ' is an optional download.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        if item:
            info = f"Download: {item['download_bytes']/1e6:.1f} MB\nInstalled size: {item['installed_bytes']/1e6:.1f} MB"
        else:info = 'Installed size: approximately ' + ('350 MB' if key == 'vision' else '1.2 GB' if key == 'vocals' else '27 MB' if key == 'android' else '267 MB')
        details = QLabel(info + '\nYour projects, sources and Power Bin are preserved.'); details.setWordWrap(True); layout.addWidget(details)
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.setFormat('%p%'); layout.addWidget(self.progress)
        row = QHBoxLayout(); layout.addLayout(row); row.addStretch()
        self.cancel_button = QPushButton('Cancel'); self.cancel_button.clicked.connect(self.reject); row.addWidget(self.cancel_button)
        self.confirm = QPushButton('Confirm download'); self.confirm.clicked.connect(self.begin); row.addWidget(self.confirm)

    def begin(self):
        from .ui import Worker
        if self.running:return
        self.running = True; self.confirm.setEnabled(False)
        active_downloads.add(self.key)
        worker = Worker(lambda: feature_packs.install(self.key, worker.signals.progress.emit, self.cancel))
        worker.signals.progress.connect(lambda event: (self.progress.setValue(round(event[0])), self.status.setText(event[1])))
        worker.signals.result.connect(self.complete); worker.signals.error.connect(self.failed)
        self._worker = worker; QThreadPool.globalInstance().start(worker)

    def complete(self, result):
        active_downloads.discard(self.key)
        self.running = False; events().changed.emit(); self.accept()

    def failed(self, error):
        active_downloads.discard(self.key)
        self.running = False
        if self.cancel.is_set():return
        self.status.setText(error.splitlines()[-1]); self.confirm.setEnabled(True)

    def reject(self):
        self.cancel.set(); super().reject()

    def closeEvent(self, event):
        self.cancel.set(); super().closeEvent(event)


def offer(parent, key):
    if feature_packs.available(key):return True
    dialog = InstallComponentDialog(parent,key); dialog.exec()
    return feature_packs.available(key)


def installer_downloads(keys, local_source=None):
    """Installer-confirmed selections still have visible progress and cancellation."""
    import sys
    from PySide6.QtWidgets import QApplication
    from .config import DATA_DIR
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog(); dialog.setWindowTitle('Installing optional downloads'); dialog.resize(520,220)
    layout = QVBoxLayout(dialog); status = QLabel('Preparing selected optional tools…'); status.setWordWrap(True); layout.addWidget(status)
    bar = QProgressBar(); bar.setRange(0,100); bar.setFormat('%p%'); layout.addWidget(bar)
    cancel = threading.Event(); button = QPushButton('Cancel'); layout.addWidget(button)
    button.clicked.connect(lambda:(cancel.set(), button.setEnabled(False),status.setText('Cancelling…')))
    dialog.rejected.connect(cancel.set)
    result = {'code':1}
    from .ui import Worker
    def work():
        log = DATA_DIR/'component-install.log'
        with log.open('w',encoding='utf-8') as stream:
            for index,key in enumerate(keys):
                if key not in feature_packs.ROOTS:raise ValueError('Unknown component: '+key)
                def progress(event):
                    stream.write(str(event)+'\n');stream.flush()
                    worker.signals.progress.emit((round((index+event[0]/100)/len(keys)*100),event[1]))
                feature_packs.install(key,progress,cancel,local_source)
        return 0
    worker = Worker(work)
    worker.signals.progress.connect(lambda event:(bar.setValue(event[0]),status.setText(event[1])))
    def done(code):result['code']=code;dialog.accept()
    def failed(error):
        with (DATA_DIR/'component-install.log').open('a',encoding='utf-8') as stream:stream.write('FAILED: '+error)
        dialog.reject()
    worker.signals.result.connect(done);worker.signals.error.connect(failed)
    QThreadPool.globalInstance().start(worker);dialog.exec()
    cancel.set(); QThreadPool.globalInstance().waitForDone(35000)
    return result['code']


class ComponentsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window); self.window = window
        self.setWindowTitle("Optional downloads"); self.resize(570, 310)
        layout = QVBoxLayout(self)
        title = QLabel("Editing and caption generation are included. Add optional tools when you need them.")
        title.setWordWrap(True); layout.addWidget(title)
        metadata = feature_packs.manifest()
        for key, name, estimate in (("android", "Android mirroring", 26240000), ("iphone", "iPhone mirroring", 266850000),
                                    ("vision", "Face / background tools", 350000000), ("vocals", "Vocal separation", 1200000000)):
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
