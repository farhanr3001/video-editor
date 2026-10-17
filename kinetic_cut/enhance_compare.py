"""Read-only, locally playing before/after wipe for prepared enhancement frames."""
import copy,math,time
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QTimer,Slot
from PySide6.QtGui import QPainter,QPen,QColor,QImage,QShortcut,QKeySequence
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSlider
from . import enhance


class WipeCanvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.before=QImage();self.after=QImage();self.split=.5;self.dragging=False
        self.setMinimumSize(280,180);self.setMouseTracking(True)
    def image_rect(self):
        size=self.before.size()
        if size.isEmpty():return QRectF(self.rect())
        scale=min(max(1,self.width()-16)/size.width(),max(1,self.height()-16)/size.height())
        width,height=size.width()*scale,size.height()*scale
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#101114'));p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.before.isNull() or self.after.isNull():
            p.setPen(QColor('#d5d6dc'));p.drawText(self.rect(),Qt.AlignCenter,'Loading comparison frame…');return
        rect=self.image_rect();x=rect.left()+rect.width()*self.split
        p.drawImage(rect,self.before);p.save();p.setClipRect(QRectF(x,rect.top(),rect.right()-x,rect.height()));p.drawImage(rect,self.after);p.restore()
        p.setPen(QPen(QColor('#ffffff'),2));p.drawLine(int(x),int(rect.top()),int(x),int(rect.bottom()))
        p.setBrush(QColor('#24262e'));p.drawRoundedRect(QRectF(x-12,rect.center().y()-19,24,38),6,6)
        cy=rect.center().y();p.drawLine(int(x-4),int(cy-5),int(x-8),int(cy));p.drawLine(int(x-8),int(cy),int(x-4),int(cy+5));p.drawLine(int(x+4),int(cy-5),int(x+8),int(cy));p.drawLine(int(x+8),int(cy),int(x+4),int(cy+5))
    def update_split(self,point):
        rect=self.image_rect();self.split=max(0.,min(1.,(point.x()-rect.left())/max(1,rect.width())));self.update()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.image_rect().contains(event.position()):self.dragging=True;self.update_split(event.position());event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.dragging:self.update_split(event.position())
        self.setCursor(Qt.SplitHCursor if self.image_rect().contains(event.position()) else Qt.ArrowCursor)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.dragging:self.update_split(event.position());self.dragging=False;event.accept()
        else:super().mouseReleaseEvent(event)


