"""Unit tests for MediaDownloaderDialog and toolbar Download Media button."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from kinetic_cut.model import Project
from kinetic_cut.ui import MainWindow
from kinetic_cut.downloader_dialog import (
    MediaDownloaderDialog,
    format_duration,
    format_views,
    format_subscribers,
    format_upload_date,
    detect_platform,
    video_download_format,
)

app = QApplication.instance() or QApplication([])


class MediaDownloaderDialogTests(unittest.TestCase):
    def test_video_download_prefers_edit_friendly_codec_without_dropping_size(self):
        selector, sorting = video_download_format("1920x1080")
        self.assertIn("height<=1080", selector)
        self.assertEqual(sorting, "res,fps,hdr,vcodec:avc")
        self.assertIn("bestvideo[ext=mp4]", video_download_format()[0])

    def test_completed_download_emits_one_import_request(self):
        dialog = MediaDownloaderDialog(None)
        dialog._headless = True
        received = []
        dialog.mediaDownloaded.connect(received.append)
        dialog._on_download_finished("clip.mp4")
        self.assertEqual(received, ["clip.mp4"])
        dialog.deleteLater()

    def test_formatting_utilities(self):
        self.assertEqual(format_duration(88), "01:28")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_duration(0), "00:00")

        self.assertEqual(format_views(1_250_000), "1.2M views")
        self.assertEqual(format_views(45_000), "45.0K views")
        self.assertEqual(format_views(320), "320 views")

        self.assertEqual(format_subscribers(10_200_000), "10.2M subscribers")
        self.assertEqual(format_subscribers(4_500), "4.5K subscribers")

    def test_detect_platform_from_url(self):
        self.assertEqual(detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "youtube")
        self.assertEqual(detect_platform("https://youtu.be/dQw4w9WgXcQ"), "youtube")
        self.assertEqual(detect_platform("https://www.tiktok.com/@user/video/1234567"), "tiktok")
        self.assertEqual(detect_platform("https://www.instagram.com/reel/C12345/"), "instagram")
        self.assertEqual(detect_platform("https://twitter.com/user/status/1234567"), "twitter")
        self.assertEqual(detect_platform("https://x.com/user/status/1234567"), "twitter")
        self.assertEqual(detect_platform("https://example.com/video.mp4"), "generic")

    def test_dialog_ui_initialization(self):
        dialog = MediaDownloaderDialog(None)
        self.assertIn("Video Downloader", dialog.windowTitle())

        # Check key UI controls exist
        self.assertIsNotNone(dialog.url_input)
        self.assertIsNotNone(dialog.fetch_btn)
        self.assertIsNotNone(dialog.card)
        self.assertIsNotNone(dialog.btn_download_video)
        self.assertIsNotNone(dialog.btn_download_audio)
        self.assertIsNotNone(dialog.res_combo)
        self.assertIsNotNone(dialog.fmt_combo)

        # Action buttons initially disabled
        self.assertFalse(dialog.btn_download_video.isEnabled())
        self.assertFalse(dialog.btn_download_audio.isEnabled())

        # Card container exists
        self.assertIsNotNone(dialog.card)
        dialog.deleteLater()

    def test_dialog_url_auto_platform_selection(self):
        dialog = MediaDownloaderDialog(None)
        dialog.url_input.setText("https://www.tiktok.com/@creator/video/987654321")
        self.assertEqual(dialog.active_platform, "tiktok")
        self.assertTrue(dialog.platform_buttons["tiktok"].isChecked())

        dialog.url_input.setText("https://x.com/tech/status/11223344")
        self.assertEqual(dialog.active_platform, "twitter")
        self.assertTrue(dialog.platform_buttons["twitter"].isChecked())
        dialog.deleteLater()

    def test_dialog_metadata_population(self):
        dialog = MediaDownloaderDialog(None)
        sample_meta = {
            "title": "Insane Coding Montage 2026",
            "duration": 75,
            "uploader": "DevLife",
            "view_count": 250_000,
            "channel_follower_count": 120_000,
            "upload_date": "20260901",
            "thumbnail": "",
            "extractor_key": "Youtube",
            "formats": [
                {"format_id": "137", "height": 1080, "ext": "mp4", "vcodec": "avc1"},
                {"format_id": "136", "height": 720, "ext": "mp4", "vcodec": "avc1"}
            ]
        }
        dialog._on_metadata_loaded(sample_meta)
        self.assertFalse(dialog.card.isHidden())
        self.assertEqual(dialog.title_lbl.text(), "Insane Coding Montage 2026")
        self.assertEqual(dialog.author_lbl.text(), "DevLife")
        self.assertEqual(dialog.dur_badge.text(), "01:15")
        self.assertTrue(dialog.btn_download_video.isEnabled())
        self.assertTrue(dialog.btn_download_audio.isEnabled())
        dialog.deleteLater()

    def test_tiktok_sound_recognition_and_ui_state(self):
        from kinetic_cut.downloader_dialog import is_tiktok_sound_url

        self.assertTrue(is_tiktok_sound_url("https://www.tiktok.com/music/dramamine-7355884225582926623"))
        self.assertTrue(is_tiktok_sound_url("https://www.tiktok.com/music/original-sound-123456"))
        self.assertFalse(is_tiktok_sound_url("https://www.tiktok.com/@creator/video/987654321"))
        self.assertFalse(is_tiktok_sound_url("https://youtube.com/shorts/12345"))

        dialog = MediaDownloaderDialog(None)
        sound_meta = {
            "title": "dramamine",
            "uploader": "TikTok Sound",
            "duration": None,
            "thumbnail": "",
            "extractor_key": "TikTokSound",
            "platform": "tiktok",
            "is_sound_only": True,
            "audio_url": "https://example.com/sound.mp3",
            "formats": [{"format_id": "mp3", "ext": "mp3"}]
        }
        dialog._on_metadata_loaded(sound_meta)
        self.assertFalse(dialog.card.isHidden())
        self.assertEqual(dialog.title_lbl.text(), "dramamine")
        self.assertEqual(dialog.platform_ind.text(), "TikTok Sound (MP3)")
        self.assertEqual(dialog.res_combo.currentText(), "N/A (Audio Only)")
        self.assertEqual(dialog.fmt_combo.currentText(), "MP3 (Audio Only)")

        # Download Video should be disabled, Download MP3 enabled
        self.assertFalse(dialog.btn_download_video.isEnabled())
        self.assertTrue(dialog.btn_download_audio.isEnabled())
        self.assertEqual(dialog.btn_download_audio.property("primarySound"), True)
        dialog.deleteLater()

    def test_youtube_bot_challenge_fallback(self):
        from kinetic_cut.downloader_dialog import _FetchMetadataWorker
        worker = _FetchMetadataWorker("https://www.youtube.com/shorts/test123")
        # Unit-test the fallback, not this PC's installed Node/browser/cookie paths.
        with patch("subprocess.run") as mock_run, patch("kinetic_cut.downloader_dialog.fetch_youtube_oembed") as mock_oembed, patch("kinetic_cut.downloader_dialog.get_ytdlp_runtime_args", return_value=[]):
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""
            mock_proc.stderr = "ERROR: [youtube] Sign in to confirm you're not a bot."
            mock_run.return_value = mock_proc

            mock_oembed.return_value = {
                "title": "Fallback Short Title",
                "uploader": "Fallback Creator",
                "thumbnail": "https://example.com/thumb.jpg",
                "extractor_key": "Youtube",
                "duration": 45
            }

            captured = []
            worker.finished.connect(lambda d: captured.append(d))
            worker.run()

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["title"], "Fallback Short Title")
            self.assertTrue(captured[0].get("needs_cookies"))
            self.assertIn("bot check", captured[0].get("bot_warning", "").lower())

    def test_youtube_oembed_none_duration_does_not_crash(self):
        dialog = MediaDownloaderDialog(None)
        dialog.url_input.setText("https://www.youtube.com/shorts/mM5nw5Ljags")
        oembed_data = {
            "title": "Funny Short",
            "uploader": "YouTube Shorts",
            "duration": None,
            "thumbnail": "",
            "extractor_key": "Youtube",
            "platform": "youtube",
            "is_sound_only": False,
            "needs_cookies": True,
            "formats": [{"format_id": "best", "ext": "mp4", "height": 1080}]
        }
        # Calling _on_metadata_loaded must not throw TypeError: '<=' not supported between instances of 'NoneType' and 'int'
        dialog._on_metadata_loaded(oembed_data)
        self.assertEqual(dialog.title_lbl.text(), "Funny Short")
        self.assertEqual(dialog.platform_ind.text(), "YouTube Shorts")
        self.assertTrue(dialog.btn_download_video.isEnabled())
        self.assertTrue(dialog.btn_download_audio.isEnabled())
        dialog.deleteLater()

    def test_fetch_error_enables_download_buttons_and_sets_fallback(self):
        dialog = MediaDownloaderDialog(None)
        dialog.url_input.setText("https://www.youtube.com/shorts/test_error")
        dialog._on_fetch_error("Connection timed out")
        self.assertTrue(dialog.btn_download_video.isEnabled())
        self.assertTrue(dialog.btn_download_audio.isEnabled())
        self.assertIn("1080 × 1920", dialog.res_combo.currentText())
        dialog.deleteLater()

    def test_url_input_immediately_enables_download_buttons(self):
        dialog = MediaDownloaderDialog(None)
        self.assertFalse(dialog.btn_download_video.isEnabled())
        self.assertFalse(dialog.btn_download_audio.isEnabled())
        dialog.url_input.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(dialog.btn_download_video.isEnabled())
        self.assertTrue(dialog.btn_download_audio.isEnabled())
        dialog.deleteLater()


class WorkspaceToolbarActionTests(unittest.TestCase):
    def test_download_media_button_replaces_vertical_layout(self):
        win = MainWindow()
        action_texts = [b.text() for b in win.edit_actions]
        # Must have "Download Media"
        self.assertIn("Download Media", action_texts)
        # Must NOT have "Vertical Layout"
        self.assertNotIn("Vertical Layout", action_texts)

        # Find the button and verify its callback
        btn = next(b for b in win.edit_actions if b.text() == "Download Media")
        self.assertTrue(hasattr(win, "open_media_downloader"))
        self.assertTrue(hasattr(win, "import_media_files"))
        self.assertTrue(hasattr(win, "download_media"))
        win.close()

    def test_main_window_download_media_method(self):
        win = MainWindow()
        with patch("kinetic_cut.downloader_dialog.download_media_synchronous") as mock_dl:
            mock_dl.return_value = {
                "path": "test_video.mp4",
                "name": "test_video.mp4",
                "title": "Test Video",
                "mode": "video",
                "size_bytes": 2048
            }
            res = win.download_media("https://www.youtube.com/watch?v=12345", auto_import=False)
            self.assertEqual(res["path"], "test_video.mp4")
            self.assertEqual(res["name"], "test_video.mp4")
            self.assertEqual(res["mode"], "video")
            self.assertFalse(res["imported"])
        win.close()


if __name__ == "__main__":
    unittest.main()
