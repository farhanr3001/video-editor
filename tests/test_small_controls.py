import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QGuiApplication
from kinetic_cut.small_controls import PanelSearch, CopyTimecodeLabel


class SmallControlsTests(unittest.TestCase):
    def test_search_escape_and_toggle_clear_hidden_filter(self):
        search = PanelSearch(); search.hide()
        closed = []; search.dismissed.connect(lambda:closed.append(True))
        search.toggle(); search.setText('blur')
        self.assertTrue(search.isClearButtonEnabled())
        QTest.keyClick(search, Qt.Key_Escape)
        self.assertTrue(search.isHidden()); self.assertEqual(search.text(), '')
        search.toggle(); search.setText('video'); search.toggle()
        self.assertTrue(search.isHidden()); self.assertEqual(search.text(), '')
        self.assertEqual(len(closed), 2); search.deleteLater()

    def test_copy_values_frozen_at_menu_open(self):
        clipboard = QGuiApplication.clipboard(); original = clipboard.text()
        seconds = [12.3456]
        label = CopyTimecodeLabel('00:00:12:20', lambda:seconds[0])
        menu = label.copy_menu()
        try:
            label.setText('00:00:13:00'); seconds[0] = 13
            menu.actions()[0].trigger(); self.assertEqual(clipboard.text(), '00:00:12:20')
            menu.actions()[1].trigger(); self.assertEqual(clipboard.text(), '12.346')
        finally:
            clipboard.setText(original); menu.deleteLater(); label.deleteLater()