class DifferenceDialog(QDialog):
    def __init__(self,window,item,effect_index):
        super().__init__(window);self.window=window;self.project=copy.deepcopy(window.project);self.item=self.project.item_by_id(item.id);self.effect_index=effect_index
        self.media=self.project.media_by_id(item.media_id);at=item.source_time(window.project.playhead)
        self.record=enhance.range_at(self.project,self.media,self.item,effect_index,at)
        if not self.record:raise ValueError('Prepare this source range before viewing its difference.')
        self.setWindowTitle('AI Enhance · View difference');self.setWindowModality(Qt.WindowModal);self.resize(820,650)
        self._closed=False;self.worker=None;self.pending=None;self.generation=0;self.playing=False
        fps=self.record['fps'];start=self.record['source_start']
        self.low=max(0,math.ceil((item.in_point-start)*fps-1e-5));self.high=min(self.record['frames']-1,math.ceil((item.in_point+item.source_duration-start)*fps-1e-5)-1)
        self.index=max(self.low,min(self.high,round((at-start)*fps)))
        layout=QVBoxLayout(self);labels=QHBoxLayout();labels.addWidget(QLabel('Original'));labels.addStretch();labels.addWidget(QLabel('AI Enhance'));layout.addLayout(labels)
        self.canvas=WipeCanvas();layout.addWidget(self.canvas,1)
        self.note=QLabel('Drag the divider to compare. Playback loops within the prepared source range; the main timeline stays unchanged.');self.note.setWordWrap(True);layout.addWidget(self.note)
        row=QHBoxLayout();layout.addLayout(row);self.play=QPushButton('Play');self.play.setToolTip('Play / Pause · Space');self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.seek=QSlider(Qt.Horizontal);self.seek.setRange(self.low,self.high);self.seek.setValue(self.index);self.seek.valueChanged.connect(self.seek_frame);row.addWidget(self.seek,1)
        self.time=QLabel();row.addWidget(self.time);close=QPushButton('Close');close.clicked.connect(self.close);row.addWidget(close)
        self.shortcut=QShortcut(QKeySequence('Space'),self);self.shortcut.setContext(Qt.WidgetWithChildrenShortcut);self.shortcut.activated.connect(self.toggle)
        self.timer=QTimer(self);self.timer.setTimerType(Qt.PreciseTimer);self.timer.setInterval(16);self.timer.timeout.connect(self.tick)
        self.request(self.index)
    def request(self,index):
        self.index=index;self.pending=(index,self.generation)
        source_at=self.record['source_start']+index/self.record['fps']
        timeline=self.item.start+(source_at-self.item.in_point)/max(.05,self.item.speed)
        self.time.setText(f'{timeline:.2f}s');self.seek.blockSignals(True);self.seek.setValue(index);self.seek.blockSignals(False)
        if self.worker is not None:return
        self.load_pending()
    def load_pending(self):
        if self._closed or self.pending is None:return
        from .ui import Worker
        index,generation=self.pending;self.pending=None
        project,item,media,effect_index,record=self.project,self.item,self.media,self.effect_index,self.record
        def read():
            original=QImage(str(Path(record['root'])/'original'/f'{index:08d}.png'))
            enhanced=enhance.cached_frame(project,media,item,effect_index,record['source_start']+index/record['fps'])
            return index,generation,original,enhanced
        self.worker=Worker(read);self.worker.signals.result.connect(self.ready,Qt.QueuedConnection);self.worker.signals.error.connect(self.failed,Qt.QueuedConnection);self.worker.signals.finished.connect(self.retire,Qt.QueuedConnection);self.window.start_worker(self.worker)
    @Slot(object)
    def ready(self,result):
        index,generation,original,enhanced=result
        if self._closed or generation!=self.generation:return
        if original.isNull() or enhanced.isNull():self.failed('Comparison frames were cleared. Prepare this clip again.');return
        self.canvas.before=original;self.canvas.after=enhanced;self.canvas.update();self.presented_index=index
    @Slot(str)
    def failed(self,error):
        if self._closed:return
        self.playing=False;self.timer.stop();self.play.setText('Play');self.note.setText(error.splitlines()[-1])
    @Slot()
    def retire(self):
        self.worker=None
        if self._closed:self.deleteLater()
        else:self.load_pending()
    def seek_frame(self,index):
        self.generation+=1;self.clock=time.monotonic();self.clock_index=index;self.request(index)
    def toggle(self):
        if self._closed:return
        self.playing=not self.playing;self.play.setText('Pause' if self.playing else 'Play')
        if self.playing:self.clock=time.monotonic();self.clock_index=self.index;self.timer.start()
        else:self.timer.stop()
    def tick(self):
        advance=int((time.monotonic()-self.clock)*self.record['fps']*self.item.speed)
        index=self.low+(self.clock_index-self.low+advance)%max(1,self.high-self.low+1)
        if index!=self.index:self.request(index)
    def closeEvent(self,event):
        self._closed=True;self.timer.stop();self.playing=False;self.pending=None;super().closeEvent(event)
        if self.worker is None:self.deleteLater()
    def done(self,result):
        self._closed=True;self.timer.stop();self.playing=False;self.pending=None;super().done(result)
        if self.worker is None:self.deleteLater()


def show(inspector):
    item=inspector.window.project.item_by_id(inspector.item_id)
    if not item:return
    try:dialog=DifferenceDialog(inspector.window,item,inspector.effect_picker.currentIndex())
    except ValueError:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(inspector.window,'Prepare this frame','This position is outside the enhanced source range. Choose Prepare selected clips to compare it.');return
    inspector._enhance_difference=dialog;dialog.open()
