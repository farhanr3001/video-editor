"""Visual and functional verification of Download Media button and Video Downloader dialog."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from kinetic_cut.ui import MainWindow
from kinetic_cut.downloader_dialog import MediaDownloaderDialog

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1400, 850)
    win.show()
    app.processEvents()

    # 1. Verify toolbar buttons
    action_texts = [b.text() for b in win.edit_actions]
    print(f"Edit action buttons: {action_texts}")
    assert "Download Media" in action_texts, "Download Media button missing from edit_actions!"
    assert "Vertical Layout" not in action_texts, "Vertical Layout still in edit_actions!"

    # Capture toolbar screenshot
    os.makedirs("build", exist_ok=True)
    toolbar_pix = win.grab()
    toolbar_pix.save("build/verify_downloader_toolbar.png")
    print("Saved toolbar verification screenshot to build/verify_downloader_toolbar.png")

    # 2. Test MediaDownloaderDialog
    dialog = MediaDownloaderDialog(win, initial_url="https://www.tiktok.com/@creative/video/123456789")
    dialog.show()
    app.processEvents()

    # Populate mock metadata matching the user's mock design to inspect full visual layout
    mock_meta = {
        "title": "Viral Editing Tricks That Changed TikTok in 2026",
        "duration": 88,
        "uploader": "CineMaster Pro",
        "channel_follower_count": 1_450_000,
        "view_count": 3_200_000,
        "upload_date": "20260910",
        "thumbnail": "",
        "extractor_key": "TikTok",
        "formats": [
            {"format_id": "1080p", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
            {"format_id": "720p", "height": 720, "ext": "mp4", "vcodec": "avc1"},
            {"format_id": "480p", "height": 480, "ext": "mp4", "vcodec": "avc1"}
        ]
    }
    dialog._on_metadata_loaded(mock_meta)
    app.processEvents()

    dialog_pix = dialog.grab()
    dialog_pix.save("build/verify_downloader_dialog.png")
    print("Saved downloader dialog verification screenshot to build/verify_downloader_dialog.png")

    dialog.close()
    win.close()
    print("VERIFICATION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
