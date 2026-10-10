"""Pool presentation and source previews; never modify project media or edits."""
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QSize,QRect,QUrl,QTimer,QObject,Slot,QEvent
from PySide6.QtGui import QImage,QPixmap,QPainter,QColor,QIcon,QStandardItemModel
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QSlider,QStyledItemDelegate,QStyle,QHeaderView,QListWidget)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .media_source import set_media_source
from PySide6.QtMultimediaWidgets import QVideoWidget
from .controls import SafeSlider as QSlider


def metadata(media):
    seconds=max(0,round(media.duration))
    return [media.name,f'{seconds//60}:{seconds%60:02d}' if media.kind!='image' else '—',
            f'{media.width} × {media.height}' if media.width and media.height else '—',media.kind.title()]


class PoolDelegate(QStyledItemDelegate):
    def __init__(self,panel):super().__init__(panel.grid); self.panel=panel
    def sizeHint(self,option,index):
        return QSize(sum(self.panel.column_header.sectionSize(n) for n in range(4)),36) if self.panel.list_view else super().sizeHint(option,index)
    def paint(self,painter,option,index):
        if not self.panel.list_view:return super().paint(painter,option,index)
        painter.save(); painter.setClipRect(option.rect)
        selected=bool(option.state&QStyle.State_Selected)
        painter.fillRect(option.rect,option.palette.highlight() if selected else option.palette.base())
        painter.setPen(option.palette.highlightedText().color() if selected else option.palette.text().color())
        if index.data(Qt.UserRole+4):
            painter.fillRect(option.rect,QColor('#410b0d')); painter.setPen(QColor('#ffaaa1'))
        values=index.data(Qt.UserRole+3) or [index.data(),'', '', 'Folder']
        x=option.rect.left()
        for n,value in enumerate(values):
            width=self.panel.column_header.sectionSize(n); cell=QRect(x+7,option.rect.top(),width-14,option.rect.height())
            if n==0:
                icon=index.data(Qt.DecorationRole)
                if icon:icon.paint(painter,QRect(x+5,option.rect.top()+5,36,26))
                cell.setLeft(x+47)
            painter.drawText(cell,Qt.AlignVCenter,painter.fontMetrics().elidedText(str(value),Qt.ElideRight,max(0,cell.width())))
            x+=width
        painter.restore()


def setup_view(panel,container):
    panel.list_view=False
    panel.column_header=QHeaderView(Qt.Horizontal,container)
    panel.column_header.setFixedHeight(26)
    model=QStandardItemModel(0,4,panel.column_header); model.setHorizontalHeaderLabels(['Name','Duration','Resolution','Type'])
    panel.column_header.setModel(model); panel.column_header.setMinimumSectionSize(60)
    for n,width in enumerate((220,85,120,80)):panel.column_header.resizeSection(n,width)
    panel.column_header.sectionResized.connect(lambda *_:panel.grid.doItemsLayout())
    panel.grid.horizontalScrollBar().valueChanged.connect(panel.column_header.setOffset)
    panel.grid.setItemDelegate(PoolDelegate(panel))
    container.layout().addWidget(panel.column_header); container.layout().addWidget(panel.grid)
    set_view(panel,panel.window.settings.get('media_pool_list_view',False),False)


def set_view(panel,enabled,persist=True):
    panel.list_view=bool(enabled); grid=panel.grid
    grid.setViewMode(QListWidget.ListMode if enabled else QListWidget.IconMode)
    grid.setFlow(QListWidget.TopToBottom if enabled else QListWidget.LeftToRight)
    grid.setWrapping(not enabled); grid.setGridSize(QSize() if enabled else QSize(130,100))
    grid.setIconSize(QSize(36,26) if enabled else QSize(110,65))
    grid.setMovement(QListWidget.Static); grid.setDragEnabled(True); grid.setAcceptDrops(True); grid.viewport().setAcceptDrops(True)
    panel.column_header.setVisible(enabled)
    panel.view_button.setText('Gallery' if enabled else 'List'); panel.view_button.setToolTip('Switch to gallery view' if enabled else 'Switch to list view')
    from .icons import lucide_icon
    panel.view_button.setIcon(lucide_icon('layout-grid' if enabled else 'list'))
    panel.view_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    grid.doItemsLayout()
    if persist:
        from .config import save_settings
        panel.window.settings['media_pool_list_view']=bool(enabled); save_settings(panel.window.settings)


def wave_image(path,ffmpeg):
    from .waveforms import waveform,BIN_SECONDS
    samples=waveform(path,ffmpeg); duration=len(samples)*BIN_SECONDS
    values=samples.columns(np.arange(108)*duration/108,duration/108)
    image=QImage(110,65,QImage.Format_ARGB32); image.fill(QColor('#151719'))
    painter=QPainter(image); painter.setPen(QColor('#33453b')); painter.drawLine(1,32,108,32)
    for x,(low,high) in enumerate(values,1):
        top=round(32-high*29); bottom=round(32-low*29)
        # Absolute sample level, not per-file normalization: quiet files stay quiet.
        for y in range(top,bottom+1):
            amplitude=abs(y-32)/29
            painter.setPen(QColor('#da6560' if amplitude>=.94 else '#c4b969' if amplitude>=.7 else '#73ae83'))
            painter.drawPoint(x,y)
    painter.setPen(QColor('#050607')); painter.drawRoundedRect(0,0,109,64,3,3); painter.end()
    return image


