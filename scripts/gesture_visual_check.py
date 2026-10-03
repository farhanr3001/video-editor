"""Render the new timeline gestures without changing any user project."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(ROOT/'build/gesture-visual-home')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QPixmap,QColor
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from test_timeline_gestures import GestureTests
app=QApplication([])
for font in ('arial.ttf','segoeui.ttf'):QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/font))
out=ROOT/'build/gesture-visual-check'; out.mkdir(parents=True,exist_ok=True)
test=GestureTests(); test.setUp(); p=test.pair(); t=test.t
pos=QPoint(round(t.x_for_time(5)),round(t.item_rect(p.timeline[0]).center().y()))
QTest.mouseMove(t.viewport(),pos); t.grab().save(str(out/'roll-hover.png'))
test.drag(pos,pos+QPoint(70,0)); t.grab().save(str(out/'roll-drag.png'))
assert t.drag_mode=='roll'; assert p.timeline[1].start==p.timeline[0].duration
QTest.keyClick(t.viewport(),Qt.Key_Escape)
test.drag(pos-QPoint(4,0),pos+QPoint(70,0)); t.grab().save(str(out/'single-trim.png'))
assert t.drag_mode=='trim_right'; assert p.timeline[1].start==5
QTest.keyClick(t.viewport(),Qt.Key_Escape)
pix=QPixmap(100,60); pix.fill(QColor('#86b1c3')); t.thumbnails['m']=pix; p.media[0].thumbnail='m'
p.timeline[0].fade_in=1.1; p.timeline[0].fade_out=1.8; p.playhead=2.4
t.grab().save(str(out/'fade-borders-playhead.png'))
snapshot=t.viewport().grab().toImage(); rect=t.item_rect(p.timeline[0]); y=round(rect.top()+12)
assert snapshot.pixelColor(round(rect.left()+12),y).lightness()<snapshot.pixelColor(round(rect.left()+90),y).lightness()-20
assert snapshot.pixelColor(round(t.x_for_time(p.playhead)),80).red()>200
test.tearDown()
(out/'report.json').write_text(json.dumps(dict(passed=True,rolling_and_single_trim_distinct=True)))
