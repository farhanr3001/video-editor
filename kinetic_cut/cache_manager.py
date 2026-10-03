"""A deliberately small allowlist of disposable, reproducible editor caches.

Recovery files, generated TTS, face analysis and render logs are never offered
for removal. In particular, analysis is referenced by saved projects.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QVBoxLayout)

from .config import CACHE_DIR
from .theme_widgets import set_ui_style


CATEGORIES = (
    ('thumbs', 'Media thumbnails', 'thumbs', {'.jpg', '.jpeg', '.png'}),
    ('proxies', 'Playback proxies', 'proxies', {'.mp4'}),
    ('waveforms', 'Audio waveforms', 'waveforms', {'.npz'}),
    ('compounds', 'Compound previews', 'compounds', {'.mkv'}),
    ('vision-renders', 'Rendered face/effect frames', 'vision-renders', {'.mkv'}),
    ('projects', 'Project thumbnails', 'projects', {'.png'}),
    ('audio-preview', 'Processed audio previews', None, {'.wav'}),
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


def scan(root: Path = CACHE_DIR) -> dict[str, tuple[int, int]]:
    result = {}
    for category, *_ in CATEGORIES:
        count = size = 0
        for path in _files(root, category):
            try:
                size += path.stat().st_size
                count += 1
            except OSError:
                pass
        result[category] = (count, size)
    return result


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
        note = QLabel('Free space used by previews that Kinetic Cut can rebuild. Projects, original media, recovery copies, generated speech, and face analysis are protected.')
        note.setWordWrap(True)
        set_ui_style(note, 'color:@text_sub;')
        layout.addWidget(note)
        self.rows = {}
        for category, label, *_ in CATEGORIES:
            row = QHBoxLayout()
            check = QCheckBox(label)
            amount = QLabel()
            set_ui_style(amount, 'color:@text_sub;')
            row.addWidget(check, 1)
            row.addWidget(amount)
            layout.addLayout(row)
            self.rows[category] = (check, amount)
        self.total = QLabel()
        layout.addWidget(self.total)
        from PySide6.QtWidgets import QGroupBox
        self.component_group = QGroupBox('Installed optional downloads')
        self.component_layout = QVBoxLayout(self.component_group); self.component_rows = {}
        layout.addWidget(self.component_group)
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

    def refresh(self):
        from .feature_packs import ROOTS, installed, component_root, manifest
        from .component_ui import active_downloads
        metadata = manifest()
        for key in ROOTS:
            ready = installed(key)
            if ready and key not in self.component_rows:
                row = QHBoxLayout(); check = QCheckBox(metadata.get(key,{}).get('name',
                    {'android':'Android mirroring','iphone':'iPhone mirroring','vision':'Face / background tools','vocals':'Vocal separation'}[key]))
                amount = QLabel(); row.addWidget(check,1); row.addWidget(amount); self.component_layout.addLayout(row)
                self.component_rows[key] = (check,amount,row)
            if key in self.component_rows:
                check,amount,row = self.component_rows[key]
                check.setVisible(ready); amount.setVisible(ready); check.setEnabled(ready and key not in active_downloads)
                if not ready:check.setChecked(False)
                else:amount.setText(size_text(sum(p.stat().st_size for p in component_root(key).rglob('*') if p.is_file())))
        self.component_group.setVisible(any(installed(key) for key in ROOTS))
        sizes = scan()
        total = 0
        for category, (check, amount) in self.rows.items():
            count, size = sizes[category]
            total += size
            amount.setText(f'{size_text(size)}  ·  {count} files')
            check.setEnabled(count > 0)
            if count == 0:
                check.setChecked(False)
        self.total.setText(f'Regenerable cache: {size_text(total)}')

    def clear_selected(self):
        selected = [category for category, (check, _) in self.rows.items() if check.isChecked()]
        components = [key for key,(check,_,_) in self.component_rows.items() if check.isChecked()]
        if not selected and not components:
            return
        window = self.window_
        from .component_ui import active_downloads
        from PySide6.QtCore import QProcess
        if window._workers or getattr(window.delivery, 'running', False) or getattr(window.phone_connect, 'active_job', None) or window.transport.playing or active_downloads or getattr(window,'_vision_busy',False) or getattr(window,'_vocal_busy',False) or (components and window.phone_connect.mirror.process.state() != QProcess.NotRunning):
            QMessageBox.information(self, 'Cache busy', 'Stop playback, transfers and rendering, and wait for background jobs to finish before clearing caches.')
            return
        summary = scan()
        total = sum(summary[key][1] for key in selected)
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
            count, released = clear(selected)
            if 'proxies' in selected:
                window.proxies.clear()
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
            remaining=scan()
            kept=sum(remaining[key][0] for key in selected)
            suffix=' Some in-use files could not be removed; close and reopen the project before retrying.' if kept else ' Previews will regenerate when needed.'
            QMessageBox.information(self, 'Cache cleared', f'Removed {count} cached files ({size_text(released)}).'+suffix)
        except (OSError,ValueError,RuntimeError) as error:
            self.refresh()
            QMessageBox.warning(self,'Removal not completed',str(error))
        finally:
            self.clear_button.setEnabled(True)