class AudioThumbnails(QObject):
    """One decoder job at a time; no selection resets or main-thread audio work."""
    def __init__(self,panel):super().__init__(panel); self.panel=panel; self.cache={}; self.pending=[]; self.known=set(); self.busy=False
    def icon(self,media):
        try:
            stat=Path(media.path).stat(); key=(media.path,stat.st_size,stat.st_mtime_ns)
        except OSError:return QIcon()
        if key not in self.known:
            self.known.add(key); self.pending.append(key); QTimer.singleShot(0,self.next)
        return self.cache.get(key,QIcon())
    @Slot()
    def next(self):
        if self.busy or not self.pending:return
        from .ui import Worker
        self.busy=True; key=self.pending.pop(0); self.current_key=key
        worker=Worker(wave_image,key[0],self.panel.window.settings.get('ffmpeg','ffmpeg'))
        worker.signals.result.connect(self.ready)
        worker.signals.finished.connect(self.finished)
        self.panel.window.start_worker(worker)
    @Slot(object)
    def ready(self,image):
        key=self.current_key
        icon=QIcon(QPixmap.fromImage(image)); self.cache[key]=icon
        for n in range(self.panel.grid.count()):
            item=self.panel.grid.item(n)
            if item.toolTip()==key[0]:item.setIcon(icon)
    @Slot()
    def finished(self):self.busy=False; QTimer.singleShot(0,self.next)


class SourcePreview(QDialog):
    def __init__(self,parent,media):
        super().__init__(parent); self.setAttribute(Qt.WA_DeleteOnClose); self.setWindowTitle('Preview · '+media.name); self.resize(760,500)
        self.setWindowModality(Qt.WindowModal); self.setFocusPolicy(Qt.StrongFocus)
        layout=QVBoxLayout(self); self.player=None
        if media.kind=='image':
            self.image=QPixmap(media.path); self.display=QLabel(); self.display.setAlignment(Qt.AlignCenter); layout.addWidget(self.display,1)
        else:
            self.player=QMediaPlayer(self); self.output=QAudioOutput(self); self.player.setAudioOutput(self.output)
            if media.kind=='audio':
                label=QLabel('♪\n'+media.name); label.setAlignment(Qt.AlignCenter); layout.addWidget(label,1)
            else:
                video=QVideoWidget(); self.player.setVideoOutput(video); layout.addWidget(video,1)
            bar=QHBoxLayout(); self.play=QPushButton('Play'); self.play.clicked.connect(self.toggle); bar.addWidget(self.play)
            self.seek=QSlider(Qt.Horizontal); self.seek.setRange(0,0); bar.addWidget(self.seek,1)
            self.time=QLabel('0:00'); bar.addWidget(self.time); layout.addLayout(bar)
            self.seek.sliderMoved.connect(self.player.setPosition)
            self.player.durationChanged.connect(lambda value:self.seek.setRange(0,value))
            self.player.positionChanged.connect(self.position)
            self.player.playbackStateChanged.connect(lambda state:self.play.setText('Pause' if state==QMediaPlayer.PlayingState else 'Play'))
            self.player.errorOccurred.connect(lambda *_:self.time.setText(self.player.errorString()))
            set_media_source(self.player,QUrl.fromLocalFile(media.path))
        layout.addWidget(QLabel(' · '.join(metadata(media)[1:])))
        for widget in [self,*self.findChildren(QLabel),*self.findChildren(QPushButton),*self.findChildren(QSlider),*self.findChildren(QVideoWidget)]:widget.installEventFilter(self)
    def showEvent(self,event):
        super().showEvent(event); self.raise_(); self.activateWindow(); self.setFocus(Qt.OtherFocusReason)
        if self.player:self.player.play()
    def eventFilter(self,watched,event):
        if event.type()==QEvent.ShortcutOverride and event.key()==Qt.Key_Space:event.accept(); return True
        if event.type()==QEvent.KeyPress and event.key()==Qt.Key_Space:
            if self.player and not event.isAutoRepeat():self.toggle()
            event.accept(); return True
        if event.type()==QEvent.KeyRelease and event.key()==Qt.Key_Space:event.accept(); return True
        return super().eventFilter(watched,event)
    def done(self,result):
        if self.player:self.player.stop(); set_media_source(self.player,QUrl())
        owner=getattr(self.parentWidget(),'window',None)
        super().done(result)
        if owner:
            owner.activateWindow(); owner.timeline.viewport().setFocus(Qt.OtherFocusReason)
    def toggle(self):
        self.player.pause() if self.player.playbackState()==QMediaPlayer.PlayingState else self.player.play()
    def position(self,value):
        if not self.seek.isSliderDown():self.seek.setValue(value)
        seconds=value//1000; self.time.setText(f'{seconds//60}:{seconds%60:02d}')
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'image'):self.display.setPixmap(self.image.scaled(max(1,self.width()-30),max(1,self.height()-60),Qt.KeepAspectRatio,Qt.SmoothTransformation))
    def closeEvent(self,event):
        if self.player:self.player.stop(); set_media_source(self.player,QUrl())
        super().closeEvent(event)
