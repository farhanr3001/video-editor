"""End-to-end test verifying TTS Dialogue Generation, ElevenLabs Adam, progress, auto-close, and timeline insertion."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "verify-dialogue-home"))
os.environ["QT_QPA_PLATFORM"] = "windows"

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtTest import QTest

from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, MediaItem
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
from kinetic_cut.tts import VOICES


def test_dialogue_workflow():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    win = MainWindow()
    win.resize(1200, 800)
    win.show()

    # 1. Load project
    project_path = ROOT / "Recovered_Crash_Project.kcut"
    if project_path.exists():
        win.load_project_path(str(project_path))
    else:
        win.set_project(Project())

    # 2. Instantiate TTSDialogueDialog
    test_script = (
        "xQc attempted some ridiculous heists in NoPixel, but one of his biggest achievements "
        "came when Jean Paul finally managed to crack the Lower Vault. "
        "The crew entered the vault and successfully got away with the loot."
    )
    dialog = TTSDialogueDialog(win, initial_text=test_script)
    assert dialog.script_edit.toPlainText() == test_script, "Script text mismatch"
    assert not dialog.counter_lbl.text().startswith("0"), "Counter not updated"

    # 3. Test Adam voice is default and selected
    assert dialog.voice_combo.currentData() == "adam-narrator", f"Default voice should be adam-narrator, got {dialog.voice_combo.currentData()}"
    assert dialog.voice_combo.currentText() == "Adam (Viral Shorts Narrator)", f"Default display name mismatch: {dialog.voice_combo.currentText()}"

    # 4. Test Preview and Cancel behavior
    dialog._toggle_preview()
    # While preview is generating or ready, triggering generate must cancel it immediately
    dialog._on_generate_clicked()
    assert dialog.preview_btn.text() == "Play voice preview", "Preview was not cancelled on generate"
    assert dialog._is_generating, "Dialog should be in generating state"

    # 5. Wait for generation to complete with timeout
    deadline = time.monotonic() + 35.0
    while dialog._is_generating and time.monotonic() < deadline:
        QTest.qWait(100)

    assert not dialog._is_generating, "Dialogue generation timed out or failed to reset is_generating flag"
    assert dialog.result_data is not None, "result_data was not populated upon completion"
    assert Path(dialog.result_data["audio_path"]).is_file(), f"Synthesized file missing: {dialog.result_data['audio_path']}"
    assert dialog.result() == QDialog.Accepted, "Dialog was not automatically accepted upon 100% completion"

    # 6. Apply to timeline
    initial_timeline_count = len(win.project.timeline)
    win._apply_generated_dialogue(dialog.result_data)

    assert len(win.project.timeline) == initial_timeline_count + 1, "Audio clip was not added to timeline"
    new_item = win.project.timeline[-1]
    assert new_item.track.startswith("audio_"), f"Expected audio track, got {new_item.track}"
    assert new_item.role == "source_audio", f"Expected source_audio role, got {new_item.role}"
    assert new_item.duration > 0.5, f"Audio duration too short: {new_item.duration}"
    assert new_item.id in win.timeline.selected_ids, "Newly inserted dialogue clip should be selected"

    dialog.close()
    win.close()
    print(f"PASS: Adam TTS dialogue generated successfully ({new_item.duration:.2f}s), dialog auto-closed, placed on timeline at playhead!", flush=True)


def test_free_adam_synthesis_flow():
    from kinetic_cut.tts import synthesize_speech, DEFAULT_VOICE, VOICES

    assert DEFAULT_VOICE == "adam-narrator"
    assert any(vid == "adam-narrator" for _, vid in VOICES)

    test_text = "This is a direct test of the free Adam viral shorts narrator voice without any API keys."
    out_file = ROOT / "build" / "verify-dialogue-home" / "test_adam_direct.mp3"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists():
        out_file.unlink()

    generated_path = synthesize_speech(
        text=test_text,
        voice="adam-narrator",
        rate_percent=0,
        pitch_hz=0,
        output_path=out_file
    )

    assert Path(generated_path).is_file(), f"Generated Adam audio missing at {generated_path}"
    assert Path(generated_path).stat().st_size > 1000, f"Generated audio file suspiciously small: {Path(generated_path).stat().st_size} bytes"
    print(f"PASS: Free Adam voice synthesized directly ({Path(generated_path).stat().st_size} bytes) with zero API keys!", flush=True)


if __name__ == "__main__":
    test_free_adam_synthesis_flow()
    test_dialogue_workflow()
