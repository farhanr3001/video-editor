import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QFont,QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project
from kinetic_cut.headline import geometry,wrap_lines,paths
from kinetic_cut.emoji import measure

TEXT='xQc enjoys Jaxx Padel at Swansea (South Wales)'


def lines(style,width,text=TEXT):
    font=QFont(style.font); font.setPixelSize(round(style.size)); font.setBold('Bold' in style.font_face)
    return wrap_lines(text,lambda value:measure(value,font),width*.9-style.size*.56)


class HeadlineTransformTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance() or QApplication([])
        self.env=patch.dict('os.environ',{'KINETIC_COMPOSITION_PROCESS':'0'}); self.env.start()
        self.w=MainWindow(); self.w.autosave_timer.stop(); self.w.resize(1400,900); self.w.set_project(Project()); self.w.show(); self.w.add_title_object('Headline'); self.app.processEvents()
        self.item=self.w.project.item_by_id(self.w.timeline.selected_id); self.item.title_text=TEXT; self.w.model_changed(); self.app.processEvents()
    def tearDown(self):self.w.close(); self.app.processEvents(); self.env.stop()
    def test_size_live_reflow_background_and_reverse_independent_properties(self):
        p=self.w.project; style=self.item.title_style; panel=self.w.inspector
        style.position_x=.4; style.position_y=.35; self.item.transform.rotation=17
        counts=[]; heights=[]
        for size in [24,48,72,120,180,240]:
            panel.headline_size.change(size); self.app.processEvents()
            self.assertEqual(style.size,size); self.assertEqual(style.zoom_x,1); self.assertEqual(self.item.transform.rotation,17)
            self.assertEqual((style.position_x,style.position_y),(.4,.35))
            letters,backing=geometry(TEXT,p.settings.width,style.font,size,True)
            self.assertLessEqual(backing.boundingRect().width(),p.settings.width*.9+1)
            self.assertTrue(backing.boundingRect().adjusted(-1,-1,1,1).contains(letters.boundingRect()))
            counts.append(len(lines(style,p.settings.width))); heights.append(backing.boundingRect().height())
        self.assertEqual(counts,sorted(counts)); self.assertGreaterEqual(len(set(counts)),4); self.assertEqual(counts[0],1)
        self.assertEqual(heights,sorted(heights)); panel.headline_size.change(24); self.assertEqual(len(lines(style,p.settings.width)),1)
    def test_scale_preserves_layout_and_scales_padding_and_dimensions(self):
        style=self.item.title_style; panel=self.w.inspector; panel.headline_size.change(180)
        layout=panel.headline_controls.layout()
        rows=[layout.getWidgetPosition(control)[0] for control in (panel.headline_size,panel.headline_scale,panel.headline_rotation)]
        self.assertEqual(rows,[rows[0],rows[0]+1,rows[0]+2])
        before=lines(style,1080); bounds=paths(TEXT,style,1080,1920)[1].boundingRect()
        panel.headline_scale.change(200)
        scaled=paths(TEXT,style,1080,1920)[1].boundingRect()
        self.assertEqual(lines(style,1080),before); self.assertEqual(style.size,180)
        self.assertAlmostEqual(scaled.width(),bounds.width()*2); self.assertAlmostEqual(scaled.height(),bounds.height()*2)
        panel.headline_scale.change(50); self.assertEqual(lines(style,1080),before)
    def test_media_rotation_handle_and_corner_scale_are_independent(self):
        preview=self.w.preview; item=self.item; preview.transform_controls_visible=True; preview.update(); self.app.processEvents()
        target=preview._headline_rect(item); anchor,corners,sides,handle,_=preview._transform_geometry(item,target)
        position=(item.title_style.position_x,item.title_style.position_y); size=item.title_style.size
        QTest.mousePress(preview,Qt.LeftButton,pos=handle.toPoint()); self.assertEqual(preview.drag_mode,'rotate')
        dest=anchor+QPointF(60,0)
        QApplication.sendEvent(preview,QMouseEvent(QEvent.MouseMove,dest,QPointF(preview.mapToGlobal(dest.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        QTest.mouseRelease(preview,Qt.LeftButton,pos=dest.toPoint()); self.app.processEvents()
        self.assertAlmostEqual(item.transform.rotation,90,delta=1); self.assertAlmostEqual(self.w.inspector.headline_rotation.spin.value(),90,delta=1)
        self.assertEqual(item.title_style.size,size); self.assertEqual(position,(item.title_style.position_x,item.title_style.position_y))
        target=preview._headline_rect(item); anchor,corners,*_=preview._transform_geometry(item,target); corner=corners[2]; dest=anchor+(corner-anchor)*1.3
        QTest.mousePress(preview,Qt.LeftButton,pos=corner.toPoint()); self.assertEqual(preview.drag_mode,'headline_scale')
        QApplication.sendEvent(preview,QMouseEvent(QEvent.MouseMove,dest,QPointF(preview.mapToGlobal(dest.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        QTest.mouseRelease(preview,Qt.LeftButton,pos=dest.toPoint()); self.assertGreater(item.title_style.zoom_x,1.2)
        self.assertEqual(item.title_style.zoom_x,item.title_style.zoom_y); self.assertEqual(item.title_style.size,size); self.assertAlmostEqual(item.transform.rotation,90,delta=1)
    def test_layout_width_tracks_canvas_and_save_roundtrip_preserves_controls(self):
        panel=self.w.inspector; panel.headline_size.change(120); panel.headline_scale.change(175); panel.headline_rotation.change(-32)
        for width,height in [(1080,1920),(1920,1080),(720,720)]:
            self.assertLessEqual(geometry(TEXT,width,'Arial',120)[1].boundingRect().width(),width*.9+1)
        before=self.w.project.to_dict()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'headline.kcut'; self.w.project.save(path); loaded=Project.load(path); item=loaded.item_by_id(self.item.id)
            self.assertEqual(item.title_style.size,120); self.assertEqual(item.title_style.zoom_x,1.75); self.assertEqual(item.transform.rotation,-32)
        self.assertEqual(before['timeline'],self.w.project.to_dict()['timeline'])
    def test_reset_and_undo_keep_typography_and_transforms_independent(self):
        panel=self.w.inspector; panel.headline_size.change(120); panel.headline_scale.change(175); panel.headline_rotation.change(-32)
        panel.headline_size.change(150); self.w.undo(); item=self.w.project.item_by_id(self.item.id)
        self.assertEqual((item.title_style.size,item.title_style.zoom_x,item.transform.rotation),(120,1.75,-32))
        self.w.redo(); item=self.w.project.item_by_id(self.item.id)
        panel.headline_rotation.reset.click(); self.assertEqual((item.title_style.size,item.title_style.zoom_x,item.transform.rotation),(150,1.75,0))
        panel.headline_scale.reset.click(); self.assertEqual((item.title_style.size,item.title_style.zoom_x),(150,1))
    def test_animated_rotation_box_uses_current_time_and_rotated_hit_polygon(self):
        from kinetic_cut.keyframes import put
        from PySide6.QtGui import QPolygonF
        preview=self.w.preview; item=self.item
        put(item,'rotation',0,0,'Linear'); put(item,'rotation',1,90,'Linear'); self.w.project.playhead=.5
        target=preview._headline_rect(item); anchor,corners,*_=preview._transform_geometry(item,target)
        from PySide6.QtGui import QTransform
        transform=QTransform(); transform.translate(anchor.x(),anchor.y()); transform.rotate(45); transform.translate(-anchor.x(),-anchor.y())
        self.assertLess((corners[0]-transform.map(target.topLeft())).manhattanLength(),.001)
        bounds=QPolygonF(corners).boundingRect()
        self.assertTrue(preview._text_contains('title',item.id,bounds,anchor))
        self.assertFalse(preview._text_contains('title',item.id,bounds,bounds.topLeft()+QPointF(1,1)))
    def test_scaled_rotated_headline_clips_only_after_transform(self):
        import numpy as np
        from PySide6.QtGui import QImage,QPainter
        from kinetic_cut.native_animation import frame
        p=self.w.project; p.settings.width=320; p.settings.height=568
        item=self.item; style=item.title_style; style.size=72; style.zoom_x=style.zoom_y=2; style.position_x=.8; style.position_y=.3; item.transform.rotation=45
        actual=frame(p,item,0)
        expected=QImage(320,568,QImage.Format_RGBA8888); expected.fill(Qt.transparent)
        painter=QPainter(expected); painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(320*.8,568*.3); painter.rotate(45); painter.translate(-320*.8,-568*.3)
        letters,backing=paths(item.title_text,style,320,568); painter.fillPath(backing,Qt.white); painter.fillPath(letters,Qt.black); painter.end()
        pixels=lambda image:np.frombuffer(image.constBits(),np.uint8).reshape(568,320,4).copy()
        np.testing.assert_array_equal(pixels(actual),pixels(expected))
    def test_rotation_anchor_line_and_handle_are_visible_over_white(self):
        from PySide6.QtGui import QImage,QPainter,QColor
        preview=self.w.preview; target=preview._headline_rect(self.item)
        anchor,_,_,handle,_=preview._transform_geometry(self.item,target)
        self.assertLess(handle.y(),target.top()-15)
        image=QImage(preview.size(),QImage.Format_RGB32); image.fill(Qt.white)
        painter=QPainter(image); preview._draw_transform_box(painter,self.item,target); painter.end()
        x=round(anchor.x()); y=round((target.top()+handle.y())/2)
        self.assertTrue(any(image.pixelColor(xx,y)==QColor('#17191c') for xx in range(x-2,x+3)))

    def test_headline_hides_center_dot_but_media_keeps_it(self):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QImage,QPainter,QColor
        preview=self.w.preview; target=QRectF(100,100,240,100)
        for headline in (True,False):
            item=copy.deepcopy(self.item)
            if not headline:item.role='video'
            anchor,_,_,handle,_=preview._transform_geometry(item,target)
            image=QImage(500,400,QImage.Format_RGB32); image.fill(Qt.white)
            painter=QPainter(image); preview._draw_transform_box(painter,item,target); painter.end()
            x,y=round(anchor.x()),round(anchor.y())
            blue=QColor('#3d8cff')
            ring=any(image.pixelColor(xx,yy)==blue for xx in range(x+4,x+8) for yy in range(y-2,y+3))
            self.assertEqual(ring,not headline)
            hx,hy=round(handle.x()),round(handle.y())
            self.assertTrue(any(image.pixelColor(xx,hy)==blue for xx in range(hx+4,hx+7)))

