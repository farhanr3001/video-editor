"""File menu ends with an Exit item that closes the window through the normal close path."""
import unittest

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


class FileMenuExitTests(unittest.TestCase):
    def test_exit_is_last_item_after_a_separator_and_closes(self):
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.autosave_timer.stop()
        menu = next(a.menu() for a in w.menuBar().actions() if a.text().replace('&', '') == 'File')
        actions = menu.actions()
        self.assertEqual(actions[-1].text(), 'Exit')
        self.assertTrue(actions[-2].isSeparator())
        self.assertEqual(actions[-1].shortcut().toString(), 'Ctrl+Q')
        self.assertFalse(getattr(w, '_closing', False))
        actions[-1].trigger()
        self.assertTrue(getattr(w, '_closing', False))          # closeEvent ran: unsaved-work guard, then orderly shutdown
        app.processEvents()


class ExitToolTests(unittest.TestCase):
    def make(self, content=False):
        import time
        from kinetic_cut.model import MediaItem, Project, TimelineItem
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.autosave_timer.stop()
        project = Project(media=[MediaItem('m', 'x.mp4', 'video', 'x', 10., 320, 180, 30., True)])
        if content:
            project.timeline = [TimelineItem('v', 'm', 'video_1', 0, 5)]
        w.set_project(project)
        return w

    def settle(self, w, seconds=3):
        import time
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not getattr(w, '_closing', False):
            app.processEvents()
            time.sleep(.02)

    def test_clean_project_exits_without_a_prompt(self):
        from kinetic_cut.assistant_api import EditorAPI
        w = self.make()
        result = EditorAPI(w).call_exit_application()
        self.assertEqual((result['state'], result['discarded_unsaved']), ('closing', False))
        self.assertFalse(getattr(w, '_closing', False))                       # the close waits until the response has been sent
        self.settle(w)
        self.assertTrue(getattr(w, '_closing', False))

    def test_unsaved_work_blocks_exit_until_discard_is_explicit(self):
        from kinetic_cut.assistant_api import EditorAPI
        w = self.make(content=True)
        api = EditorAPI(w)
        with self.assertRaisesRegex(ValueError, 'unsaved changes'):
            api.call_exit_application()
        self.settle(w, .6)
        self.assertFalse(getattr(w, '_closing', False))
        self.assertFalse(getattr(w, '_exit_confirmed', False))
        result = api.call_exit_application(discard_unsaved=True)
        self.assertTrue(result['discarded_unsaved'])
        self.settle(w)
        self.assertTrue(getattr(w, '_closing', False))

    def test_render_and_argument_checks(self):
        from kinetic_cut.assistant_api import EditorAPI
        w = self.make()
        api = EditorAPI(w)
        w.delivery.running = True
        try:
            with self.assertRaisesRegex(ValueError, 'render is running'):
                api.call_exit_application()
        finally:
            w.delivery.running = False
        with self.assertRaises(ValueError):
            api.call_exit_application(discard_unsaved='yes')
        w.close()

    def test_background_probe_fields_are_not_unsaved_changes(self):
        from kinetic_cut.close_guard import document_key
        w = self.make(content=True)
        before = document_key(w.project)
        w.project.media[0].video_codec = 'h264'
        w.project.media[0].stream_durations = {'video': 10.0}
        w.project.media[0].thumbnail = 'thumb.jpg'
        self.assertEqual(document_key(w.project), before)
        w.project.media[0].name = 'renamed'
        self.assertNotEqual(document_key(w.project), before)
        w.close()


if __name__ == '__main__':
    unittest.main()
