"""Live test fetching and downloading TikTok sound link."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from kinetic_cut.downloader_dialog import MediaDownloaderDialog

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    test_url = "https://www.tiktok.com/music/dramamine-7355884225582926623"

    dialog = MediaDownloaderDialog(None)
    dialog._headless = True
    dialog.url_input.setText(test_url)
    dialog._on_url_changed(test_url)
    dialog.show()
    app.processEvents()

    print(f"Triggering fetch for: {test_url}")
    dialog._on_fetch_clicked()

    # Wait for fetch worker to finish
    loop = QEventLoop()
    if dialog._fetch_worker:
        dialog._fetch_worker.finished.connect(lambda d: (print("FETCH FINISHED:", ascii(d.get("title"))), loop.quit()))
        dialog._fetch_worker.error.connect(lambda e: (print("FETCH ERROR:", e), loop.quit()))
        QTimer.singleShot(15000, loop.quit)
        loop.exec()

    app.processEvents()
    time.sleep(0.5)
    app.processEvents()

    # Verify metadata
    print("Dialog title:", ascii(dialog.title_lbl.text()))
    print("Platform indicator:", dialog.platform_ind.text())
    print("Resolution combo:", dialog.res_combo.currentText())
    print("Format combo:", dialog.fmt_combo.currentText())
    print("btn_download_video enabled:", dialog.btn_download_video.isEnabled())
    print("btn_download_audio enabled:", dialog.btn_download_audio.isEnabled())

    assert dialog.platform_ind.text() == "TikTok Sound (MP3)", "Platform indicator should be TikTok Sound (MP3)"
    assert not dialog.btn_download_video.isEnabled(), "Video download should be disabled for sound-only link"
    assert dialog.btn_download_audio.isEnabled(), "Audio download must be enabled for sound-only link"

    # Capture dialog screenshot
    os.makedirs("build", exist_ok=True)
    pix = dialog.grab()
    pix.save("build/verify_tiktok_sound_dialog.png")
    print("Saved screenshot to build/verify_tiktok_sound_dialog.png")

    # Trigger MP3 download
    print("Triggering MP3 download...")
    dialog._start_download("audio")
    loop2 = QEventLoop()
    if dialog._download_worker:
        dialog._download_worker.finished.connect(lambda p: loop2.quit())
        dialog._download_worker.error.connect(lambda e: loop2.quit())
        QTimer.singleShot(25000, loop2.quit)
        loop2.exec()

    app.processEvents()
    time.sleep(0.5)

    downloaded_files = list(Path("assets/downloads").glob("*.mp3"))
    print(f"Downloaded files: {[f.name for f in downloaded_files]}")
    assert any("dramamine" in f.name.lower() or "tiktok" in f.name.lower() for f in downloaded_files), "Downloaded MP3 not found in assets/downloads!"

    dialog.close()
    print("TIKTOK SOUND LIVE VERIFICATION SUCCEEDED!")

if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception as e:
        with open("scratch/verify_error.log", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        print(f"Error caught: {e}", file=sys.stderr)
        sys.exit(1)
