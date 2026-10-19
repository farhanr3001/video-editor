import copy,unittest
from PySide6.QtCore import Qt,QPoint,QEvent,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem,Caption


class TimelineTextFocusTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance();self.w=MainWindow();self.w.resize(1400,850);self.w.show();self.w.autosave_timer.stop()
        self.p=Project(timeline=[TimelineItem('title','','video_1',0,3,role='title',title_text='Existing 🥹\nHeadline')],
            captions=[Caption('caption',0,3,'Existing subtitle')])
        self.w.set_project(self.p);self.t=self.w.timeline;self.t.set_zoom(70);self.t.horizontalScrollBar().setValue(0);self.app.processEvents()
    def tearDown(self):
        self.w.close();QThreadPool.globalInstance().waitForDone(10000);self.w.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def click(self,rect):
        QTest.mouseDClick(self.t.viewport(),Qt.LeftButton,pos=QPoint(round(self.t.x_for_time(1)),round(rect.center().y())))
        self.app.processEvents()
    def test_title_double_click_opens_inspector_and_caret_at_end_without_mutation(self):
        before=copy.deepcopy(self.p.to_dict());self.w.inspector_toggle.setChecked(False)
        self.click(self.t.visible_item_rect(self.p.timeline[0]))
        field=self.w.inspector.title_text
        self.assertTrue(field.hasFocus());self.assertTrue(self.w.inspector_toggle.isChecked())
        self.assertEqual(field.textCursor().position(),len('Existing 🥹\nHeadline'.encode('utf-16-le'))//2)
        self.assertFalse(field.textCursor().hasSelection());self.assertEqual(self.p.to_dict(),before)
        QTest.keyClicks(field,'!');self.assertEqual(self.p.timeline[0].title_text,'Existing 🥹\nHeadline!')
    def test_caption_double_click_places_caret_at_end_and_does_not_replace_other_caption(self):
        self.p.captions.append(Caption('other',4,6,'Other'));self.t.select_captions({'caption','other'},'other')
        self.click(self.t.visible_caption_rect(self.p.captions[0]))
        field=self.w.inspector.caption_text;self.assertTrue(field.hasFocus())
        self.assertEqual(field.textCursor().position(),len('Existing subtitle'));self.assertFalse(field.textCursor().hasSelection())
        QTest.keyClick(field,Qt.Key_Backspace)
        self.assertEqual(self.p.captions[0].text,'Existing subtitl');self.assertEqual(self.p.captions[1].text,'Other')
    def test_read_only_timeline_does_not_request_text_editing(self):
        called=[];self.t.textEditRequested.connect(lambda *args:called.append(args));self.t.set_read_only(True)
        self.click(self.t.visible_item_rect(self.p.timeline[0]));self.assertEqual(called,[])
