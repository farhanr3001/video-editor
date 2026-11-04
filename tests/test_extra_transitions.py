import math,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
APP=QApplication.instance() or QApplication([])
from kinetic_cut.animated_transitions import NAMES,EXTRA_NAMES,ALL_NAMES,CONTROLS,BASE,values,defaults,maps,composite
from kinetic_cut.transitions import Transition,TRANSITION_SET,TRANSITION_NAMES,default_transition_properties

def image(offset=0):
    y,x=np.mgrid[:48,:64];a=np.empty((48,64,4),np.uint8);a[:,:,0]=(x*4+offset)%256;a[:,:,1]=(y*5+offset)%256;a[:,:,2]=160;a[:,:,3]=255
    return QImage(a.data,64,48,256,QImage.Format_RGBA8888).copy()

class ExtraTransitions(unittest.TestCase):
    def test_gpu_backed_catalogue_is_unchanged_and_extras_are_registered(self):
        self.assertEqual(len(NAMES),24); self.assertEqual(len(EXTRA_NAMES),17); self.assertEqual(len(set(ALL_NAMES)),41)
        for n in EXTRA_NAMES:
            self.assertIn(n,TRANSITION_SET); self.assertIn(n,TRANSITION_NAMES); self.assertEqual(default_transition_properties(n),defaults(n)); self.assertIn(n,CONTROLS)
    def test_exact_endpoints_and_midpoints(self):
        a,b=image(),image(85)
        for n in EXTRA_NAMES:
            t=Transition('t',n,properties={'easing':'Linear'})
            self.assertEqual(composite(a,b,t,0,(64,48)),a.convertToFormat(QImage.Format_RGBA8888_Premultiplied),n)
            self.assertEqual(composite(a,b,t,1,(64,48)),b.convertToFormat(QImage.Format_RGBA8888_Premultiplied),n)
            if n!='Strobe Cut':self.assertNotEqual(composite(a,b,t,.4,(64,48)),a.convertToFormat(QImage.Format_RGBA8888_Premultiplied),n)
            self.assertFalse(composite(None,b,t,.4,(64,48)).isNull())
    def test_finite_for_hostile_controls_and_weights_bounded(self):
        for n in EXTRA_NAMES:
            for props in ({},{k:float('nan') for k,*_ in BASE},{k:1e20 for k,*_ in BASE},{k:-1e20 for k,*_ in BASE}):
                params=values(props)
                for at in (0,.1,.5,.9,1):
                    out=maps(n,32,24,params,at); self.assertTrue(all(np.isfinite(v).all() for v in out),(n,at)); self.assertTrue(((out[-1]>=0)&(out[-1]<=1)).all())
    def test_deterministic(self):
        for n in EXTRA_NAMES:
            t=Transition('t',n); self.assertEqual(composite(image(),image(85),t,.3,(64,48)),composite(image(),image(85),t,.3,(64,48)),n)
    def test_gpu_modes_shaders_and_native_gating(self):
        from pathlib import Path
        from kinetic_cut.animated_transitions import mode_of,descriptor,native_names,EXTRA_MODE_BASE
        root=Path(__file__).resolve().parents[1]
        modes=[mode_of(n) for n in EXTRA_NAMES]; self.assertEqual(modes,list(range(EXTRA_MODE_BASE,EXTRA_MODE_BASE+17)))
        for n in EXTRA_NAMES:
            self.assertEqual(descriptor(Transition('t',n))['mode'],mode_of(n))
            self.assertTrue((root/'assets/shaders'/('transition_%d.frag.qsb'%mode_of(n))).is_file(),n)
        self.assertIn('KINETIC_TRANSITION_MODE == 66',(root/'native/gpu_export.cpp').read_text(encoding='utf-8'))
        marker=root/'assets/native/gpu_export.modes'
        if not marker.exists():self.assertEqual(native_names(),NAMES,'extras must stay on the safe path until the DLL is rebuilt')
if __name__=='__main__':unittest.main()
