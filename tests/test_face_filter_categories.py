"""Face-filter browser grouping must not alter effect identity or project data."""
import unittest

from PySide6.QtCore import Qt

from kinetic_cut.effects import CATALOG,FACE_FILTER_SUBSECTIONS
from kinetic_cut.ui import MainWindow


class FaceFilterCategoryTests(unittest.TestCase):
    def test_all_filters_are_grouped_once_and_remain_draggable(self):
        grouped=[name for members in FACE_FILTER_SUBSECTIONS.values() for name in members]
        self.assertEqual(set(grouped),set(CATALOG['Face Filters']))
        self.assertEqual(len(grouped),len(set(grouped)))
        window=MainWindow()
        window.autosave_timer.stop()
        try:
            browser=window.effects_panel
            choices=[browser.categories.item(i).text() for i in range(browser.categories.count())]
            browser.categories.setCurrentRow(choices.index('Face Filters'))
            headings=[]
            entries=[]
            for row in range(browser.list.count()):
                item=browser.list.item(row)
                identity=item.data(Qt.UserRole)
                (entries if identity else headings).append(item.text())
            self.assertEqual(headings,list(FACE_FILTER_SUBSECTIONS))
            self.assertEqual(entries,grouped)
            browser.search.setText('glasses')
            self.assertEqual([browser.list.item(i).text() for i in range(browser.list.count())],
                             ['Glasses','AR Pixel Glasses'])
        finally:
            window.close()


if __name__=='__main__':
    unittest.main()
