"""Asynchronous update checks; shared themes style every native control."""
import logging
import threading
from dataclasses import replace
from pathlib import Path
import sys
from PySide6.QtCore import QObject, QThreadPool, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QProgressDialog
from . import updates
from .version import VERSION


class UpdateDialog(QDialog):
    def __init__(self, parent, release=None, message="", startup=False):
        super().__init__(parent)
        self.setWindowTitle("Kinetic Cut updates")
        self.resize(510, 260)
        self.choice = "cancel"
        layout = QVBoxLayout(self)
        title = QLabel(f"Kinetic Cut {release.version} is available" if release else "Check for updates")
        title.setWordWrap(True); layout.addWidget(title)
        self.detail = QLabel((f"Installed: {VERSION}\nDownload: {release.size / 1e6:.1f} MB\n\n" +
                             ("Only changed application files will download. Your settings, Power Bin and optional downloads stay in place."
                              if release.incremental else "Press OK to download the installer. Your work stays open during the download."))
                            if release else message)
        self.detail.setWordWrap(True); layout.addWidget(self.detail)
        if release and release.notes:
            from PySide6.QtWidgets import QTextBrowser
            notes = QTextBrowser(); notes.setPlainText(release.notes); layout.addWidget(notes)
        actions = QHBoxLayout(); layout.addLayout(actions)
        if release and startup:
            ignore = QPushButton("Don't show again")
            ignore.setToolTip("Hide this version's startup notice. Later versions will still be offered.")
            ignore.clicked.connect(lambda: self.choose("ignore")); actions.addWidget(ignore)
        actions.addStretch()
        cancel = QPushButton("Cancel" if release else "Close")
        cancel.clicked.connect(self.reject); actions.addWidget(cancel)
        if release:
            okay = QPushButton("OK"); okay.setDefault(True)
            okay.clicked.connect(lambda: self.choose("download")); actions.addWidget(okay)

    def choose(self, choice):
        self.choice = choice; self.accept()


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window); self.window = window; self.busy = False; self.dialog = None

    def check(self, startup=False):
        if self.busy or self.window.transport.closed:
            return
        from .ui import Worker
        self.busy = True
        if not startup:
            self.dialog = UpdateDialog(self.window, message="Checking GitHub for updates…")
            self.dialog.show()
        worker = Worker(updates.check)
        worker.signals.result.connect(lambda release: self.checked(release, startup))
        worker.signals.error.connect(lambda error: self.failed(error, startup))
        self._worker = worker; QThreadPool.globalInstance().start(worker)

    def checked(self, release, startup):
        self.busy = False
        if self.window.transport.closed:
            return
        if self.dialog:
            self.dialog.close(); self.dialog = None
        if not release:
            if not startup:
                UpdateDialog(self.window, message=f"You're up to date.\nInstalled version: {VERSION}").exec()
            return
        if startup and self.window.settings.get("updates_ignored_version") == release.version:
            return
        if release.incremental and release.selection is None:
            self.prepare(release, startup)
            return
        dialog = UpdateDialog(self.window, release, startup=startup)
        dialog.exec()
        if dialog.choice == "ignore":
            from .config import save_settings
            self.window.settings["updates_ignored_version"] = release.version
            save_settings(self.window.settings)
        elif dialog.choice == "download":
            self.fetch(release)

    def prepare(self, release, startup):
        from .ui import Worker
        from .update_files import plan
        if not getattr(sys, 'frozen', False):
            if not startup:UpdateDialog(self.window, message='Install the packaged application to use automatic file updates. Source checkouts are updated through Git.').exec()
            return
        self.busy = True
        worker = Worker(lambda: replace(release, selection=plan(Path(sys.executable).parent, release.manifest)))
        worker.signals.result.connect(lambda prepared: self.checked(replace(prepared, size=prepared.selection['download_bytes']), startup))
        worker.signals.error.connect(lambda error: self.failed(error, startup))
        self._worker = worker; QThreadPool.globalInstance().start(worker)

    def failed(self, error, startup=False):
        self.busy = False
        if self.window.transport.closed:
            return
        if self.dialog:
            self.dialog.close(); self.dialog = None
        if not startup:
            UpdateDialog(self.window, message="Unable to check for updates. Check your connection and try again.\n\n"
                         + error.splitlines()[-1][:240]).exec()
        else:
            logging.info("Startup update check unavailable: %s", error.splitlines()[-1])

    def fetch(self, release):
        from .ui import Worker
        from .config import CACHE_DIR
        self.busy = True; cancel = threading.Event()
        progress = QProgressDialog("Downloading verified update…", "Cancel", 0, 100, self.window)
        progress.setWindowTitle("Kinetic Cut update"); progress.setWindowModality(Qt.NonModal)
        progress.setAutoClose(False); progress.setMinimumDuration(0)
        progress.canceled.connect(cancel.set); progress.show()
        if release.incremental:
            from .update_files import stage_update
            import uuid, shutil
            # One pending update only; finished downloads/backups never accumulate per version.
            update_cache = CACHE_DIR / 'updates'; update_cache.mkdir(parents=True, exist_ok=True)
            for previous in update_cache.glob('pending-*'):
                if previous.is_dir():shutil.rmtree(previous)
            directory = CACHE_DIR / 'updates' / ('pending-' + uuid.uuid4().hex)
            worker = Worker(lambda: stage_update(Path(sys.executable).parent, release.manifest, release.selection,
                                                directory, cancel, lambda value, text: worker.signals.progress.emit(value)))
        else:
            worker = Worker(lambda: updates.download(release, CACHE_DIR / "updates", cancel,
                                                    lambda done, total: worker.signals.progress.emit(round(done/total*100))))
        worker.signals.progress.connect(progress.setValue)
        worker.signals.result.connect(lambda path: self.ready(path, progress, release.incremental))
        worker.signals.error.connect(lambda error: (progress.close(), self.failed(error)))
        self._worker = worker; self._cancel = cancel
        self.window.destroyed.connect(cancel.set)
        QThreadPool.globalInstance().start(worker)

    def ready(self, path, progress, incremental=False):
        from PySide6.QtWidgets import QMessageBox
        from .process import popen
        progress.close(); self.busy = False
        if self.window.transport.closed:
            return
        answer = QMessageBox.question(self.window, "Update ready",
                                      "The update is verified. Save your work before closing the editor.\n\n"
                                      "Close Kinetic Cut and install the update now?")
        if answer == QMessageBox.Yes:
            if incremental:
                import os, shutil
                helper = Path(sys.executable).parent / 'KineticCutUpdater.exe'
                copied = Path(path).parent / helper.name
                try:shutil.copy2(helper, copied)
                except OSError as error:self.failed(str(error)); return
                # Start first: the helper waits for this PID. A cancelled save cannot replace files.
                if self.window.close():popen([str(copied), 'apply', str(path), '--wait-pid', str(os.getpid())])
            elif self.window.close():popen([str(path)])
