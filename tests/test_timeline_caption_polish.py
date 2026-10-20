import unittest
from PySide6.QtCore import Qt,QEvent,QPoint,QPointF,QRectF
from PySide6.QtGui import QFocusEvent,QMouseEvent,QImage,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit,QStyle,QStyleOptionSpinBox
from PySide6.QtTest import QTest
from kinetic_cut.controls import SafeDoubleSpinBox,SafeSpinBox
from kinetic_cut.timeline_style import caption_layout,paint_caption,CAPTION_COLOR,fade_tab


class CaptionPolishTests(unittest.TestCase):
    def test_embedded_window_handoff_keeps_first_drag_but_real_deactivation_ends_it(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            host=QWidget();spin=cls(host);spin.setRange(-100,100);spin.setValue(3);spin.drag_sensitivity=.5
            foreign=QWidget(host);foreign.setObjectName('embedded timeline window');host.show();QApplication.processEvents()
            try:
                for end_event in (QEvent.WindowDeactivate,QEvent.ApplicationDeactivate):
                    line=spin.lineEdit();pos=QPoint(8,8);before=spin.value()
                    QTest.mousePress(line,Qt.LeftButton,pos=pos)
                    QApplication.sendEvent(foreign,QEvent(QEvent.WindowDeactivate))
                    self.assertIsNotNone(spin._drag_start,'Sibling native window focus handoff must retain the first gesture')
                    QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(pos+QPoint(8,0)),QPointF(line.mapToGlobal(pos)+QPoint(8,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                    self.assertGreater(spin.value(),before)
                    QApplication.sendEvent(host,QEvent(end_event))
                    self.assertIsNone(spin._drag_start,'Real editor/application deactivation must still release the mouse')
                    self.assertEqual(line.cursor().shape(),Qt.SizeHorCursor)
                    QTest.mouseRelease(line,Qt.LeftButton,pos=pos)
            finally:host.close();host.deleteLater();QApplication.processEvents()

    def test_numeric_arrows_remain_native_and_do_not_select_text(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            spin=cls();spin.setRange(-100,100);spin.setValue(3);spin.show();QApplication.processEvents()
            try:
                option=QStyleOptionSpinBox();spin.initStyleOption(option)
                for control,direction in ((QStyle.SC_SpinBoxUp,1),(QStyle.SC_SpinBoxDown,-1)):
                    before=spin.value();rect=spin.style().subControlRect(QStyle.CC_SpinBox,option,control,spin)
                    QTest.mouseClick(spin,Qt.LeftButton,pos=rect.center())
                    self.assertAlmostEqual(spin.value(),before+direction*spin.singleStep())
                    self.assertIsNone(spin._drag_start);self.assertFalse(spin._typing);self.assertFalse(spin.lineEdit().hasSelectedText())
            finally:spin.close();spin.deleteLater();QApplication.processEvents()

    def test_numeric_selection_requires_explicit_double_click(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            spin=cls();spin.setRange(-100,100);spin.setValue(3);spin.show();QApplication.processEvents()
            try:
                line=spin.lineEdit()
                self.assertEqual(line.cursor().shape(),Qt.SizeHorCursor)
                # Qt's focus/step machinery may call selectAll independently
                # of mouse delivery when an inspector becomes active.
                line.setFocus(Qt.MouseFocusReason);line.selectAll();QApplication.processEvents()
                self.assertFalse(line.hasSelectedText())
                self.assertEqual(line.focusPolicy(),Qt.NoFocus)
                QTest.mouseDClick(line,Qt.LeftButton)
                self.assertTrue(spin._typing);self.assertTrue(line.hasSelectedText())
                self.assertEqual(line.cursor().shape(),Qt.IBeamCursor)
                QTest.keyClicks(spin,'7');QTest.keyClick(spin,Qt.Key_Return)
                self.assertEqual(spin.value(),7);self.assertFalse(line.hasSelectedText())
                self.assertEqual(line.focusPolicy(),Qt.NoFocus)
                self.assertEqual(line.cursor().shape(),Qt.SizeHorCursor)
            finally:spin.close();spin.deleteLater();QApplication.processEvents()

    def test_first_drag_on_spin_value_area_is_not_native_text_selection(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            host=QWidget();spin=cls(host);spin.setGeometry(10,10,140,28);spin.setRange(-100,100);spin.setValue(3);spin.drag_sensitivity=.5
            host.show();QApplication.processEvents()
            try:
                for target in (spin,spin.lineEdit()):
                    for repeat in range(3):
                        spin.hide();spin.show();QApplication.processEvents()
                        pos=target.rect().center();initial=spin.value()
                        QTest.mousePress(target,Qt.LeftButton,pos=pos)
                        self.assertIsNotNone(spin._drag_start)
                        self.assertEqual(spin.lineEdit().cursor().shape(),Qt.BlankCursor)
                        QApplication.sendEvent(target,QMouseEvent(QEvent.MouseMove,QPointF(pos+QPoint(8,0)),QPointF(target.mapToGlobal(pos)+QPoint(8,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                        QTest.mouseRelease(target,Qt.LeftButton,pos=pos)
                        self.assertGreater(spin.value(),initial);self.assertFalse(spin.lineEdit().hasSelectedText())
                        self.assertEqual(spin.lineEdit().cursor().shape(),Qt.SizeHorCursor)
            finally:host.close();host.deleteLater();QApplication.processEvents()

    def test_unedited_focus_loss_preserves_individual_selected_values(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.model import Project,TimelineItem
        window=MainWindow();window.autosave_timer.stop();window.show()
        try:
            p=Project(timeline=[TimelineItem('a','','video_1',0,2),TimelineItem('b','','video_1',2,2)])
            p.timeline[1].transform.scale=2.;window.set_project(p);window.timeline.select_ids({'a','b'},'a');QApplication.processEvents()
            spin=window.inspector.zoom_x.spin;line=spin.lineEdit();QTest.mouseDClick(line,Qt.LeftButton)
            QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(window.width()-2,window.height()-2));QApplication.processEvents()
            self.assertFalse(spin._typing);self.assertEqual([i.transform.scale for i in p.timeline],[1.,2.])
        finally:window.close();window.deleteLater();QApplication.processEvents()

    def test_clicking_nonfocusable_empty_space_finishes_typing(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            for changed in (False,True):
                host=QWidget();host.resize(300,200);spin=cls(host);spin.setGeometry(10,10,120,25);spin.setRange(-100,100);spin.setValue(3);host.show();QApplication.processEvents()
                try:
                    line=spin.lineEdit();QTest.mouseDClick(line,Qt.LeftButton);QTest.mouseClick(line,Qt.LeftButton)
                    self.assertTrue(spin._typing,'Clicks inside the field must keep text editing')
                    if changed:QTest.keyClick(spin,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(spin,'7')
                    QTest.mouseClick(host,Qt.LeftButton,pos=QPoint(250,170));QApplication.processEvents()
                    self.assertFalse(spin._typing);self.assertFalse(spin.hasFocus());self.assertEqual(spin.value(),7 if changed else 3)
                    QTest.mousePress(line,Qt.LeftButton,pos=QPoint(8,8));self.assertIsNotNone(spin._drag_start)
                    QTest.mouseRelease(line,Qt.LeftButton,pos=QPoint(8,8))
                finally:host.close();host.deleteLater();QApplication.processEvents()

    def test_partial_caption_uses_width_and_height_without_requiring_full_text(self):
        text='Yeah, this is your really long caption'
        layout=caption_layout(text,30,40)
        self.assertGreaterEqual(layout.lineCount(),2)
        shown=sum(layout.lineAt(n).textLength() for n in range(layout.lineCount()))
        self.assertGreater(shown,0);self.assertLess(shown,len(text))
        self.assertGreater(caption_layout(text,30,80).lineCount(),layout.lineCount())
        self.assertEqual(caption_layout(text,5,40).lineCount(),0)
        self.assertEqual(caption_layout(text,30,5).lineCount(),0)

    def test_caption_cream_and_text_pixels_and_flat_top_fade_tab(self):
        image=QImage(140,70,QImage.Format_ARGB32_Premultiplied);image.fill(CAPTION_COLOR)
        painter=QPainter(image);paint_caption(painter,QRectF(0,0,35,48),'a very good caption');fade_tab(painter,90,0);painter.end()
        self.assertEqual(image.pixelColor(60,40).name(),'#b9b097')
        self.assertTrue(any(image.pixelColor(x,y).red()<70 for x in range(4,31) for y in range(4,41)))
        self.assertGreater(image.pixelColor(90,4).red(),240)
        self.assertGreater(image.pixelColor(88,4).red(),220,'Flat top has visible shoulders')
        self.assertEqual(image.pixelColor(90,14).name(),'#b9b097')

    def test_both_numeric_types_reenter_dragging_after_spin_or_line_focus_loss(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            for target in ('spin','line'):
                for change in (False,True):
                    with self.subTest(cls=cls,target=target,change=change):
                        host=QWidget();layout=QVBoxLayout(host);spin=cls();spin.setRange(-100,100);spin.setValue(3);spin.drag_sensitivity=.25
                        other=QLineEdit();layout.addWidget(spin);layout.addWidget(other);host.show();QApplication.processEvents()
                        try:
                            line=spin.lineEdit();QTest.mouseDClick(line,Qt.LeftButton)
                            self.assertTrue(spin._typing)
                            if change:QTest.keyClicks(spin,'7')
                            QApplication.sendEvent(spin if target=='spin' else line,QFocusEvent(QEvent.FocusOut,Qt.MouseFocusReason))
                            other.setFocus();QApplication.processEvents()
                            self.assertFalse(spin._typing);self.assertEqual(spin.focusPolicy(),Qt.NoFocus)
                            self.assertTrue(other.hasFocus())
                            self.assertEqual(spin.value(),7 if change else 3)
                            initial=spin.value();pos=QPoint(8,8);QTest.mousePress(line,Qt.LeftButton,pos=pos)
                            self.assertIsNotNone(spin._drag_start)
                            QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(28,8),QPointF(line.mapToGlobal(pos)+QPoint(20,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                            QTest.mouseRelease(line,Qt.LeftButton,pos=pos);self.assertGreater(spin.value(),initial)
                        finally:host.close();host.deleteLater();QApplication.processEvents()
