"""Phone feature removal: navigation, lifecycle and optional downloads."""
import os, unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import set_page
from kinetic_cut import feature_packs
class RemovedPhoneTests(unittest.TestCase):
 def test_only_edit_and_deliver_pages(self):
  app=QApplication.instance() or QApplication([])
  window=MainWindow()
  try:
   self.assertEqual([b.text() for b in window.page_group.buttons()],['Edit','Deliver'])
   self.assertFalse(hasattr(window,'phone_connect'))
   set_page(window,2);self.assertEqual(window.current_page,0)
   set_page(window,1);self.assertEqual(window.current_page,1)
   set_page(window,0);self.assertEqual(window.current_page,0)
  finally:window.close();window.deleteLater();app.processEvents()
 def test_phone_components_cannot_be_installed(self):
  self.assertEqual(set(feature_packs.ROOTS),{'vision','vocals','enhance'})
  for key in ('android','iphone'):
   with self.assertRaises(KeyError):feature_packs.component_root(key)
if __name__=='__main__':unittest.main()
