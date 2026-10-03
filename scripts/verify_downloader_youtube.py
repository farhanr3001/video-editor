"""Verify MediaDownloaderDialog with YouTube Shorts without crash and clickable buttons."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from kinetic_cut.downloader_dialog import MediaDownloaderDialog

app = QApplication.instance() or QApplication([])

dialog = MediaDownloaderDialog(None)
dialog.resize(620, 720)
dialog.show()

# Set YouTube short URL
test_url = "https://www.youtube.com/shorts/mM5nw5Ljags"
dialog.url_input.setText(test_url)

# Trigger fetch
dialog._on_fetch_clicked()

# Process events until metadata loads or timeout
start_t = time.time()
while time.time() - start_t < 15:
    app.processEvents()
    time.sleep(0.05)
    if dialog.btn_download_video.isEnabled() and dialog.title_lbl.text() not in ("", "Loading..."):
        break

for _ in range(20):
    time.sleep(0.05)
    app.processEvents()

# Save screenshot of dialog
out_img = Path("build/verify_youtube_shorts_fixed.png")
out_img.parent.mkdir(parents=True, exist_ok=True)
pixmap = dialog.grab()
pixmap.save(str(out_img))
print(f"Captured screenshot to: {out_img}")
print(f"Title: {dialog.title_lbl.text().encode('ascii', 'replace').decode()}")
print(f"Platform: {dialog.platform_ind.text()}")
print(f"Download Video enabled: {dialog.btn_download_video.isEnabled()}")
print(f"Download MP3 enabled: {dialog.btn_download_audio.isEnabled()}")

assert dialog.btn_download_video.isEnabled(), "Download Video button must be enabled!"
assert dialog.btn_download_audio.isEnabled(), "Download MP3 button must be enabled!"
assert dialog.title_lbl.text() != "", "Title must be loaded!"
print("VERIFICATION_SUCCESSFUL")
dialog.close()
