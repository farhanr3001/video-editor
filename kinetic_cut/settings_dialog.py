"""Settings dialog: keyboard shortcuts first, technical options on their own tab."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from .config import DEFAULT_SHORTCUTS
from .theme_widgets import set_ui_style
from .feature_packs import size_label

SHORTCUT_LABELS = {
    "import": "Import media", "save": "Save project", "export": "Export", "undo": "Undo", "redo": "Redo",
    "selection_mode": "Selection mode", "blade_mode": "Cut/Split", "crop_selected": "Crop selected",
    "snapping": "Toggle snapping", "retime_controls": "Retime controls",
    "play_pause": "Play / pause", "shuttle_back": "Shuttle back", "shuttle_stop": "Stop",
    "shuttle_forward": "Shuttle forward", "mark_in": "Mark in", "mark_out": "Mark out",
    "cut": "Split clip", "delete": "Lift", "ripple_delete": "Ripple delete",
    "vertical_layout": "Vertical layout", "captions": "Generate captions", "remove_silence": "Remove silence",
    "instant_package": "Instant package",
}
SECTIONS = (
    ("File & project", ("import", "save", "export", "undo", "redo")),
    ("Playback", ("play_pause", "shuttle_back", "shuttle_stop", "shuttle_forward", "mark_in", "mark_out")),
    ("Editing", ("selection_mode", "blade_mode", "cut", "delete", "ripple_delete", "crop_selected", "snapping", "retime_controls")),
    ("Tools", ("vertical_layout", "captions", "remove_silence", "instant_package")),
)
CUSTOM_MODEL = '__custom_model__'
MODEL_LABELS = {'tiny.en': 'tiny.en (fastest, least accurate)', 'base.en': 'base.en (default)',
                'small.en': 'small.en', 'large-v3-turbo': 'large-v3-turbo (most accurate)'}
MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_unknown}


def normalize(text: str) -> str:
    return QKeySequence(text).toString(QKeySequence.PortableText) if text else ""


class ShortcutButton(QPushButton):
    """Click, press the new combination. Esc cancels, Backspace/Delete clears."""
    changed = Signal(str)

    def __init__(self, value=""):
        super().__init__(); self.value = normalize(value); self.recording = False; self.conflict = False
        self.setObjectName('shortcutKey'); self.setFocusPolicy(Qt.StrongFocus); self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(150); self.clicked.connect(self.begin); self.refresh()

    def begin(self):
        self.recording = True; self.setFocus(); self.refresh()

    def stop(self):
        self.recording = False; self.refresh()

    def set_value(self, value, emit=True):
        value = normalize(value)
        if value != self.value:
            self.value = value
            if emit: self.changed.emit(value)
        self.recording = False; self.refresh()

    def set_conflict(self, flag):
        self.conflict = flag; self.refresh()

    def refresh(self):
        if self.recording:
            self.setText('Press keys…')
            border, color = '@accent', '@accent'
        elif self.value:
            self.setText(self.value.replace('+', '  +  '))
            border, color = ('#e5534b' if self.conflict else '@border_subtle'), '@text_main'
        else:
            self.setText('Not set'); border, color = '@border_subtle', '@text_sub'
        set_ui_style(self, f'QPushButton#shortcutKey{{background:@bg_input;border:1px solid {border};border-radius:6px;'
                           f'color:{color};padding:5px 10px;font-weight:{600 if self.value else 400};}}'
                           'QPushButton#shortcutKey:hover{border-color:@accent;}')

    def keyPressEvent(self, event):
        if not self.recording:
            return super().keyPressEvent(event)
        key = event.key()
        if key == Qt.Key_Escape:
            return self.stop()
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and not event.modifiers():
            return self.set_value('')
        if key in MODIFIER_KEYS:
            return
        combo = QKeySequence(int(event.modifiers().value) | key).toString(QKeySequence.PortableText)
        self.set_value(combo)

    def focusOutEvent(self, event):
        if self.recording: self.stop()
        super().focusOutEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window); self.window_ = window; s = window.settings
        self.setWindowTitle('Kinetic Cut settings'); self.setObjectName('settingsDialog'); self.resize(640, 520)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(); self.tabs.setObjectName('settingsTabs'); layout.addWidget(self.tabs)
        self.tabs.addTab(self.build_shortcuts(s), 'Keyboard shortcuts')
        self.tabs.addTab(self.build_advanced(s), 'Advanced')
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.check_conflicts()

    # --- keyboard shortcuts -------------------------------------------------
    def build_shortcuts(self, s):
        page = QWidget(); outer = QVBoxLayout(page)
        top = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Search shortcuts'); self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter); top.addWidget(self.search, 1)
        reset_all = QPushButton('Reset all to defaults'); reset_all.clicked.connect(self.reset_all); top.addWidget(reset_all)
        outer.addLayout(top)
        hint = QLabel('Click a shortcut, then press the new keys. Esc cancels · Backspace clears.')
        set_ui_style(hint, 'color:@text_sub;'); outer.addWidget(hint)
        self.status = QLabel(''); self.status.setWordWrap(True); outer.addWidget(self.status)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget(); form = QVBoxLayout(body); form.setContentsMargins(0, 0, 6, 0)
        self.keys = {}; self.rows = {}; self.headers = {}; current = s.get('shortcuts', {})
        for title, logicals in SECTIONS:
            header = QLabel(title.upper()); set_ui_style(header, 'color:@text_sub;font-weight:600;letter-spacing:1px;padding-top:8px;')
            form.addWidget(header); self.headers[title] = (header, logicals)
            for logical in logicals:
                row = QWidget(); line = QHBoxLayout(row); line.setContentsMargins(0, 0, 0, 0)
                name = QLabel(SHORTCUT_LABELS[logical]); line.addWidget(name, 1)
                button = ShortcutButton(current.get(logical, DEFAULT_SHORTCUTS.get(logical, '')))
                button.changed.connect(lambda _v, k=logical: self.edited(k))
                default = QPushButton('Reset'); default.setObjectName('shortcutReset'); default.setFlat(True)
                default.setToolTip('Restore the default: ' + (DEFAULT_SHORTCUTS.get(logical) or 'none'))
                default.clicked.connect(lambda _c=False, k=logical: self.keys[k].set_value(DEFAULT_SHORTCUTS.get(k, '')))
                line.addWidget(button); line.addWidget(default)
                form.addWidget(row); self.keys[logical] = button; self.rows[logical] = (row, name, default)
        form.addStretch(1); scroll.setWidget(body); outer.addWidget(scroll, 1)
        return page

    def edited(self, logical):
        self.refresh_resets(); self.check_conflicts()

    def refresh_resets(self):
        for logical, (row, name, default) in self.rows.items():
            default.setEnabled(self.keys[logical].value != normalize(DEFAULT_SHORTCUTS.get(logical, '')))

    def check_conflicts(self):
        self.refresh_resets(); seen = {}
        for logical, button in self.keys.items():
            if button.value: seen.setdefault(button.value, []).append(logical)
        clashes = {value: names for value, names in seen.items() if len(names) > 1}
        for logical, button in self.keys.items():
            button.set_conflict(button.value in clashes)
        if clashes:
            parts = [f"{value} is used by " + ' and '.join(SHORTCUT_LABELS[n] for n in names) for value, names in clashes.items()]
            self.status.setText('⚠ ' + '; '.join(parts)); set_ui_style(self.status, 'color:#e5534b;')
        else:
            self.status.setText(''); self.status.setStyleSheet('')
        return clashes

    def reset_all(self):
        for logical, button in self.keys.items():
            button.set_value(DEFAULT_SHORTCUTS.get(logical, ''), emit=False)
        self.check_conflicts()

    def filter(self, text):
        text = text.strip().lower()
        for logical, (row, name, _default) in self.rows.items():
            row.setVisible(not text or text in name.text().lower() or text in self.keys[logical].value.lower())
        for header, logicals in self.headers.values():
            header.setVisible(any(self.rows[l][0].isVisible() or not text for l in logicals) and (not text or any(self.rows[l][0].isVisible() for l in logicals)))

    # --- advanced ------------------------------------------------------------
    def build_advanced(self, s):
        page = QWidget(); form = QFormLayout(page)
        self.ffmpeg = QLineEdit(s.get('ffmpeg', 'ffmpeg')); self.ffprobe = QLineEdit(s.get('ffprobe', 'ffprobe'))
        from .caption_runtime import CHOICES
        self.whisper_size = QComboBox(); self.whisper_size.setObjectName('speechModel')
        for name in CHOICES: self.whisper_size.addItem(MODEL_LABELS.get(name, name), name)
        self.whisper_size.addItem('Custom model folder…', CUSTOM_MODEL)
        saved = str(s.get('whisper_model', 'base.en') or 'base.en')
        self.model_folder = QLineEdit(); self.model_folder.setPlaceholderText('Folder containing model.bin (faster-whisper / CTranslate2 format)')
        browse = QPushButton('Browse…'); browse.clicked.connect(self.browse_model)
        self.model_folder_row = QWidget(); folder_line = QHBoxLayout(self.model_folder_row); folder_line.setContentsMargins(0, 0, 0, 0)
        folder_line.addWidget(self.model_folder, 1); folder_line.addWidget(browse)
        self.model_status = QLabel(); self.model_status.setWordWrap(True); self.model_status.setObjectName('speechModelStatus')
        index = self.whisper_size.findData(saved)
        if index < 0:
            index = self.whisper_size.findData(CUSTOM_MODEL); self.model_folder.setText(saved)
        self.whisper_size.setCurrentIndex(index)
        self.whisper_size.currentIndexChanged.connect(self.update_model_status); self.model_folder.textChanged.connect(self.update_model_status)
        self.whisper = QLineEdit(s.get('whisper_cli', '')); self.model = QLineEdit(s.get('whisper_model_path', '')); self.sfx = QLineEdit(s.get('sfx_folder', ''))
        form.addRow('FFmpeg command', self.ffmpeg); form.addRow('ffprobe command', self.ffprobe); form.addRow('Speech model', self.whisper_size)
        form.addRow('Model folder', self.model_folder_row); form.addRow('', self.model_status)
        self.model_folder_label = form.labelForField(self.model_folder_row)
        form.addRow('whisper-cli override', self.whisper); form.addRow('whisper.cpp model', self.model); form.addRow('Auto-index SFX folder', self.sfx)
        from .playback_config import MODES
        self.decoder = QComboBox(); self.decoder.addItems(MODES); self.decoder.setCurrentText(s.get('playback_decoder', MODES[0])); form.addRow('Playback decoder', self.decoder)
        note = QLabel('Restart after changing decoder. GPU decoding depends on codec/driver support.\nSee File → Playback Diagnostics for the active preview backend. Export encoder is selected in Deliver.')
        note.setWordWrap(True); set_ui_style(note, 'color:@text_sub;'); form.addRow(note)
        self.update_model_status()
        return page

    def speech_model(self):
        data = self.whisper_size.currentData()
        return self.model_folder.text().strip() if data == CUSTOM_MODEL else data

    def browse_model(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, 'Choose a speech model folder', self.model_folder.text())
        if folder: self.model_folder.setText(folder)

    def update_model_status(self, *_):
        from .caption_runtime import is_model_folder, model_status
        custom = self.whisper_size.currentData() == CUSTOM_MODEL
        self.model_folder_row.setVisible(custom)
        if self.model_folder_label: self.model_folder_label.setVisible(custom)
        name = self.speech_model()
        if custom:
            ok = bool(name) and is_model_folder(name)
            text = 'Model found. Captions will use this folder.' if ok else 'Choose a folder that contains model.bin and config.json.'
            color = '@text_sub' if ok else '#e5534b'
        else:
            state, detail = model_status(name)
            text = 'Installed and ready.' if state == 'ready' else f'Not downloaded yet: about {size_label(detail * 1_000_000)} is downloaded the first time captions are generated (or get it from Optional downloads).'
            if name == 'large-v3-turbo': text += ' Most accurate; much faster with an NVIDIA GPU.'
            color = '@text_sub'
        self.model_status.setText(text); set_ui_style(self.model_status, f'color:{color};')

    def accept(self):
        from .caption_runtime import is_model_folder
        if self.whisper_size.currentData() == CUSTOM_MODEL and not is_model_folder(self.speech_model()):
            from PySide6.QtWidgets import QMessageBox
            self.tabs.setCurrentIndex(1)
            QMessageBox.warning(self, 'Speech model folder', 'Choose a folder that contains a faster-whisper model (model.bin and config.json), or pick a listed model.')
            return
        if self.check_conflicts():
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(self, 'Shortcut conflicts', 'Some shortcuts are assigned twice, so only one of them will work. Save anyway?') != QMessageBox.Yes:
                return
        super().accept()

    def apply(self):
        w = self.window_; s = w.settings
        s['playback_decoder'] = self.decoder.currentText()
        s.update(ffmpeg=self.ffmpeg.text(), ffprobe=self.ffprobe.text(), whisper_model=self.speech_model(),
                 whisper_cli=self.whisper.text(), whisper_model_path=self.model.text(), sfx_folder=self.sfx.text())
        s.setdefault('shortcuts', {}).update({key: button.value for key, button in self.keys.items()})
