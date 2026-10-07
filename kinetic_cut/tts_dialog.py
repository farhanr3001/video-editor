"""AI Text-to-Speech dialog for generating viral Shorts & TikTok voiceovers."""
from __future__ import annotations

from .theme_widgets import set_ui_style, set_ui_icon
import math
import os
import re
from threading import Event
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QThread, QObject, Slot
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QSlider, QPushButton, QCheckBox, QGroupBox, QFormLayout,
    QProgressBar, QMessageBox, QWidget, QFrame, QDialogButtonBox
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .config import CACHE_DIR
from .controls import SafeComboBox
from .dialog_jobs import RetainedThread
from .icons import lucide_icon
from .tts import VOICES, DEFAULT_VOICE, synthesize_speech


class _SynthesisWorker(QObject):
    finished = Signal(str, object)
    error = Signal(str, object)
    settled = Signal()

    def __init__(self, text: str, voice: str, rate: int, pitch: int, output_path: str = "", ffmpeg_bin: str = "ffmpeg"):
        super().__init__()
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.output_path = output_path
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
                output_path=self.output_path,
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


class TTSDialog(QDialog):
    """Modern dialog for synthesizing speech with curated viral AI voices."""

    speechGenerated = Signal(dict)

    def __init__(self, parent=None, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("AI Text to Speech · Viral Voice Generator")
        self.setMinimumWidth(560)
        self.resize(580, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._preview_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._preview_player.setAudioOutput(self._audio_output)
        self._preview_player.playbackStateChanged.connect(self._on_player_state_changed)

        self._active_thread: RetainedThread | None = None
        self._active_worker: _SynthesisWorker | None = None
        self._preview_thread = None
        self._preview_worker = None
        self._is_generating = False
        self._closed = False
        self._generation_data = None
        self._preview_token = None
        self._generation_token = None
        self.generated_data: dict | None = None

        self._build_ui(initial_text)

    def _build_ui(self, initial_text: str):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(18, 16, 18, 16)

        # Header
        header = QHBoxLayout()
        icon_lbl = QLabel()
        set_ui_icon(icon_lbl, 'sparkles', '#62d0ff', 26)
        header.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_lbl = QLabel("AI Voiceover Generator")
        set_ui_style(title_lbl, 'font-size: 15px; font-weight: 700; color: @text_main;')
        sub_lbl = QLabel("Create viral TikTok & Shorts narrator voices with synced captions")
        set_ui_style(sub_lbl, 'font-size: 11px; color: @text_sub;')
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

        # Text Input Area
        text_group = QGroupBox("Script / Narration Text")
        text_layout = QVBoxLayout(text_group)
        text_layout.setContentsMargins(10, 10, 10, 10)
        text_layout.setSpacing(6)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Type or paste what you want the AI narrator to say...")
        set_ui_style(self.text_edit, "QTextEdit { background: @bg_input; border: 1px solid @border_subtle; border-radius: 6px; padding: 8px; color: @text_main; font-size: 13px; font-family: 'Segoe UI', sans-serif; }QTextEdit:focus { border: 1px solid @accent; }")
        self.text_edit.setMinimumHeight(120)
        if initial_text:
            self.text_edit.setPlainText(initial_text)
        self.text_edit.textChanged.connect(self._update_counter)
        text_layout.addWidget(self.text_edit)

        counter_layout = QHBoxLayout()
        self.counter_lbl = QLabel("0 characters · 0 words · ~0.0s")
        set_ui_style(self.counter_lbl, 'font-size: 11px; color: @text_sub;')
        counter_layout.addWidget(self.counter_lbl)
        counter_layout.addStretch()
        text_layout.addLayout(counter_layout)

        root.addWidget(text_group)

        # Voice Options Area
        voice_group = QGroupBox("Voice & Delivery")
        voice_layout = QFormLayout(voice_group)
        voice_layout.setContentsMargins(10, 10, 10, 10)
        voice_layout.setSpacing(10)

        self.voice_combo = SafeComboBox()
        for display_name, voice_id in VOICES:
            self.voice_combo.addItem(display_name, voice_id)
        # Select default
        idx = next((i for i, (_, vid) in enumerate(VOICES) if vid == DEFAULT_VOICE), 0)
        self.voice_combo.setCurrentIndex(idx)
        set_ui_style(self.voice_combo, 'QComboBox { min-height: 28px; font-size: 12px; }')
        voice_layout.addRow("Narrator Voice:", self.voice_combo)

        # Speed / Rate slider
        speed_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(-50, 50)
        self.speed_slider.setValue(0)
        self.speed_slider.setSingleStep(5)
        self.speed_val_lbl = QLabel("1.00x (Normal)")
        self.speed_val_lbl.setFixedWidth(85)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        reset_speed_btn = QPushButton()
        reset_speed_btn.setIcon(lucide_icon("rotate-ccw", "#8c909b", 13))
        reset_speed_btn.setToolTip("Reset speed to 1.0x")
        reset_speed_btn.setFixedSize(24, 24)
        reset_speed_btn.clicked.connect(lambda: self.speed_slider.setValue(0))
        speed_row.addWidget(self.speed_slider)
        speed_row.addWidget(self.speed_val_lbl)
        speed_row.addWidget(reset_speed_btn)
        voice_layout.addRow("Speaking Speed:", speed_row)

        # Pitch slider
        pitch_row = QHBoxLayout()
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-40, 40)
        self.pitch_slider.setValue(0)
        self.pitch_slider.setSingleStep(2)
        self.pitch_val_lbl = QLabel("0 Hz (Normal)")
        self.pitch_val_lbl.setFixedWidth(85)
        self.pitch_slider.valueChanged.connect(self._on_pitch_changed)
        reset_pitch_btn = QPushButton()
        reset_pitch_btn.setIcon(lucide_icon("rotate-ccw", "#8c909b", 13))
        reset_pitch_btn.setToolTip("Reset pitch to default")
        reset_pitch_btn.setFixedSize(24, 24)
        reset_pitch_btn.clicked.connect(lambda: self.pitch_slider.setValue(0))
        pitch_row.addWidget(self.pitch_slider)
        pitch_row.addWidget(self.pitch_val_lbl)
        pitch_row.addWidget(reset_pitch_btn)
        voice_layout.addRow("Voice Pitch:", pitch_row)

        # Preview Button Row
        preview_row = QHBoxLayout()
        self.preview_btn = QPushButton(" Preview Voice")
        self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))
        self.preview_btn.setFixedHeight(30)
        self.preview_btn.clicked.connect(self._toggle_preview)
        preview_row.addWidget(self.preview_btn)
        preview_row.addStretch()
        voice_layout.addRow("", preview_row)

        root.addWidget(voice_group)

        # Placement & Timeline Options
        dest_group = QGroupBox("Timeline Insertion")
        dest_layout = QVBoxLayout(dest_group)
        dest_layout.setContentsMargins(10, 8, 10, 8)
        dest_layout.setSpacing(6)

        self.insert_timeline_chk = QCheckBox("Insert voiceover clip directly to timeline at playhead")
        self.insert_timeline_chk.setChecked(True)
        dest_layout.addWidget(self.insert_timeline_chk)

        track_row = QHBoxLayout()
        track_row.setContentsMargins(20, 0, 0, 0)
        track_lbl = QLabel("Destination track:")
        set_ui_style(track_lbl, 'color: @text_sub;')
        self.track_combo = SafeComboBox()
        self.track_combo.addItem("Auto (First Available Audio Track)", "auto")
        # Populate available tracks if parent window has project
        parent_win = self.parent()
        if parent_win and hasattr(parent_win, "project") and parent_win.project:
            for t in parent_win.project.audio_tracks:
                name = parent_win.project.track_names.get(t, t.replace("_", " ").title())
                self.track_combo.addItem(name, t)
        track_row.addWidget(track_lbl)
        track_row.addWidget(self.track_combo)
        track_row.addStretch()
        dest_layout.addLayout(track_row)

        self.generate_captions_chk = QCheckBox("Generate synchronized captions on Subtitle track")
        self.generate_captions_chk.setChecked(True)
        dest_layout.addWidget(self.generate_captions_chk)

        root.addWidget(dest_group)

        # Progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        set_ui_style(self.status_lbl, 'color: @info; font-size: 11px;')
        self.status_lbl.setVisible(False)
        root.addWidget(self.status_lbl)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(self.cancel_btn)

        self.generate_btn = QPushButton(" Generate Voiceover")
        self.generate_btn.setIcon(lucide_icon("sparkles", "#11130d", 15))
        self.generate_btn.setFixedHeight(34)
        set_ui_style(self.generate_btn, 'QPushButton { background: @accent; color: @accent_text; font-weight: 700; border-radius: 5px; padding: 0 16px; font-size: 12px; }QPushButton:hover { background: @accent; }QPushButton:disabled { background: @bg_panel; color: @text_disabled; }')
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        btn_box.addWidget(self.generate_btn)

        root.addLayout(btn_box)

        self._update_counter()

    def _update_counter(self):
        text = self.text_edit.toPlainText().strip()
        chars = len(text)
        words = len(re.findall(r"\b\w+\b", text))
        # Average English speech rate is ~140-150 words per minute (2.4 words/sec)
        speed_factor = 1.0 + (self.speed_slider.value() / 100.0)
        est_sec = (words / (2.4 * max(0.5, speed_factor))) if words > 0 else 0.0
        self.counter_lbl.setText(f"{chars} characters · {words} words · ~{est_sec:.1f}s duration")

    def _on_speed_changed(self, val: int):
        factor = 1.0 + (val / 100.0)
        prefix = f"+{val}%" if val > 0 else f"{val}%" if val < 0 else "Normal"
        self.speed_val_lbl.setText(f"{factor:.2f}x ({prefix})")
        self._update_counter()

    def _on_pitch_changed(self, val: int):
        prefix = f"+{val} Hz" if val > 0 else f"{val} Hz" if val < 0 else "Normal"
        self.pitch_val_lbl.setText(f"{prefix}")

    def _on_player_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.preview_btn.setText(" Stop")
            self.preview_btn.setIcon(lucide_icon("square", "#ff6b6b", 14))
        else:
            self.preview_btn.setText(" Preview Voice")
            self.preview_btn.setIcon(lucide_icon("play", "#ffffff", 14))

    def _toggle_preview(self):
        if self._closed or self._is_generating:
            return
        if self._preview_player.playbackState() == QMediaPlayer.PlayingState:
            self._cancel_preview()
            return

        text = self.text_edit.toPlainText().strip()
        if not text:
            # Fallback preview sentence if empty
            text = "Welcome back! In today's video, we are looking at something incredible."

        # Take at most the first 160 characters for a fast snappy preview
        preview_text = text[:160]
        voice = self.voice_combo.currentData()
        rate = self.speed_slider.value()
        pitch = self.pitch_slider.value()

        self.preview_btn.setEnabled(False)
        self.preview_btn.setText(" Synthesizing...")
        self.status_lbl.setText("Generating audio preview...")
        self.status_lbl.setVisible(True)

        self._cancel_preview()
        self.preview_btn.setEnabled(False)
        self.preview_btn.setText(" Synthesizing...")
        worker = _SynthesisWorker(preview_text, voice, rate, pitch, ffmpeg_bin=self._ffmpeg())
        thread = RetainedThread(worker)
        self._preview_worker = worker
        self._preview_token = worker._cancel
        self._preview_thread = thread
        worker.finished.connect(self._on_preview_done, Qt.QueuedConnection)
        worker.error.connect(self._on_preview_error, Qt.QueuedConnection)
        thread.start()

    def _ffmpeg(self):
        return getattr(self.parent(), "settings", {}).get("ffmpeg", "ffmpeg")

    def _cancel_preview(self):
        self._preview_player.stop()
        if self._preview_worker:
            self._preview_worker.cancel()
        self._preview_worker = None
        self._preview_token = None
        self._preview_thread = None
        self.preview_btn.setText(" Preview Voice")
        self.preview_btn.setEnabled(not self._is_generating)

    @Slot(str, object)
    def _on_preview_done(self, path, token=None):
        if self._closed or self._is_generating or token is not self._preview_token:
            return
        self._preview_worker = None
        self._preview_thread = None
        self.preview_btn.setEnabled(True)
        self.status_lbl.setVisible(False)
        from .media_source import set_media_source
        set_media_source(self._preview_player, QUrl.fromLocalFile(path))
        self._preview_player.play()

    @Slot(str, object)
    def _on_preview_error(self, err, token=None):
        if self._closed or self._is_generating or token is not self._preview_token:
            return
        self._preview_worker = None
        self._preview_thread = None
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText(" Preview Voice")
        self.status_lbl.setVisible(False)
        QMessageBox.warning(self, "Preview Failed", f"Could not generate voice preview:\n{err}")

    def _on_generate_clicked(self):
        if self._closed or self._is_generating:
            return
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "No Text", "Please enter narration text to synthesize.")
            return

        voice = self.voice_combo.currentData()
        rate = self.speed_slider.value()
        pitch = self.pitch_slider.value()

        self._cancel_preview()
        self._is_generating = True
        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.preview_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_lbl.setText("Synthesizing full voiceover with AI...")
        self.status_lbl.setVisible(True)

        self._generation_data = {
            "text": text, "voice": voice,
            "insert_timeline": self.insert_timeline_chk.isChecked(),
            "destination_track": self.track_combo.currentData(),
            "generate_captions": self.generate_captions_chk.isChecked(),
        }
        self._set_inputs_enabled(False)
        worker = _SynthesisWorker(text, voice, rate, pitch, ffmpeg_bin=self._ffmpeg())
        thread = RetainedThread(worker)
        self._active_thread = thread
        self._active_worker = worker
        self._generation_token = worker._cancel

        worker.finished.connect(self._on_generate_done, Qt.QueuedConnection)
        worker.error.connect(self._on_generate_error, Qt.QueuedConnection)
        thread.start()

    @Slot(str, object)
    def _on_generate_done(self, path, token=None):
        if self._closed or token is not self._generation_token:
            return
        self._active_thread = None
        self._active_worker = None
        self._is_generating = False
        self.generated_data = dict(self._generation_data)
        self.generated_data["audio_path"] = path
        self.speechGenerated.emit(self.generated_data)
        self.accept()

    @Slot(str, object)
    def _on_generate_error(self, err, token=None):
        if self._closed or token is not self._generation_token:
            return
        self._active_thread = None
        self._active_worker = None
        self._is_generating = False
        self.progress_bar.setVisible(False)
        self.status_lbl.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self._set_inputs_enabled(True)
        QMessageBox.critical(self, "Synthesis Error", f"Failed to generate speech:\n{err}")

    def _set_inputs_enabled(self, enabled):
        self.text_edit.setReadOnly(not enabled)
        for widget in (self.voice_combo, self.speed_slider, self.pitch_slider,
                       self.insert_timeline_chk, self.track_combo, self.generate_captions_chk):
            widget.setEnabled(enabled)

    def done(self, result):
        self._closed = True
        self._cancel_preview()
        if self._active_worker:
            self._active_worker.cancel()
        self._active_worker = None
        self._active_thread = None
        self._is_generating = False
        if result != QDialog.Accepted:
            self.generated_data = None
        super().done(result)
