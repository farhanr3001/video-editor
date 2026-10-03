"""Custom Face cache, pixel, authoring, and export regressions."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QDialog

from kinetic_cut.custom_face import REGIONS, apply_custom_face, values
from kinetic_cut.custom_face_dialog import CustomFaceDialog
from kinetic_cut.model import Crop, MediaItem, Project, ProjectSettings, TimelineItem, Transform
from kinetic_cut import vision_effects as vision


def fixture(root):
    source = Path(root)/'source.png'
    image = QImage(160, 160, QImage.Format_RGBA8888)
    for y in range(160):
        for x in range(160):
            image.setPixelColor(x, y, QColor(min(255, 60+x), min(255, 65+y), 100, 255))
    image.save(str(source))
    media = MediaItem('media', str(source), 'image', source.name, 2, 160, 160)
    item = TimelineItem('clip', 'media', 'video_1', 0, 2)
    folder = Path(root)/'analysis'
    (folder/'masks').mkdir(parents=True)
    mask = QImage(160, 160, QImage.Format_Grayscale8)
    mask.fill(255)
    mask.save(str(folder/'masks'/'00000000.png'))
    mask.save(str(folder/'masks'/'00000001.png'))
    (folder/'faces.json').write_text(json.dumps([[[.5,.5]]*10,None]), encoding='utf-8')
    mesh = np.full((2, 478, 3), np.nan, dtype=np.float16)
    mesh[0,:,:] = (.5,.5,0)
    for name,(cx,cy,rx,ry) in {
        'Face':(.5,.51,.34,.42), 'Left eye':(.39,.43,.08,.035),
        'Right eye':(.61,.43,.08,.035), 'Nose':(.5,.55,.09,.11),
        'Mouth':(.5,.69,.12,.055),
    }.items():
        indices = REGIONS[name]
        for j, landmark in enumerate(indices):
            angle = 2*math.pi*j/len(indices)
            mesh[0,landmark,:2] = (cx+rx*math.cos(angle), cy+ry*math.sin(angle))
    mesh[0,205,:2] = (.37,.6)
    mesh[0,425,:2] = (.63,.6)
    np.save(folder/'mesh.npy',mesh)
    analysis = dict(root=str(folder),source=vision.fingerprint(media),crop=vars(item.crop.clamped()),
                    source_start=0,source_end=2,fps=1,frames=2,face_frames=1,person_frames=2)
    return media,item,analysis,image,mesh[0]


class CustomFaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        vision._face_data.cache_clear()
        vision._mesh_data.cache_clear()
        vision.mask_image.cache_clear()
        self.temp.cleanup()

    def test_mesh_cache_required_only_for_custom_face(self):
        media,item,analysis,image,mesh = fixture(self.root)
        item.effects=[dict(name='Custom Face',analysis=analysis,morph={'nose_size':70})]
        self.assertTrue(vision.valid_effect(item.effects[0],media,item))
        (Path(analysis['root'])/'mesh.npy').unlink()
        self.assertFalse(vision.valid_effect(item.effects[0],media,item))
        self.assertIn('Re-analyse',vision.status(item,media,0))
        self.assertEqual(vision.apply(image,item,media,0),image)
        item.effects[0]['name']='Big Nose'
        self.assertTrue(vision.valid_effect(item.effects[0],media,item))

    def test_morph_tint_and_no_face_leave_original_safe(self):
        media,item,analysis,image,mesh = fixture(self.root)
        effect=dict(name='Custom Face',analysis=analysis,morph={'left_eye':80,'nose_size':65},
                    skin_color='#b28474',skin_strength=35)
        item.effects=[effect]
        changed=vision.apply(image,item,media,0)
        self.assertNotEqual(changed,image)
        self.assertEqual(changed.pixelColor(0,0),image.pixelColor(0,0))
        self.assertEqual(changed.pixelColor(80,80).alpha(),255)
        self.assertEqual(vision.apply(image,item,media,1),image)
        item.effects[0]['enabled']=False
        self.assertEqual(vision.apply(image,item,media,0),image)

    def test_invalid_values_are_bounded(self):
        self.assertEqual(values({'morph':{'left_eye':float('nan'),'nose_size':1000}})['left_eye'],0)
        self.assertEqual(values({'morph':{'nose_size':1000}})['nose_size'],140)
        media,item,analysis,image,mesh=fixture(self.root)
        tinted=image.copy()
        apply_custom_face(tinted,mesh,dict(morph={},skin_strength='invalid',skin_color='not-a-color'))
        self.assertEqual(tinted,image)

    def test_skin_colour_covers_lit_and_shadowed_parts_of_whole_face(self):
        media,item,analysis,image,mesh=fixture(self.root)
        tinted=image.copy()
        apply_custom_face(tinted,mesh,dict(morph={},skin_color='#3459b7',skin_strength=100))
        for x,y in ((80,35),(45,85),(80,90),(115,85),(80,135)):
            self.assertNotEqual(tinted.pixelColor(x,y),image.pixelColor(x,y),(x,y))
        self.assertEqual(tinted.pixelColor(0,0),image.pixelColor(0,0))

    def test_eye_spacing_moves_both_eyes_in_and_out_without_changing_edges(self):
        media,item,analysis,_,mesh=fixture(self.root)
        original=QImage(160,160,QImage.Format_RGBA8888)
        original.fill(QColor(35,35,35))
        for x,colour in ((62,QColor(230,20,20)),(98,QColor(20,20,230))):
            for py in range(66,72):
                for px in range(x-3,x+4):original.setPixelColor(px,py,colour)
        def centres(image):
            rgba=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(160,160,4)
            red=np.where((rgba[:,:,0]>150)&(rgba[:,:,2]<90))
            blue=np.where((rgba[:,:,2]>150)&(rgba[:,:,0]<90))
            self.assertGreater(len(red[1]),0)
            self.assertGreater(len(blue[1]),0)
            return float(np.mean(red[1])),float(np.mean(blue[1]))
        left,right=centres(original)
        wide=original.copy(); apply_custom_face(wide,mesh,{'morph':{'eye_spacing':100}})
        narrow=original.copy(); apply_custom_face(narrow,mesh,{'morph':{'eye_spacing':-100}})
        wide_left,wide_right=centres(wide)
        narrow_left,narrow_right=centres(narrow)
        self.assertLess(wide_left,left-2)
        self.assertGreater(wide_right,right+2)
        self.assertGreater(narrow_left,left+2)
        self.assertLess(narrow_right,right-2)
        self.assertEqual(wide.pixelColor(0,0),original.pixelColor(0,0))
        self.assertEqual(narrow.pixelColor(0,0),original.pixelColor(0,0))
        item.effects=[dict(name='Custom Face',analysis=analysis,morph={'eye_spacing':-75})]
        project=Project(media=[media],timeline=[item])
        saved=self.root/'eye-spacing.kcut'; project.save(saved)
        self.assertEqual(Project.load(saved).timeline[0].effects[0]['morph']['eye_spacing'],-75)

    def test_dialog_preview_uses_output_aspect_crop_and_clip_transform(self):
        from kinetic_cut.ui import MainWindow
        media,item,analysis,_,_=fixture(self.root)
        media.width,media.height=160,90
        item.crop=Crop(.25,0,.5,1)
        item.transform=Transform(x=.5,y=.62,scale=.5,flip_horizontal=True)
        item.keyframes={'scale':[dict(time=0,value=.5),dict(time=1,value=1.)]}
        analysis['crop']=vars(item.crop.clamped())
        frame=QImage(160,90,QImage.Format_RGBA8888)
        frame.fill(QColor(30,70,220))
        for y in range(90):
            for x in range(80,160):frame.setPixelColor(x,y,QColor(220,50,30))
        window=MainWindow()
        window.autosave_timer.stop()
        window.set_project(Project(settings=ProjectSettings(width=90,height=160,fps=30),
                                   media=[media],timeline=[item]))
        dialog=CustomFaceDialog(window,media,item,analysis)
        try:
            dialog._decode_timer.stop()
            dialog.before.setChecked(True)
            dialog.guides.setChecked(False)
            dialog.frame_ready(0,frame)
            result=dialog.view.image
            self.assertEqual((result.width(),result.height()),(90,160))
            self.assertEqual(result.pixelColor(45,10),QColor(0,0,0))
            self.assertEqual(result.pixelColor(5,100),QColor(0,0,0))
            self.assertEqual(result.pixelColor(25,100),QColor(220,50,30))
            self.assertEqual(result.pixelColor(65,100),QColor(30,70,220))
            dialog._requested=30
            dialog.frame_ready(30,frame)
            self.assertEqual(dialog.view.image.pixelColor(5,100),QColor(220,50,30))
        finally:
            dialog.reject()
            window.close()

    def test_apply_and_customize_accept_without_dialog_attribute_error(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.vision_ui import begin,customize
        window=MainWindow()
        window.autosave_timer.stop()
        media,item,analysis,image,mesh=fixture(self.root)
        item.effects=[dict(name='Custom Face',enabled=True,analysis=analysis,morph={})]
        window.set_project(Project(media=[media],timeline=[item]))
        window.select_item(item.id)
        class AcceptedDialog:
            def __init__(self,*args,**kwargs):pass
            def exec(self):return QDialog.Accepted
            def result_effect(self):
                return dict(name='Custom Face',enabled=True,analysis=copy.deepcopy(analysis),
                            morph={'nose_size':120},skin_strength=0,skin_color='#bd856b')
        try:
            with patch('kinetic_cut.custom_face_dialog.CustomFaceDialog',AcceptedDialog):
                begin(window,'Custom Face')
                self.assertEqual(item.effects[0]['morph']['nose_size'],120)
                with patch.object(window.inspector,'effect',return_value=item.effects[0]):
                    customize(window)
                self.assertEqual(item.effects[0]['morph']['nose_size'],120)
        finally:window.close()

    def test_dialog_group_reset_and_cancel_do_not_modify_clip(self):
        from kinetic_cut.ui import MainWindow
        window=MainWindow()
        window.autosave_timer.stop()
        media,item,analysis,image,mesh=fixture(self.root)
        window.set_project(Project(media=[media],timeline=[item]))
        original=copy.deepcopy(item)
        effect=dict(name='Custom Face',morph={'eye_spacing':75,'left_eye':55,'right_eye':-40,'nose_size':22},
                    skin_strength=35,skin_color='#aabbcc')
        dialog=CustomFaceDialog(window,media,item,analysis,effect)
        dialog._decode_timer.stop()
        self.assertEqual(dialog.rows['nose_size'][0].maximum(),140)
        self.assertEqual(dialog.rows['nose_size'][1].maximum(),140)
        self.assertEqual(dialog.rows['left_eye'][0].value(),55)
        dialog.reset_group('Eyes')
        self.assertEqual(dialog.rows['eye_spacing'][0].value(),0)
        self.assertEqual(dialog.rows['left_eye'][0].value(),0)
        self.assertEqual(dialog.rows['right_eye'][0].value(),0)
        self.assertEqual(dialog.rows['nose_size'][0].value(),22)
        dialog.reset_group('Skin colour')
        self.assertEqual(dialog.skin_strength.value(),0)
        self.assertEqual(dialog.effect['skin_color'],'#bd856b')
        dialog.reset_all()
        self.assertTrue(all(slider.value()==0 for slider,_,_ in dialog.rows.values()))
        dialog.reject()
        self.assertEqual(window.project.item_by_id(item.id),original)
        window.close()
