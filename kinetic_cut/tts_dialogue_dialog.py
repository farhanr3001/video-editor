"""Dialog for generating full spoken dialogue from a video script with batch processing."""
from __future__ import annotations

from .theme_widgets import set_ui_style
import os
import re
from threading import Event
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QThread, QObject, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QSlider, QPushButton, QFormLayout, QProgressBar,
    QMessageBox, QWidget, QScrollArea, QDialogButtonBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .controls import SafeComboBox
from .dialog_jobs import RetainedThread
from .icons import lucide_icon, resource_path
from .tts import (
    VOICES, DEFAULT_VOICE, synthesize_speech,
    extract_preview_sentence, synthesize_dialogue_batches
)


class _PreviewWorker(QObject):
    finished = Signal(str, object)
    error = Signal(str, object)
    settled = Signal()

    def __init__(self, text: str, voice: str, rate: int, pitch: int, ffmpeg_bin: str = "ffmpeg"):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.ffmpeg_bin = ffmpeg_bin
        self._cancel = Event()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()

    @Slot()
    def run(self):
        try:
            path = synthesize_speech(
                text=self.text,
                voice=self.voice,
                rate_percent=self.rate,
                pitch_hz=self.pitch,
                ffmpeg_bin=self.ffmpeg_bin,
                cancel_check=self._cancel.is_set,
            )
            if not self.cancelled:
                self.finished.emit(path, self._cancel)
        except Exception as err:
            if not self.cancelled:
                self.error.emit(str(err), self._cancel)
        finally:
            self.settled.emit()


class _DialogueWorker(QObject):
    progress = Signal(int, str, object)
    finished = Signal(str, object)
    error = Signal(str, object)
    settled = Signal()

    def __init__(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        ffmpeg_bin: str = "ffmpeg"
    ):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.ffmpeg_bin = ffmpeg_bin
        self._cancel = Event()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()

    @Slot()
    def run(self):
        try:
            path = synthesize_dialogue_batches(
                text=self.text,
                voice=self.voice,
                rate_percent=self.rate,
                pitch_hz=self.pitch,
                progress_callback=self._progress,
                ffmpeg_bin=self.ffmpeg_bin,
                cancel_check=lambda: self.cancelled,
            )
            if not self.cancelled:
                self.finished.emit(path, self._cancel)
        except Exception as err:
            if not self.cancelled:
                self.error.emit(str(err), self._cancel)
        finally:
            self.settled.emit()

    def _progress(self, pct, msg):
        if not self.cancelled:
            self.progress.emit(pct, msg, self._cancel)


