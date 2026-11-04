"""A deliberately small allowlist of disposable, reproducible editor caches.

Recovery files, generated TTS, face analysis and render logs are never offered
for removal. In particular, analysis is referenced by saved projects.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QVBoxLayout)

from .config import CACHE_DIR
from .theme_widgets import set_ui_style


CATEGORIES = (
    ('ai-enhance', 'AI enhanced video frames', 'ai-enhance', {'.png','.json','.mkv','.log'}),
    ('transcripts', 'Source transcript indexes', 'transcripts', {'.json'}),
    ('edit-reviews', 'Edit review frames and reports', 'edit-reviews', {'.png', '.json'}),
    ('motion-renders', 'Rendered motion graphics', 'motion-renders', {'.mkv'}),
    ('thumbs', 'Media thumbnails', 'thumbs', {'.jpg', '.jpeg', '.png'}),
    ('proxies', 'Playback proxies', 'proxies', {'.mp4'}),
    ('waveforms', 'Audio waveforms', 'waveforms', {'.npz'}),
    ('compounds', 'Compound previews', 'compounds', {'.mkv'}),
    ('vision-renders', 'Rendered face/effect frames', 'vision-renders', {'.mkv'}),
    ('projects', 'Project thumbnails', 'projects', {'.png'}),
    ('audio-preview', 'Processed audio previews', None, {'.wav', '.flac'}),
)


def _files(root: Path, category: str):
    """Yield only known regular files below the chosen root, never links."""
    root = Path(root).absolute()
    definition = next((row for row in CATEGORIES if row[0] == category), None)
    if definition is None:
        raise ValueError('Unknown cache category')
    _, _, folder, suffixes = definition
    if folder is None:
        if not root.is_dir() or root.is_symlink():
            return
        for child in root.iterdir():
            if child.name.startswith('audio-preview-') and child.suffix.lower() in suffixes and child.is_file() and not child.is_symlink():
                yield child
        return
    target = root / folder
    if not target.is_dir() or target.is_symlink():
        return
    for directory, dirs, files in os.walk(target, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if path.suffix.lower() in suffixes and path.is_file() and not path.is_symlink():
                yield path


def scan(root: Path = CACHE_DIR, categories=None, progress=None) -> dict[str, tuple[int, int]]:
    result = {}
    for category, *_ in CATEGORIES:
        if categories is not None and category not in categories:
            continue
        count = size = 0
        for path in _files(root, category):
            try:
                size += path.stat().st_size
                count += 1
            except OSError:
                pass
        result[category] = (count, size)
        if progress:
            progress(category)
    return result


def tree_size(root) -> int:
    """Total size of regular files below root without following links."""
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(directory, name)).st_size
            except OSError:
                pass
    return total


def removal_blocked(window) -> bool:
    """True while playback, rendering, transfers or background writers could be using cache or tools."""
    from .component_ui import active_downloads
    writing = any(not getattr(job, 'preview_decoder', False) for job in window._workers)
    return bool(writing or getattr(window.delivery, 'running', False) or window.transport.playing or active_downloads
                or getattr(window, '_vision_busy', False) or getattr(window, '_vocal_busy', False))


class _ScanSignals(QObject):
    step = Signal(int, object)   # generation, ('cache', category, (count, size)) or ('tool', key, size)
    finished = Signal(int)


class _ScanJob(QRunnable):
    """Measure caches and installed tools off the UI thread."""
    def __init__(self, generation, tools, root):
        super().__init__(); self.generation = generation; self.tools = dict(tools); self.root = root
        self.signals = _ScanSignals(); self.setAutoDelete(True)

    def run(self):
        try:
            for category, *_ in CATEGORIES:
                result = scan(self.root, (category,))[category]
                self.signals.step.emit(self.generation, ('cache', category, result))
            for key, path in self.tools.items():
                self.signals.step.emit(self.generation, ('tool', key, tree_size(path)))
        except Exception:
            logging.exception('Cache size scan failed')
        finally:
            try:
                self.signals.finished.emit(self.generation)
            except RuntimeError:
                pass


def clear(categories, root: Path = CACHE_DIR) -> tuple[int, int]:
    root = Path(root).resolve(strict=True)
    count = size = 0
    for category in categories:
        for path in _files(root, category):
            # A second check at deletion time limits races with directory swaps.
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                length = path.stat().st_size
                path.unlink()
                count += 1
                size += length
            except (FileNotFoundError, PermissionError, OSError):
                pass
    return count, size


def clear_waveforms_on_exit(root=None):
    """Run only at terminal shutdown, after all retained writers have finished."""
    root=Path(root) if root is not None else CACHE_DIR
    folder=root/'waveforms'
    try:
        if not folder.is_dir() or folder.is_symlink():return (0,0)
        # A Windows junction must not turn this into cleanup outside the cache.
        if not folder.resolve().is_relative_to(root.resolve()):return (0,0)
        return clear(('waveforms',),root)
    except (OSError,ValueError):
        logging.exception('Could not clear waveform cache on exit')
        return (0,0)


PLAYBACK_IDLE_SECONDS = 24 * 3600
CLEAR_PLAYBACK_ON_EXIT = 'clear_playback_cache_on_exit'


def prune_idle_playback(root=None, max_idle=PLAYBACK_IDLE_SECONDS, now=None):
    """Startup cleanup: drop playback copies and processed audio previews not used for a day (they rebuild on demand).

    Copies are marked as used whenever a project picks them up again, so only
    previews of media that was not opened recently are removed.
    """
    import time
    root = Path(root) if root is not None else CACHE_DIR
    folder = root / 'proxies'
    now = time.time() if now is None else now
    count = size = 0
    try:
        proxies_ok = folder.is_dir() and not folder.is_symlink() and folder.resolve().is_relative_to(root.resolve())
        for path in (_files(root, 'proxies') if proxies_ok else ()):
            try:
                info = path.stat()
                if now - info.st_mtime < max_idle or not path.resolve().is_relative_to(root.resolve()):
                    continue
                path.unlink(); count += 1; size += info.st_size
            except OSError:
                pass
    except (OSError, ValueError):
        logging.exception('Could not prune idle playback copies')
    try:
        if root.is_dir() and not root.is_symlink():
            for path in _files(root, 'audio-preview'):
                try:
                    info = path.stat()
                    if now - info.st_mtime < max_idle or not path.resolve().is_relative_to(root.resolve()):
                        continue
                    path.unlink(); count += 1; size += info.st_size
                except OSError:
                    pass
    except (OSError, ValueError):
        logging.exception('Could not prune idle audio previews')
    return (count, size)


def clear_on_exit(settings=None, root=None):
    """Terminal shutdown: waveforms always; playback proxies and processed audio previews unless the user turned it off (default on)."""
    result = clear_waveforms_on_exit(root)
    if settings and settings.get(CLEAR_PLAYBACK_ON_EXIT, True):
        try:
            base = Path(root) if root is not None else CACHE_DIR
            folder = base / 'proxies'
            if folder.is_dir() and not folder.is_symlink() and folder.resolve().is_relative_to(base.resolve()):
                clear(('proxies',), base)
        except (OSError, ValueError):
            logging.exception('Could not clear playback cache on exit')
        try:
            base = Path(root) if root is not None else CACHE_DIR
            if base.is_dir() and not base.is_symlink():
                clear(('audio-preview',), base)    # only audio-preview-*.wav files directly inside the cache
        except (OSError, ValueError):
            logging.exception('Could not clear audio previews on exit')
    return result


def size_text(value: int) -> str:
    unit = 'B'
    number = float(value)
    for candidate in ('KB', 'MB', 'GB', 'TB'):
        if number < 1024:
            break
        number /= 1024
        unit = candidate
    return f'{number:.1f} {unit}' if unit != 'B' else f'{int(number)} B'


class CacheManagerDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle('Cache Manager')
        self.setMinimumWidth(520)
        self.setModal(True)
        layout = QVBoxLayout(self)
        title = QLabel('Cache Manager')
        set_ui_style(title, 'font-size:18px; font-weight:600;')
        layout.addWidget(title)
        note = QLabel('Free space used by previews that Kinetic Cut can rebuild. Audio waveform files are cleared automatically on exit, and playback proxies not used for a day are removed at startup; both are rebuilt when needed. Projects, original media, recovery copies, generated speech, and face analysis are protected.')
        note.setWordWrap(True)
        set_ui_style(note, 'color:@text_sub;')
        layout.addWidget(note)
        self.clear_on_exit = QCheckBox('Clear playback proxies and audio previews when Kinetic Cut closes')
        self.clear_on_exit.setObjectName('clearPlaybackOnExit')
        self.clear_on_exit.setToolTip('Keeps no playback proxies or processed audio previews between sessions. They are rebuilt in the background when a project is opened, so seeking may be slower at first.')
        self.clear_on_exit.setChecked(bool(getattr(window, 'settings', {}).get(CLEAR_PLAYBACK_ON_EXIT, True)))
        self.clear_on_exit.toggled.connect(self.set_clear_on_exit)
        self.settings_group = QGroupBox('Cache Manager settings')
        settings_row = QHBoxLayout(self.settings_group)
        settings_row.addStretch(1); settings_row.addWidget(self.clear_on_exit); settings_row.addStretch(1)
        layout.addWidget(self.settings_group)
        self.clear_group = QGroupBox('Clear regenerable cache')
        clear_layout = QVBoxLayout(self.clear_group)
        self.rows = {}
        for category, label, *_ in CATEGORIES:
            row = QHBoxLayout()
            check = QCheckBox(label)
            amount = QLabel('Calculating…')
            set_ui_style(amount, 'color:@text_sub;')
            check.setEnabled(False)
            row.addWidget(check, 1)
            row.addWidget(amount)
            clear_layout.addLayout(row)
            self.rows[category] = (check, amount)
        footer = QHBoxLayout()
        self.total = QLabel('Calculating sizes…')
        self.scan_progress = QProgressBar(); self.scan_progress.setObjectName('cacheScanProgress')
        self.scan_progress.setTextVisible(False); self.scan_progress.setFixedHeight(8)
        footer.addWidget(self.total, 1); footer.addWidget(self.scan_progress, 1)
        clear_layout.addLayout(footer)
        layout.addWidget(self.clear_group)
        self.component_group = QGroupBox('Installed optional downloads')
        self.component_layout = QVBoxLayout(self.component_group); self.component_rows = {}
        layout.addWidget(self.component_group)
        self._generation = 0; self._scan_total = 0; self._scan_done = 0; self._sizes = None; self._scanning = False
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.clear_button = QPushButton('Clear selected')
        self.clear_button.clicked.connect(self.clear_selected)
        actions.addWidget(self.clear_button)
        done = QPushButton('Done')
        done.clicked.connect(self.accept)
        actions.addWidget(done)
        layout.addLayout(actions)
        self.refresh()

    def set_clear_on_exit(self, checked):
        from .config import save_settings
        settings = getattr(self.window_, 'settings', None)
        if settings is None:
            return
        settings[CLEAR_PLAYBACK_ON_EXIT] = bool(checked)
        save_settings(settings)

    def refresh(self):
        """Update tool visibility now and measure sizes in the background."""
        from .feature_packs import ROOTS, component_root, manifest
        from .component_ui import active_downloads
        metadata = manifest()
        tools = {}
        for key in ROOTS:
            root = component_root(key)
            ready = root.is_dir() and not root.is_symlink() and any(root.iterdir())
            if ready and key not in self.component_rows:
                row = QHBoxLayout(); check = QCheckBox(metadata.get(key, {}).get('name',
                    {'vision': 'Face / background tools', 'vocals': 'Vocal separation', 'enhance': 'AI Enhance'}[key]))
                amount = QLabel(); row.addWidget(check, 1); row.addWidget(amount); self.component_layout.addLayout(row)
                self.component_rows[key] = (check, amount, row)
            if key in self.component_rows:
                check, amount, row = self.component_rows[key]
                check.setVisible(ready); amount.setVisible(ready); check.setEnabled(ready and key not in active_downloads)
                if not ready:
                    check.setChecked(False)
                else:
                    amount.setText('Calculating…'); tools[key] = root
        self.component_group.setVisible(any(not check.isHidden() for check, _, _ in self.component_rows.values()))
        self._start_scan(tools)

    def _start_scan(self, tools):
        self._generation += 1
        self._scanning = True; self._sizes = {}
        self._scan_total = len(CATEGORIES) + len(tools); self._scan_done = 0
        self.scan_progress.setRange(0, self._scan_total); self.scan_progress.setValue(0); self.scan_progress.show()
        self.total.setText('Calculating sizes…'); self.clear_button.setEnabled(False)
        for check, amount in self.rows.values():
            amount.setText('Calculating…')
        job = _ScanJob(self._generation, tools, CACHE_DIR)
        job.signals.step.connect(self._scan_step, Qt.QueuedConnection)
        job.signals.finished.connect(self._scan_finished, Qt.QueuedConnection)
        self._scan_signals = job.signals
        QThreadPool.globalInstance().start(job)

    @Slot(int, object)
    def _scan_step(self, generation, payload):
        if generation != self._generation:
            return
        self._scan_done += 1; self.scan_progress.setValue(self._scan_done)
        kind, key, value = payload
        if kind == 'cache':
            check, amount = self.rows[key]; count, size = value
            self._sizes[key] = value
            amount.setText(f'{size_text(size)}  ·  {count} files')
            check.setEnabled(count > 0)
            if count == 0:
                check.setChecked(False)
        elif key in self.component_rows:
            self.component_rows[key][1].setText(size_text(value))

    @Slot(int)
    def _scan_finished(self, generation):
        if generation != self._generation:
            return
        self._scanning = False; self.scan_progress.hide(); self.clear_button.setEnabled(True)
        total = sum(size for _, size in self._sizes.values())
        self.total.setText(f'Regenerable cache: {size_text(total)}')

    def wait_for_scan(self, timeout=30.):
        """Process events until the background measurement ends (used by tests and diagnostics)."""
        import time
        from PySide6.QtWidgets import QApplication
        end = time.time() + timeout
        while self._scanning and time.time() < end:
            QApplication.processEvents(); time.sleep(.005)
        return not self._scanning

    def closeEvent(self, event):
        self._generation += 1
        super().closeEvent(event)

    def done(self, result):
        self._generation += 1
        super().done(result)

    def clear_selected(self):
        selected = [category for category, (check, _) in self.rows.items() if check.isChecked()]
        components = [key for key,(check,_,_) in self.component_rows.items() if check.isChecked()]
        if not selected and not components:
            return
        window = self.window_
        if removal_blocked(window):
            QMessageBox.information(self, 'Cache busy', 'Stop playback, transfers and rendering, and wait for background jobs to finish before clearing caches.')
            return
        summary = self._sizes if self._sizes and not self._scanning else scan(CACHE_DIR, selected)
        total = sum(summary.get(key, (0, 0))[1] for key in selected)
        extra = '\nSelected optional tools will be removed and can be downloaded again.' if components else ''
        if QMessageBox.question(self, 'Clear selected caches?', f'Remove {size_text(total)} of regenerable previews? They will be rebuilt as needed. Your projects and source media will not be deleted.'+extra) != QMessageBox.Yes:
            return
        self.clear_button.setEnabled(False)
        try:
            from .feature_packs import remove
            for key in components:remove(key)
            if components:
                from .component_ui import events
                events().changed.emit()
            count, released = clear(selected) if selected else (0, 0)
            gpu=getattr(getattr(window,'preview',None),'gpu',None) if selected else None
            if selected and gpu:gpu.invalidate_caches()
            if 'ai-enhance' in selected:
                from . import enhance
                from .enhance_preview import frames as enhanced_frames
                enhance._images.clear();enhanced_frames.clear();enhance._range_indexes.clear()
                window.preview.effect_cache.clear();window.preview.crop_cache.clear();window.preview.composition_cache.clear();window.preview.update()
            if 'proxies' in selected:
                frames=dict(window.preview.frames)
                for key in list(window.transport.decoders):
                    if key[3]=='video':window.transport.retire_decoder(key)
                window.preview.frames.update(frames)
                window.proxies.clear()
                quality=getattr(window,'preview_quality',None)
                if quality:
                    quality.seek_ready.clear(); quality.seek_signatures.clear()
                    quality.ready.clear(); quality.ready_signatures.clear()
                    quality.compat_ready.clear(); quality.compat_signatures.clear()
                window.transport.sync()
            if 'vision-renders' in selected:
                from .vision_effects import mask_image
                mask_image.cache_clear()
            window.timeline.thumbnails.clear()
            window.timeline._scaled_thumbnails.clear()
            window.timeline._waveform_pixmaps.clear()
            window.timeline.viewport().update()
            if 'thumbs' in selected:
                if hasattr(window.media_panel,'_image_icon_cache'):
                    window.media_panel._image_icon_cache.clear()
                window.media_panel.refresh()
            self.refresh()
            remaining=scan(CACHE_DIR, selected)
            kept=sum(remaining[key][0] for key in selected)
            suffix=' Some in-use files could not be removed; close and reopen the project before retrying.' if kept else ' Previews will regenerate when needed.'
            QMessageBox.information(self, 'Cache cleared', f'Removed {count} cached files ({size_text(released)}).'+suffix)
        except (OSError,ValueError,RuntimeError) as error:
            self.refresh()
            QMessageBox.warning(self,'Removal not completed',str(error))
        finally:
            self.clear_button.setEnabled(True)
