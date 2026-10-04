"""Read-only, session-independent media sources. Indexing never edits a project."""
import hashlib
import os
import threading
import time
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QObject, QFileSystemWatcher, QTimer, Signal, Slot, Qt

from .media import media_kind, probe
from .media_insert import source_key


def folder_key(path):
    return 'watch:' + hashlib.sha256(source_key(path).encode('utf-8')).hexdigest()[:24]


@dataclass
class Entry:
    signature: tuple
    since: float
    path: str = ''
    media: object = None
    loaded: tuple = ()
    retry_at: float = 0
    attempts: int = 0


@dataclass
class Folder:
    path: str
    entries: dict = field(default_factory=dict)
    available: bool = False
    error: str = ''

    def media(self):
        return [entry.media for entry in self.entries.values()
                if entry.media is not None and entry.loaded == entry.signature]


def fingerprint(path):
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def index_folders(folders, ffprobe, ffmpeg, cancel, *, now=None, loader=probe,
                  settle=1.0, batch=8):
    """Detached state in/out; scan and decode only on the worker thread.

    Two stable observations prevent indexing an ongoing copy. Changed and failed
    files are retried; a post-probe fingerprint rejects changes during decoding.
    Limit each batch so a large folder cannot monopolize the import worker pool.
    """
    now = time.monotonic() if now is None else now
    result = {}; budget = batch; more = False
    for key, old in folders.items():
        if cancel.is_set():break
        current = Folder(old.path); result[key] = current
        try:
            with os.scandir(old.path) as listing:
                for file in listing:
                    if cancel.is_set():break
                    if media_kind(file.name) == 'unknown' or not file.is_file():continue
                    path = os.path.abspath(file.path); identity = source_key(path)
                    try:signature = fingerprint(path)
                    except OSError:continue
                    previous = old.entries.get(identity)
                    entry = (replace(previous) if previous and previous.signature == signature
                             else Entry(signature, now, path))
                    current.entries[identity] = entry
            current.available = True
        except OSError as error:
            current.error = str(error)
            continue
        for identity, entry in current.entries.items():
            if cancel.is_set():break
            if entry.loaded == entry.signature or now-entry.since < settle or now < entry.retry_at:continue
            if not entry.signature[0]:continue
            if budget <= 0:
                more = True; continue
            budget -= 1
            try:
                media = loader(entry.path, ffprobe, ffmpeg, timeout=15)
                if fingerprint(entry.path) != entry.signature:continue
                media.id = folder_key(identity)
                # File spelling/case must remain suitable for Explorer and display.
                entry.media = media; entry.loaded = entry.signature
                entry.attempts = 0; entry.retry_at = 0
            except Exception:
                entry.attempts += 1
                entry.retry_at = now + min(30, 2 ** min(entry.attempts, 5))
    return result, more


class WatchFolders(QObject):
    changed = Signal()

    def __init__(self, panel):
        super().__init__(panel); self.panel = panel; self.folders = {}
        self.busy = False; self.closed = False; self.rescan = False
        self.cancel = threading.Event()
        saved = panel.window.settings.get('media_watch_folders', [])
        if isinstance(saved, list):
            for path in saved:
                if isinstance(path, str) and path and os.path.isabs(path):
                    path = os.path.abspath(path)
                    self.folders.setdefault(folder_key(path), Folder(path))
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.schedule)
        self.debounce = QTimer(self); self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.check)
        self.timer = QTimer(self); self.timer.setInterval(2000)
        self.timer.timeout.connect(self.check); self.timer.start()
        self.debounce.start(0)

    def save(self):
        from .config import save_settings
        self.panel.window.settings['media_watch_folders'] = [f.path for f in self.folders.values()]
        save_settings(self.panel.window.settings)

    def add(self, path):
        path = os.path.abspath(path); key = folder_key(path)
        if key not in self.folders:
            self.folders[key] = Folder(path); self.save()
        self.schedule(); return key

    def remove(self, key):
        folder = self.folders.pop(key, None)
        if not folder:return
        if folder.path in self.watcher.directories():self.watcher.removePath(folder.path)
        self.save(); self.changed.emit()

    @Slot()
    def schedule(self, *_):
        if self.closed:return
        if self.busy:self.rescan = True
        else:self.debounce.start(250)

    @Slot()
    def check(self):
        if self.closed or self.busy or not self.folders:return
        from .ui import Worker
        self.busy = True; self.rescan = False
        settings = self.panel.window.settings
        worker = Worker(index_folders, dict(self.folders), settings.get('ffprobe', 'ffprobe'),
                        settings.get('ffmpeg', 'ffmpeg'), self.cancel)
        worker.signals.result.connect(self.indexed, Qt.QueuedConnection)
        worker.signals.error.connect(self.failed, Qt.QueuedConnection)
        self.panel.window.start_worker(worker)

    @Slot(object)
    def indexed(self, result):
        self.busy = False
        if self.closed:return
        indexed, more = result
        presence = {}
        for key, folder in indexed.items():
            # Removed watches cannot be resurrected by an in-flight result.
            if key in self.folders:
                presence.update({identity:identity not in folder.entries for identity in self.folders[key].entries})
                presence.update({identity:False for identity in folder.entries})
                self.folders[key] = folder
        desired = {f.path for f in self.folders.values() if f.available}
        attached = set(self.watcher.directories())
        if attached-desired:self.watcher.removePaths(list(attached-desired))
        if desired-attached:self.watcher.addPaths(list(desired-attached))
        if presence and hasattr(self.panel,'missing_media'):self.panel.missing_media.checked(presence)
        self.changed.emit()
        if more or self.rescan:self.schedule()

    @Slot(str)
    def failed(self, _):
        self.busy = False
        if self.rescan:self.schedule()

    def resolve(self, media_id):
        return next((media for folder in self.folders.values() for media in folder.media()
                     if media.id == media_id), None)

    def status(self, key):
        folder = self.folders.get(key)
        if not folder:return ''
        if not folder.available:return 'Folder unavailable — waiting for it to return' if folder.error else 'Scanning folder…'
        pending = sum(e.loaded != e.signature and not e.attempts for e in folder.entries.values())
        failed = sum(bool(e.attempts) for e in folder.entries.values())
        text = f'Watching · {len(folder.media())} files'
        if pending:text += f' · {pending} preparing'
        if failed:text += f' · {failed} unreadable (retrying)'
        return text

    @Slot()
    def stop(self):
        if self.closed:return
        self.closed = True; self.cancel.set(); self.timer.stop(); self.debounce.stop()
        paths = self.watcher.directories()
        if paths:self.watcher.removePaths(paths)