class TTSDialogueDialog(QDialog):
    """Dialogue generation dialog with batch processing and live progress."""

    speechGenerated = Signal(dict)

    def __init__(self, parent=None, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Generate TTS Dialogue")
        avail_h = self.screen().availableGeometry().height() if self.screen() else 700
        self.resize(470, min(600, avail_h - 60))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._preview_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._preview_player.setAudioOutput(self._audio_output)
        self._preview_player.playbackStateChanged.connect(self._on_player_state_changed)

        self._preview_thread: RetainedThread | None = None
        self._preview_worker: _PreviewWorker | None = None

        self._generate_thread: RetainedThread | None = None
        self._generate_worker: _DialogueWorker | None = None
        self._is_generating = False
        self._closed = False
        self._generation_data = None
        self._preview_token = None
        self._generation_token = None

        self.result_data: dict | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(10)
        self.form = form

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(content)
        area.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(area, 1)

        # 1. Script input box
        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText("Type or paste your video script here...")
        self.script_edit.setMinimumHeight(180)
        set_ui_style(self.script_edit, "QPlainTextEdit {  background: @bg_input;  border: 1px solid @border_subtle;  border-radius: 4px;  color: @text_main;  padding: 10px;  font-size: 13px;  font-family: 'Segoe UI', sans-serif;  line-height: 1.4;}QPlainTextEdit:focus { border: 1px solid @accent; }")
        if initial_text:
            self.script_edit.setPlainText(initial_text)
        self.script_edit.textChanged.connect(self._update_counter)
        form.addRow(self.script_edit)

        # Counter for characters, words, and duration
        self.counter_lbl = QLabel("0 characters · 0 words · ~0.0s")
        set_ui_style(self.counter_lbl, 'font-size: 11px; color: @text_sub; padding-left: 2px;')
        form.addRow(self.counter_lbl)

        # 2. Voice audition button (previews first sentence only)
        self.preview_btn = QPushButton("Play voice preview")
        self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))
        self.preview_btn.setFixedHeight(30)
        self.preview_btn.clicked.connect(self._toggle_preview)
        form.addRow(self.preview_btn)

        # 3. TTS property settings (ONLY Voice, Speed, Pitch)
        self.voice_combo = SafeComboBox()
        for display_name, voice_id in VOICES:
            self.voice_combo.addItem(display_name, voice_id)
        idx = next((i for i, (_, vid) in enumerate(VOICES) if vid == DEFAULT_VOICE), 0)
        self.voice_combo.setCurrentIndex(idx)
        chevron_path = resource_path("assets", "icons", "dropdown-chevron.svg").as_posix()
        set_ui_style(self.voice_combo, 'QComboBox::down-arrow {image:url("@arrow_combo");width:14px;height:14px;} QComboBox::drop-down {width:26px;border-left:1px solid @border_subtle;}')
        form.addRow("Voice", self.voice_combo)

        # Speed slider row
        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(6)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(-50, 50)
        self.speed_slider.setValue(0)
        self.speed_slider.setSingleStep(5)
        self.speed_val_lbl = QLabel("1.00x")
        self.speed_val_lbl.setFixedWidth(56)
        self.speed_val_lbl.setAlignment(Qt.AlignCenter)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        reset_speed_btn = QPushButton()
        reset_speed_btn.setIcon(lucide_icon("rotate-ccw", "#8c909b", 13))
        reset_speed_btn.setToolTip("Reset speed to 1.00x")
        reset_speed_btn.setFixedSize(24, 24)
        reset_speed_btn.clicked.connect(lambda: self.speed_slider.setValue(0))
        speed_layout.addWidget(self.speed_slider, 1)
        speed_layout.addWidget(self.speed_val_lbl)
        speed_layout.addWidget(reset_speed_btn)
        form.addRow("Speed", speed_widget)

        # Pitch slider row
        pitch_widget = QWidget()
        pitch_layout = QHBoxLayout(pitch_widget)
        pitch_layout.setContentsMargins(0, 0, 0, 0)
        pitch_layout.setSpacing(6)
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-40, 40)
        self.pitch_slider.setValue(0)
        self.pitch_slider.setSingleStep(2)
        self.pitch_val_lbl = QLabel("0 Hz")
        self.pitch_val_lbl.setFixedWidth(56)
        self.pitch_val_lbl.setAlignment(Qt.AlignCenter)
        self.pitch_slider.valueChanged.connect(self._on_pitch_changed)
        reset_pitch_btn = QPushButton()
        reset_pitch_btn.setIcon(lucide_icon("rotate-ccw", "#8c909b", 13))
        reset_pitch_btn.setToolTip("Reset pitch to 0 Hz")
        reset_pitch_btn.setFixedSize(24, 24)
        reset_pitch_btn.clicked.connect(lambda: self.pitch_slider.setValue(0))
        pitch_layout.addWidget(self.pitch_slider, 1)
        pitch_layout.addWidget(self.pitch_val_lbl)
        pitch_layout.addWidget(reset_pitch_btn)
        form.addRow("Pitch", pitch_widget)

        # Status indicator with dynamic message
        self.status_lbl = QLabel("")
        set_ui_style(self.status_lbl, 'color: @info; font-size: 11px; font-weight: 600;')
        self.status_lbl.setVisible(False)
        form.addRow(self.status_lbl)

        # Progress bar with percentage readout
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        set_ui_style(self.progress_bar, 'QProgressBar { background: @bg_panel; border: 1px solid @border_subtle; border-radius: 4px; text-align: center; color: @text_main; font-size: 10px; font-weight: 700; }QProgressBar::chunk { background: @accent; border-radius: 3px; }')
        self.progress_bar.setVisible(False)
        outer.addWidget(self.progress_bar)

        # 4. Dialog button box
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.generate_btn = buttons.button(QDialogButtonBox.Ok)
        self.generate_btn.setText("Generate Dialogue")
        self.generate_btn.setIcon(lucide_icon("sparkles", "#11130d", 14))
        self.generate_btn.setProperty("accent", True)
        set_ui_style(self.generate_btn, 'QPushButton { background: @accent; color: @accent_text; font-weight: 700; border-radius: 4px; padding: 6px 14px; }QPushButton:hover { background: @accent; }QPushButton:disabled { background: @bg_panel; color: @text_disabled; }')
        self.cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_generate_clicked)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._update_counter()

    def _update_counter(self):
        text = self.script_edit.toPlainText().strip()
        chars = len(text)
        words = len(re.findall(r"\b\w+\b", text))
        speed_factor = 1.0 + (self.speed_slider.value() / 100.0)
        est_sec = (words / (2.4 * max(0.5, speed_factor))) if words > 0 else 0.0
        self.counter_lbl.setText(f"{chars} characters · {words} words · ~{est_sec:.1f}s")

    def _on_speed_changed(self, val: int):
        factor = 1.0 + (val / 100.0)
        prefix = f"+{val}%" if val > 0 else f"{val}%" if val < 0 else "0%"
        self.speed_val_lbl.setText(f"{factor:.2f}x ({prefix})")
        self._update_counter()

    def _on_pitch_changed(self, val: int):
        prefix = f"+{val} Hz" if val > 0 else f"{val} Hz" if val < 0 else "0 Hz"
        self.pitch_val_lbl.setText(prefix)

    def _on_player_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.preview_btn.setText("Stop preview")
            self.preview_btn.setIcon(lucide_icon("square", "#ff6b6b", 14))
        else:
            self.preview_btn.setText("Play voice preview")
            self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))

    def _cancel_preview(self):
        """Immediately stop preview playback and cancel preview synthesis."""
        if hasattr(self, "_preview_player") and self._preview_player.playbackState() == QMediaPlayer.PlayingState:
            self._preview_player.stop()

        if self._preview_worker:
            self._preview_worker.cancel()

        self._preview_thread = None
        self._preview_worker = None
        self._preview_token = None
        self.preview_btn.setText("Play voice preview")
        self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))
        if not self._is_generating:
            self.preview_btn.setEnabled(True)

    def _toggle_preview(self):
        if self._closed or self._is_generating:
            return

        if self._preview_player.playbackState() == QMediaPlayer.PlayingState:
            self._cancel_preview()
            return

        voice = self.voice_combo.currentData()
        text = self.script_edit.toPlainText().strip()
        preview_text = extract_preview_sentence(text)

        rate = self.speed_slider.value()
        pitch = self.pitch_slider.value()

        self._cancel_preview()

        self.preview_btn.setEnabled(False)
        self.preview_btn.setText("Synthesizing preview...")
        self.status_lbl.setText("Generating voice preview...")
        self.status_lbl.setVisible(True)

        parent_win = self.parent()
        ffmpeg_bin = "ffmpeg"
        if parent_win and hasattr(parent_win, "settings"):
            ffmpeg_bin = parent_win.settings.get("ffmpeg", "ffmpeg")

        worker = _PreviewWorker(preview_text, voice, rate, pitch, ffmpeg_bin=ffmpeg_bin)
        thread = RetainedThread(worker)
        self._preview_worker = worker
        self._preview_token = worker._cancel
        self._preview_thread = thread

        worker.finished.connect(self._on_preview_done, Qt.QueuedConnection)
        worker.error.connect(self._on_preview_error, Qt.QueuedConnection)
        thread.start()

    @Slot(str, object)
    def _on_preview_done(self, path: str, token=None):
        if self._closed or self._is_generating or token is not self._preview_token:
            return
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText("Stop preview")
        self.preview_btn.setIcon(lucide_icon("square", "#ff6b6b", 14))
        self.status_lbl.setVisible(False)

        self._preview_thread = None
        self._preview_worker = None

        if not self._is_generating:
            from .media_source import set_media_source
            set_media_source(self._preview_player,QUrl.fromLocalFile(path))
            self._preview_player.play()

    @Slot(str, object)
    def _on_preview_error(self, err: str, token=None):
        if self._closed or self._is_generating or token is not self._preview_token:
            return
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText("Play voice preview")
        self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))
        self.status_lbl.setVisible(False)

        self._preview_thread = None
        self._preview_worker = None

        if not self._is_generating:
            QMessageBox.warning(self, "Preview Failed", f"Could not generate voice preview:\n{err}")

    def _on_generate_clicked(self):
        if self._closed or self._is_generating:
            return
        text = self.script_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Script Required", "Please paste or type your video script before generating dialogue.")
            return

        voice = self.voice_combo.currentData()

        # Always cancel any ongoing preview immediately
        self._cancel_preview()
        self._is_generating = True

        rate = self.speed_slider.value()
        pitch = self.pitch_slider.value()

        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.preview_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("Starting dialogue generation...")
        self.status_lbl.setVisible(True)

        parent_win = self.parent()
        ffmpeg_bin = "ffmpeg"
        if parent_win and hasattr(parent_win, "settings"):
            ffmpeg_bin = parent_win.settings.get("ffmpeg", "ffmpeg")

        worker = _DialogueWorker(text, voice, rate, pitch, ffmpeg_bin=ffmpeg_bin)
        self._generation_data = {"text": text, "voice": voice, "speed": rate, "pitch": pitch}
        self._set_inputs_enabled(False)
        thread = RetainedThread(worker)
        self._generate_thread = thread
        self._generate_worker = worker
        self._generation_token = worker._cancel

        worker.progress.connect(self._on_generate_progress, Qt.QueuedConnection)
        worker.finished.connect(self._on_generate_done, Qt.QueuedConnection)
        worker.error.connect(self._on_generate_error, Qt.QueuedConnection)
        thread.start()

    @Slot(int, str, object)
    def _on_generate_progress(self, pct: int, msg: str, token=None):
        if self._closed or not self._is_generating or token is not self._generation_token:
            return
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    @Slot(str, object)
    def _on_generate_done(self, path: str, token=None):
        if self._closed or (token is not None and token is not self._generation_token):
            return
        self._is_generating = False
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.status_lbl.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)

        self._generate_thread = None
        self._generate_worker = None

        self._set_inputs_enabled(True)
        self.result_data = dict(self._generation_data or {
            "text": self.script_edit.toPlainText().strip(), "voice": self.voice_combo.currentData(),
            "speed": self.speed_slider.value(), "pitch": self.pitch_slider.value()})
        self.result_data["audio_path"] = path
        self.speechGenerated.emit(self.result_data)
        self.accept()

    @Slot(str, object)
    def _on_generate_error(self, err: str, token=None):
        if self._closed or token is not self._generation_token:
            return
        self._is_generating = False
        self.progress_bar.setVisible(False)
        self.status_lbl.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)

        self._generate_thread = None
        self._generate_worker = None
        self._set_inputs_enabled(True)

        QMessageBox.critical(self, "Generation Error", f"Failed to generate dialogue audio:\n{err}")

    def _set_inputs_enabled(self, enabled):
        self.script_edit.setReadOnly(not enabled)
        for widget in (self.voice_combo, self.speed_slider, self.pitch_slider):
            widget.setEnabled(enabled)

    def done(self, result):
        # Cancel, Escape, X and owner destruction all invalidate delivery. No
        # bounded wait can safely transfer ownership away from a live thread.
        self._closed = True
        self._cancel_preview()
        if self._generate_worker:
            self._generate_worker.cancel()
        self._generate_thread = None
        self._generate_worker = None
        self._is_generating = False
        if result != QDialog.Accepted:
            self.result_data = None
        super().done(result)
