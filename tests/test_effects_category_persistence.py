import unittest

from PySide6.QtWidgets import QApplication

from kinetic_cut.config import load_settings, save_settings
from kinetic_cut.ui import MainWindow


class EffectsCategoryPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_category_survives_relaunch_without_changing_project(self):
        first=MainWindow()
        try:
            names=[first.effects_panel.categories.item(i).text() for i in range(first.effects_panel.categories.count())]
            first.effects_panel.categories.setCurrentRow(names.index('Open FX / Blur'))
            self.assertEqual(first.settings['effects_category'],'Open FX / Blur')
            self.assertEqual(load_settings()['effects_category'],'Open FX / Blur')
        finally:first.close()
        second=MainWindow()
        try:
            self.assertEqual(second.effects_panel.categories.currentItem().text(),'Open FX / Blur')
            self.assertEqual(second.effects_panel.list.count(),1)
            self.assertEqual(second.effects_panel.list.item(0).text(),'Gaussian Blur')
        finally:second.close()

    def test_removed_category_falls_back_safely(self):
        settings=load_settings(); settings['effects_category']='Removed category'; save_settings(settings)
        window=MainWindow()
        try:self.assertEqual(window.effects_panel.categories.currentItem().text(),'All Effects')
        finally:window.close()


if __name__=='__main__':
    unittest.main()
