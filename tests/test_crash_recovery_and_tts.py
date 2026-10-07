"""Tests for crash auto-recovery, timeline move crash guards, and AI Text-to-Speech (TTS)."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from kinetic_cut.config import SESSION_LOCK_PATH, AUTOSAVE_PATH, CACHE_DIR
from kinetic_cut.model import Project, TimelineItem, MediaItem, Caption, uid
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.tts import VOICES, DEFAULT_VOICE, synthesize_speech
from kinetic_cut.tts_dialog import TTSDialog


class TestCrashRecoveryAndTTS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kc_test_recovery_")
        self.lock_file = Path(self.temp_dir) / "test_session.lock"
        self.autosave_file = Path(self.temp_dir) / "recovery.kcut"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_voices_list_and_default(self):
        """Ensure viral short/tiktok voices Adam and Christopher are present and Adam is default."""
        self.assertEqual(DEFAULT_VOICE, "adam-narrator")
        voice_ids = [vid for _, vid in VOICES]
        self.assertIn("adam-narrator", voice_ids)
        self.assertIn("en-US-ChristopherNeural", voice_ids)
        self.assertIn("en-US-GuyNeural", voice_ids)
        self.assertIn("en-US-EricNeural", voice_ids)
        self.assertIn("en-US-JennyNeural", voice_ids)

    def test_tts_dialog_initialization(self):
        """TTSDialog instantiates properly with initial text and default settings."""
        dialog = TTSDialog(initial_text="Hello world from test")
        self.assertEqual(dialog.text_edit.toPlainText(), "Hello world from test")
        self.assertEqual(dialog.voice_combo.currentData(), DEFAULT_VOICE)
        self.assertEqual(dialog.speed_slider.value(), 0)
        self.assertEqual(dialog.pitch_slider.value(), 0)
        self.assertTrue(dialog.insert_timeline_chk.isChecked())
        self.assertTrue(dialog.generate_captions_chk.isChecked())
        dialog.close()

    def test_timeline_alt_drag_initialized(self):
        """TimelineWidget initializes alt_drag to False avoiding AttributeError."""
        widget = TimelineWidget()
        self.assertFalse(widget.alt_drag)
        widget.set_read_only(True)
        self.assertFalse(widget.alt_drag)
        widget.cancel_drag()
        self.assertFalse(widget.alt_drag)
        widget.close()

    def test_timeline_audio_move_into_gap_safeguards(self):
        """Moving an audio clip into a gap between two other clips on the same audio track doesn't crash."""
        widget = TimelineWidget()
        p = Project()
        p.add_track("video")
        p.add_track("audio")
        p.add_track("audio")  # audio_2

        # Create two audio clips on audio_1 with a gap in between: [0, 2] and [4, 6]
        m1 = MediaItem(id="med1", path="dummy1.mp3", kind="audio", name="Audio 1", duration=10, has_audio=True)
        p.media.append(m1)

        clip_left = TimelineItem(id="left", media_id="med1", track="audio_1", start=0.0, duration=2.0, in_point=0.0, group_id="g1")
        clip_right = TimelineItem(id="right", media_id="med1", track="audio_1", start=4.0, duration=2.0, in_point=4.0, group_id="g1")

        # Clip on audio_2: [1.0, 3.5] to be moved into the gap [2.0, 4.0]
        clip_moving = TimelineItem(id="move_me", media_id="med1", track="audio_2", start=1.0, duration=1.8, in_point=1.0, group_id="g2")

        p.timeline = [clip_left, clip_right, clip_moving]
        widget.set_project(p)

        # Simulate move drag
        widget.drag_mode = "move"
        widget.snapshots = {"move_me": clip_moving}
        # Destination: placed at start 2.1 on track audio_1 (fits in the gap without overlap or partial overlap)
        ghost = TimelineItem(id="move_me", media_id="med1", track="audio_1", start=2.1, duration=1.8, in_point=1.0, group_id="g2")
        setattr(ghost, "_drag_ghost", True)
        widget.move_preview = [ghost]
        widget.selected_id = "move_me"
        widget.selected_ids = {"move_me"}

        # Release mouse event
        class DummyEvent:
            def button(self):
                return Qt.LeftButton
            def accept(self):
                pass

        # Should execute cleanly without raising exception or crashing
        widget.mouseReleaseEvent(DummyEvent())
        self.assertEqual(widget.drag_mode, "")
        placed_clip = p.item_by_id("move_me")
        self.assertIsNotNone(placed_clip)
        self.assertEqual(placed_clip.track, "audio_1")
        self.assertAlmostEqual(placed_clip.start, 2.1, places=2)
        widget.close()

    def test_session_lock_detection_logic(self):
        """Crash is detected only if session lock exists AND autosave exists and has content."""
        # Case 1: Clean state - neither exists
        crashed = self.lock_file.exists() and self.autosave_file.exists() and self.autosave_file.stat().st_size > 50
        self.assertFalse(crashed)

        # Case 2: Autosave exists but clean shutdown removed lock file
        self.autosave_file.write_text(json.dumps({"name": "Test Project", "settings": {"width": 1080, "height": 1920}, "timeline": []}), encoding="utf-8")
        crashed = self.lock_file.exists() and self.autosave_file.exists() and self.autosave_file.stat().st_size > 50
        self.assertFalse(crashed)

        # Case 3: Session lock left behind (unclean shutdown / crash) AND autosave exists
        self.lock_file.write_text("pid=1234\n", encoding="utf-8")
        crashed = self.lock_file.exists() and self.autosave_file.exists() and self.autosave_file.stat().st_size > 50
        self.assertTrue(crashed)

    def test_synthesize_speech_validation(self):
        """synthesize_speech validates empty text properly."""
        with self.assertRaises(ValueError):
            synthesize_speech("   ")

    def test_title_item_tts_attributes_and_serialization(self):
        """TimelineItem stores TTS options and serializes/deserializes cleanly."""
        item = TimelineItem(
            id="title_1",
            media_id="",
            track="video_1",
            start=0.0,
            duration=4.0,
            role="title",
            title_text="TTS Headline",
            tts_enabled=True,
            tts_voice="en-US-ChristopherNeural",
            tts_speed=10,
            tts_pitch=-5
        )
        self.assertTrue(item.tts_enabled)
        self.assertEqual(item.tts_voice, "en-US-ChristopherNeural")
        self.assertEqual(item.tts_speed, 10)
        self.assertEqual(item.tts_pitch, -5)

        proj = Project(timeline=[item])
        raw = proj.to_dict()
        loaded_proj = Project.from_dict(raw)
        loaded_item = loaded_proj.item_by_id("title_1")
        self.assertIsNotNone(loaded_item)
        self.assertTrue(loaded_item.tts_enabled)
        self.assertEqual(loaded_item.tts_voice, "en-US-ChristopherNeural")
        self.assertEqual(loaded_item.tts_speed, 10)
        self.assertEqual(loaded_item.tts_pitch, -5)

    def test_inspector_title_tts_section(self):
        """Inspector properly displays and binds TTS options for title items."""
        from kinetic_cut.ui import MainWindow
        win = MainWindow()
        item = TimelineItem(
            id="t1",
            media_id="",
            track="video_1",
            start=0.0,
            duration=3.0,
            role="title",
            title_text="Voiceover test",
            tts_enabled=True,
            tts_voice="en-US-ChristopherNeural",
            tts_speed=5,
            tts_pitch=-2
        )
        win.project.timeline.append(item)
        win.inspector.select("t1")
        self.assertTrue(win.inspector.title_tts_enabled.isChecked())
        self.assertEqual(win.inspector.title_tts_voice.currentData(), "en-US-ChristopherNeural")
        self.assertEqual(win.inspector.title_tts_speed.spin.value(), 5)
        self.assertEqual(win.inspector.title_tts_pitch.spin.value(), -2)
        # Verify TTS section is nested within the style_content widget (text property section, after Animation)
        self.assertIs(win.inspector.title_tts_section.parentWidget(), win.inspector.style_content)
        self.assertFalse(win.inspector.title_tts_section.isHidden())

        # When non-title (e.g. caption/subtitle) is inspected, title TTS section is hidden
        win.inspector.item_id = ""
        win.inspector.relocate_style()
        self.assertTrue(win.inspector.title_tts_section.isHidden())
        win.close()

    def test_tts_dialogue_dialog_initialization_and_defaults(self):
        """TTSDialogueDialog instantiates with proper defaults, counter, and controls."""
        from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
        dialog = TTSDialogueDialog(initial_text="Welcome to this video dialogue test script.")
        self.assertEqual(dialog.windowTitle(), "Generate TTS Dialogue")
        self.assertEqual(dialog.script_edit.toPlainText(), "Welcome to this video dialogue test script.")
        self.assertEqual(dialog.voice_combo.currentData(), DEFAULT_VOICE)
        self.assertEqual(dialog.speed_slider.value(), 0)
        self.assertEqual(dialog.pitch_slider.value(), 0)
        self.assertEqual(dialog.generate_btn.text(), "Generate Dialogue")
        self.assertIn("characters", dialog.counter_lbl.text())
        self.assertIn("words", dialog.counter_lbl.text())

        # Test speed change alters label and counter duration
        dialog.speed_slider.setValue(20)
        self.assertEqual(dialog.speed_val_lbl.text(), "1.20x (+20%)")
        dialog.pitch_slider.setValue(-4)
        self.assertEqual(dialog.pitch_val_lbl.text(), "-4 Hz")

        # Test reset buttons
        dialog.speed_slider.setValue(0)
        self.assertEqual(dialog.speed_val_lbl.text(), "1.00x (0%)")
        dialog.pitch_slider.setValue(0)
        self.assertEqual(dialog.pitch_val_lbl.text(), "0 Hz")
        dialog.close()

    def test_workspace_edit_actions_tts_dialogue_button(self):
        """Verify Generate TTS Dialogue button is in w.edit_actions beside Generate Captions."""
        from kinetic_cut.ui import MainWindow
        win = MainWindow()
        action_texts = [btn.text() for btn in win.edit_actions]
        self.assertIn("Generate Captions", action_texts)
        self.assertIn("Generate TTS Dialogue", action_texts)
        captions_idx = action_texts.index("Generate Captions")
        dialogue_idx = action_texts.index("Generate TTS Dialogue")
        self.assertEqual(dialogue_idx, captions_idx + 1, "Generate TTS Dialogue must be right beside Generate Captions")
        win.close()

    def test_apply_generated_dialogue_timeline_insertion(self):
        """_apply_generated_dialogue indexes audio and inserts clip onto timeline audio track with source_audio role."""
        from kinetic_cut.ui import MainWindow
        win = MainWindow()
        win.project.playhead = 3.5

        mock_media = MediaItem(
            id="tts_dialogue_med",
            path="C:/dummy/dialogue.mp3",
            kind="audio",
            name="Dialogue Audio",
            duration=4.8,
            has_audio=True
        )

        with patch("kinetic_cut.ui.probe", return_value=mock_media), \
             patch.object(win, "request_waveform"):
            win._apply_generated_dialogue({
                "audio_path": "C:/dummy/dialogue.mp3",
                "text": "Hello and welcome to my new video."
            })

        # Check media pool
        self.assertIn(mock_media, win.project.media)
        # Check timeline insertion
        inserted = [item for item in win.project.timeline if item.media_id == mock_media.id]
        self.assertEqual(len(inserted), 1)
        item = inserted[0]
        self.assertEqual(item.track, "audio_1")
        self.assertAlmostEqual(item.start, 3.5, places=2)
        self.assertAlmostEqual(item.duration, 4.8, places=2)
        self.assertEqual(item.role, "source_audio")
        self.assertIn(item.id, win.timeline.selected_ids)
        win.close()

    def test_extract_preview_sentence(self):
        """extract_preview_sentence extracts only the first sentence for snappy preview."""
        from kinetic_cut.tts import extract_preview_sentence
        long_script = (
            "xQc has attempted some ridiculous heists in NoPixel. "
            "Before this attempt, X had already tried reaching the deepest section. "
            "Another paragraph follows."
        )
        preview = extract_preview_sentence(long_script)
        self.assertEqual(preview, "xQc has attempted some ridiculous heists in NoPixel.")

    def test_split_script_into_batches_unlimited_script(self):
        """split_script_into_batches divides large scripts into natural batches under limit."""
        from kinetic_cut.tts import split_script_into_batches
        long_text = "\n\n".join([f"This is paragraph number {i} with some descriptive words." for i in range(20)])
        batches = split_script_into_batches(long_text, max_chars=200)
        self.assertGreater(len(batches), 1)
        for b in batches:
            self.assertLessEqual(len(b), 200)

    def test_cancel_preview_on_generate(self):
        """_cancel_preview halts preview player and worker cleanly."""
        from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
        dialog = TTSDialogueDialog(initial_text="Test sentence for cancellation.")
        dialog._preview_player.play()
        dialog._cancel_preview()
        self.assertEqual(dialog.preview_btn.text(), "Play voice preview")
        dialog.close()

    def test_adam_voice_present_and_default(self):
        """Adam voice is present in VOICES and set as the default voice with zero API key required."""
        from kinetic_cut.tts import VOICES, DEFAULT_VOICE
        voice_ids = [vid for _, vid in VOICES]
        self.assertIn("adam-narrator", voice_ids)
        self.assertEqual(DEFAULT_VOICE, "adam-narrator")

        from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
        dialog = TTSDialogueDialog(initial_text="Testing Adam voice selection.")
        self.assertEqual(dialog.voice_combo.currentData(), "adam-narrator")
        dialog.close()

    def test_dialogue_generation_done_slot_unblocks_and_accepts(self):
        """_on_generate_done slot cleanly terminates thread, sets result_data, and accepts dialog."""
        from PySide6.QtWidgets import QDialog
        from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
        dialog = TTSDialogueDialog(initial_text="Script to test completion slot.")
        received = []
        dialog.speechGenerated.connect(lambda d: received.append(d))

        # Invoke completion slot directly
        dialog._on_generate_done("C:/dummy/test_completed_audio.mp3")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["audio_path"], "C:/dummy/test_completed_audio.mp3")
        self.assertEqual(dialog.result_data["audio_path"], "C:/dummy/test_completed_audio.mp3")
        self.assertEqual(dialog.result(), QDialog.Accepted)
        dialog.close()


if __name__ == "__main__":
    unittest.main()




class SpeechProviderCleanupTests(unittest.TestCase):
    def test_default_narration_keeps_processed_edge_voice_without_credentials(self):
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from kinetic_cut import tts
        calls=[]
        async def speech(text,voice,rate,pitch,target,cancel_check=None):
            calls.append((voice,rate,pitch));target.write_bytes(b'raw-edge-speech')
        def mastering(command,cancel_check):
            Path(command[-1]).write_bytes(b'mastered-adam')
        with tempfile.TemporaryDirectory() as directory,patch.object(tts,'_synthesize_async',speech),patch.object(tts,'_run_audio_process',mastering):
            result=tts.synthesize_speech('Ordinary narration',output_path=Path(directory)/'speech.mp3')
            self.assertEqual(Path(result).read_bytes(),b'mastered-adam')
        self.assertEqual(calls,[('en-US-AndrewNeural','+0%','-2Hz')])
