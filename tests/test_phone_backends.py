"""Removed phone launchers must never enter the shipped package."""
import unittest
from pathlib import Path
class RemovedBackendTests(unittest.TestCase):
 def test_removed_launchers_and_dependencies(self):
  root=Path(__file__).resolve().parents[1]
  for name in ('phone_connect','phone_mirror','phone_process','phone_worker','phone_common','phone_diagnostics'):
   self.assertFalse((root/'kinetic_cut'/(name+'.py')).exists(),name)
  for name in ('main.py','KineticCut.spec','requirements.txt'):
   text=(root/name).read_text(encoding='utf-8')
   for marker in ('--phone-worker','--phone-selftest','pymobiledevice3','adbutils'):
    self.assertNotIn(marker,text)
if __name__=='__main__':unittest.main()
