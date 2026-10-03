"""Scrub the original selected clip and pick a pixel without moving the main playhead."""
import copy
from PySide6.QtCore import QRectF,Qt,QTimer,Signal
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLabel,QSlider,QVBoxLayout,QWidget


class SampleImage(QWidget):
    picked=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.image=QImage(); self.setMinimumSize(400,300); self.setCursor(Qt.CrossCursor)
    def image_rect(self):
        if self.image.isNull():return QRectF()
        size=self.image.size().scaled(self.size(),Qt.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
    def paintEvent(self,event):
        painter=QPainter(self); painter.fillRect(self.rect(),QColor("#14161b")); painter.drawImage(self.image_rect(),self.image)
    def mousePressEvent(self,event):
        rect=self.image_rect(); point=event.position()
        if event.button()==Qt.LeftButton and not self.image.isNull() and rect.contains(point):
            x=min(self.image.width()-1,int((point.x()-rect.x())/rect.width()*self.image.width()))
            y=min(self.image.height()-1,int((point.y()-rect.y())/rect.height()*self.image.height()))
            self.picked.emit(self.image.pixelColor(x,y).name())


class ChromaSampleDialog(QDialog):
    def __init__(self,window,item):
        super().__init__(window); self.setWindowTitle("Select colour in video"); self.resize(470,570)
        self.window=window; self.item=copy.deepcopy(item); self.media=copy.deepcopy(window.project.media_by_id(item.media_id))
        self.fps=window.project.settings.fps; self.closed=False; self.busy=False; self.requested=0; self.colour=None
        layout=QVBoxLayout(self); info=QLabel("Original selected clip · click a colour, then Apply.\nScrubbing here does not move the main timeline playhead."); info.setWordWrap(True); layout.addWidget(info)
        self.view=SampleImage(); self.view.picked.connect(self.pick); layout.addWidget(self.view,1)
        self.timestamp=QLabel(); layout.addWidget(self.timestamp)
        self.slider=QSlider(Qt.Horizontal); self.slider.setRange(0,max(0,round(item.duration*self.fps)-1)); layout.addWidget(self.slider)
        self.swatch=QLabel("No colour selected"); self.swatch.setMinimumHeight(34); layout.addWidget(self.swatch)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Apply)
        self.buttons.button(QDialogButtonBox.Apply).setEnabled(False); self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        self.debounce=QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(80); self.debounce.timeout.connect(self.fetch)
        self.slider.valueChanged.connect(self.request); self.finished.connect(self.finish)
        self.slider.setValue(max(0,min(self.slider.maximum(),round((window.project.playhead-item.start)*self.fps))))
        self.request(self.slider.value())

    def request(self,frame):
        self.requested=frame; time=self.item.start+frame/self.fps
        self.timestamp.setText(f"Timeline {int(time)//60:02d}:{int(time)%60:02d}:{int(round(time*self.fps))%self.fps:02d} · Clip {frame/self.fps:.2f} / {self.item.duration:.2f} s")
        self.view.setEnabled(False); self.debounce.start()

    def fetch(self):
        if self.busy or self.closed:return
        if not self.media:return
        if self.media.kind=="image":self.view.image=QImage(self.media.path); self.view.setEnabled(True); self.view.update(); return
        from .ui import Worker
        from .widgets import extract_frame
        frame=self.requested; self.busy=True
        worker=Worker(extract_frame,self.media.path,self.item.in_point+frame/self.fps*self.item.speed,self.window.settings.get("ffmpeg","ffmpeg"))
        def ready(image):
            self.busy=False
            if self.closed:return
            if self.requested!=frame:self.fetch(); return
            self.view.image=image; self.view.setEnabled(not image.isNull()); self.view.update()
            if image.isNull():self.swatch.setText("Could not read this frame. Try another timestamp.")
        def failed(_):
            self.busy=False
            if not self.closed:self.swatch.setText("Could not read this frame.")
        worker.signals.result.connect(ready); worker.signals.error.connect(failed); self.window.start_worker(worker)

    def pick(self,color):
        self.colour=color; ink="#111" if QColor(color).lightnessF()>.5 else "#fff"
        self.swatch.setText("Selected "+color); self.swatch.setStyleSheet(f"background:{color};color:{ink};padding:6px")
        self.buttons.button(QDialogButtonBox.Apply).setEnabled(True)

    def finish(self,*_):self.closed=True; self.debounce.stop()
