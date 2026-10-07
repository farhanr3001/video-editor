"""Asynchronous update checks; shared themes style every native control."""
import logging
import threading
from dataclasses import replace
from pathlib import Path
import sys
from PySide6.QtCore import QObject, Qt, Slot
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QProgressDialog, QGridLayout, QTextBrowser, QSizePolicy)
from .theme_widgets import set_ui_style, set_ui_icon
from . import updates
from .version import VERSION


class UpdateDialog(QDialog):
    def __init__(self, parent, release=None, message="", startup=False, state="info"):
        super().__init__(parent)
        self.setWindowTitle("Kinetic Cut updates")
        self.setMinimumWidth(360)
        self.choice = "cancel"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16); layout.setSpacing(10)
        header = QHBoxLayout(); header.setSpacing(10)
        icon = QLabel(self); icon.setFixedSize(24, 24)
        set_ui_icon(icon, 'download' if release else 'check' if state == 'current' else 'refresh-cw', size=24)
        header.addWidget(icon, 0, Qt.AlignTop)
        headings = dict(current="You're up to date", checking="Checking for updates", error="Unable to check for updates")
        self.heading = QLabel("Update available" if release else headings.get(state, "Check for updates"))
        self.heading.setTextFormat(Qt.PlainText); self.heading.setWordWrap(True)
        set_ui_style(self.heading, 'font-size:16px; font-weight:600; color:@text_main;')
        header.addWidget(self.heading, 1); layout.addLayout(header)
        self.versions = QGridLayout(); self.versions.setHorizontalSpacing(16); self.versions.setVerticalSpacing(5)
        self.versions.setColumnStretch(1, 1)
        if release:
            for row, (label, value) in enumerate((('Installed version', VERSION),
                                                ('Available version', release.version),
                                                ('Download size', f'{release.size / 1e6:.1f} MB'))):
                key = QLabel(label); set_ui_style(key, 'color:@text_sub;')
                self.versions.addWidget(key, row, 0); self.versions.addWidget(QLabel(value), row, 1)
            layout.addLayout(self.versions)
        self.detail = QLabel(("Only changed application files will download. Your settings, Power Bin and optional downloads stay in place."
                              if release.incremental else "Press OK to download the installer. Your work stays open during the download.")
                             if release else message)
        self.detail.setTextFormat(Qt.PlainText); self.detail.setWordWrap(True)
        self.detail.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(self.detail)
        self.notes = None
        if release and release.notes:
            caption = QLabel("What's new"); set_ui_style(caption, 'font-weight:600; color:@text_main;'); layout.addWidget(caption)
            self.notes = QTextBrowser(); self.notes.setPlainText(release.notes)
            self.notes.setMinimumHeight(90); self.notes.setMaximumHeight(140)
            layout.addWidget(self.notes)
        layout.addStretch()
        actions = QHBoxLayout(); actions.setContentsMargins(0, 6, 0, 0); actions.setSpacing(8); layout.addLayout(actions)
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
        self.resize(460, max(130, layout.totalHeightForWidth(460)))

    def choose(self, choice):
        self.choice = choice; self.accept()


class UpdateController(QObject):
    def __init__(self, window):
        super().__init__(window); self.window = window; self.busy = False; self.dialog = None; self._worker = None

    def _start_worker(self,worker):
        self._worker=worker
        worker.signals.finished.connect(self._worker_finished,Qt.QueuedConnection)
        self.window.start_worker(worker)

    @Slot()
    def _worker_finished(self):
        if self._worker and self._worker.signals is self.sender():self._worker=None

    def check(self, startup=False):
        if self.busy or self.window.transport.closed:
            return
        from .ui import Worker
        self.busy = True
        cancelled=threading.Event()
        if not startup:
            self.dialog = UpdateDialog(self.window, message="Contacting GitHub for the latest release…", state="checking")
            self.dialog.rejected.connect(cancelled.set)
            self.dialog.show()
        worker = Worker(updates.check)
        worker.signals.result.connect(lambda release: self.checked(release,startup,cancelled))
        worker.signals.error.connect(lambda error: self.failed(error,startup,cancelled))
        self._start_worker(worker)

    def checked(self, release, startup, cancelled=None):
        self.busy = False
        was_cancelled=bool(cancelled and cancelled.is_set())
        if self.window.transport.closed:
            return
        if self.dialog:
            self.dialog.close(); self.dialog = None
        if was_cancelled:return
        if not release:
            if not startup:
                UpdateDialog(self.window, message=f"Installed version: {VERSION}", state="current").exec()
            return
        if startup and self.window.settings.get("updates_ignored_version") == release.version:
            return
        if release.incremental and release.selection is None:
            self.prepare(release,startup)
            return
        dialog = UpdateDialog(self.window, release, startup=startup)
        dialog.exec()
        if dialog.choice == "ignore":
            from .config import save_settings
            self.window.settings["updates_ignored_version"] = release.version
            save_settings(self.window.settings)
        elif dialog.choice == "download":
            self.fetch(release)

    def prepare(self, release, startup, cancelled=None):
        from .ui import Worker
        from .update_files import plan
        if not getattr(sys, 'frozen', False):
            if not startup:UpdateDialog(self.window, message='Install the packaged application to use automatic file updates. Source checkouts are updated through Git.').exec()
            return
        self.busy = True
        worker = Worker(lambda: replace(release, selection=plan(Path(sys.executable).parent, release.manifest)))
        worker.signals.result.connect(lambda prepared: self.checked(replace(prepared,size=prepared.selection['download_bytes']),startup,cancelled))
        worker.signals.error.connect(lambda error: self.failed(error,startup,cancelled))
        self._start_worker(worker)

    def failed(self, error, startup=False, cancelled=None):
        self.busy = False
        was_cancelled=bool(cancelled and cancelled.is_set())
        if self.window.transport.closed:
            return
        if self.dialog:
            self.dialog.close(); self.dialog = None
        if was_cancelled:return
        if not startup:
            UpdateDialog(self.window, message="Unable to check for updates. Check your connection and try again.\n\n"
                         + (error.splitlines() or ['Unknown update error'])[-1][:240], state="error").exec()
        else:
            logging.info("Startup update check unavailable: %s", (error.splitlines() or ['Unknown update error'])[-1])

    def fetch(self, release):
        if self.busy or self.window.transport.closed:return
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
        worker.signals.result.connect(lambda path: self.ready(path,progress,release.incremental,cancel))
        worker.signals.error.connect(lambda error: self.download_failed(error,progress,cancel))
        self._cancel = cancel
        self.window.destroyed.connect(cancel.set)
        self._start_worker(worker)

    def download_failed(self,error,progress,cancelled):
        was_cancelled=cancelled.is_set()
        progress.close(); self.busy=False
        if not was_cancelled:self.failed(error)

    def ready(self, path, progress, incremental=False, cancelled=None):
        from PySide6.QtWidgets import QMessageBox
        from .process import popen
        was_cancelled=cancelled and cancelled.is_set()
        progress.close(); self.busy = False
        if was_cancelled:return
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
                command=[str(copied), 'apply', str(path), '--wait-pid', str(os.getpid())]
            else:command=[str(path)]
            # Shutdown may be deferred while cancellable editing jobs settle.
            # A rejected Save/Cancel prompt must never launch the updater later.
            launched=False
            signal=self.window.shutdownFinished
            def launch():
                nonlocal launched
                if launched:return
                launched=True
                signal.disconnect(launch)
                popen(command)
            signal.connect(launch)
            if self.window.close():launch()
            elif not getattr(self.window,'_closing',False):signal.disconnect(launch)
