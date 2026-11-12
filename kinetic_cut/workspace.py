"""Edit / Deliver workspace with independently collapsible native Qt panels."""
import copy
import json
import math
import re
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from .theme_widgets import ui_color
from PySide6.QtCore import Qt,QSize,QMimeData,QRectF,QPoint,QUrl,QEvent,QTimer,Slot
from PySide6.QtGui import QIcon,QDrag,QColor,QPainter,QFont,QPen,QPixmap,QImage,QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QSplitter,QStackedWidget,QListWidget,QListWidgetItem,QTreeWidget,QTreeWidgetItem,QAbstractItemView,
    QToolButton,QPushButton,QButtonGroup,QSlider,QCheckBox,QStatusBar,QInputDialog,QMenu,QFileDialog,
    QProgressBar,QMessageBox,QAbstractButton,QDialog,QTabBar,QSizePolicy)
from .config import DATA_DIR
from .controls import SafeComboBox,SafeDoubleSpinBox,SafeSlider
from .small_controls import PanelSearch, CopyTimecodeLabel
from .icons import lucide_icon
from .model import MediaItem
from .widgets import MediaList,PreviewCanvas
from .timeline import TimelineWidget
from .properties import PropertiesPanel,scroll
from .exporter import ExportPreset,estimate,export
from .effects import CATALOG, DESCRIPTIONS, CATEGORY_STYLE, EFFECT_ICONS
from . import binclips


class BackgroundTasks(QDialog):
    history_limit = 10
    statuses = {
        'Queued': 'activity', 'Running': 'activity', 'Completed': 'check',
        'Failed': 'badge-alert', 'Cancelled': 'badge-alert',
    }
    labels = {
        'waveform': 'Generate audio waveform', 'wave_image': 'Generate audio waveform',
        'extract_frame': 'Extract preview frame', 'video_codec': 'Inspect video codec',
        'generate_proxy': 'Prepare preview proxy', 'probe': 'Inspect media',
        'check': 'Check for updates', 'publish_write': 'Publish media preview',
        'next_job': 'Render video', 'render_asset': 'Render compound clip',
        'index_folders': 'Index watched folders', 'scan': 'Scan projects',
        'do_download': 'Download media', 'synthesize_speech': 'Synthesize dialogue',
    }

    def __init__(self, owner):
        super().__init__(owner, Qt.Tool)
        self.setWindowTitle('Background tasks')
        self.resize(340, 310)
        self.active = {}
        self.history = deque(maxlen=self.history_limit)
        layout = QVBoxLayout(self)
        self.summary = QLabel(self)
        self.rows = QListWidget(self)
        self.rows.setAccessibleName('Background tasks')
        self.rows.setSelectionMode(QAbstractItemView.NoSelection)
        self.rows.setWordWrap(True)
        self.clear_button = QPushButton('Clear history', self)
        self.clear_button.setToolTip('Remove finished tasks from this list')
        self.clear_button.clicked.connect(self.clear_history)
        layout.addWidget(self.summary)
        layout.addWidget(self.rows, 1)
        layout.addWidget(self.clear_button, 0, Qt.AlignRight)

    @classmethod
    def task_name(cls, worker):
        if label := getattr(worker, 'task_label', ''):
            return label
        name = getattr(worker.function, '__qualname__', '')
        name = name.split('.<locals>.')[0].split('.')[-1]
        name = name.removeprefix('call_').strip('_')
        if not name or name.startswith('<'):
            return 'Background task'
        return cls.labels.get(name, re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name.replace('_', ' ')).capitalize())

    def add(self, worker):
        self.active[worker.signals] = [self.task_name(worker), 'Queued', None]
        worker.signals.started.connect(self.started, Qt.QueuedConnection)
        worker.signals.error.connect(self.failed, Qt.QueuedConnection)
        self.refresh()

    @Slot(float)
    def started(self, timestamp):
        if entry := self.active.get(self.sender()):
            entry[1] = 'Running'
            entry[2] = timestamp
            self.refresh()

    @Slot(str)
    def failed(self, message):
        if entry := self.active.get(self.sender()):
            entry[1] = 'Cancelled' if message == 'Operation cancelled.' else 'Failed'
            self.refresh()

    def finish(self, signals):
        if entry := self.active.pop(signals, None):
            label, state, started_at = entry
            ended_at = getattr(signals, 'task_finished_at', None)
            if ended_at is None:
                ended_at = time.monotonic()
            elapsed = max(0, ended_at - started_at) if started_at is not None else 0
            self.history.appendleft((label, state if state in ('Failed', 'Cancelled') else 'Completed', elapsed))
            self.refresh()

    def clear_history(self):
        self.history.clear()
        self.refresh()

    def refresh(self):
        if not self.isVisible():
            return
        scroll = self.rows.verticalScrollBar().value()
        entries = [(name, state, None) for name, state, _ in self.active.values()]
        entries.extend(list(self.history)[:max(0, self.history_limit - len(entries))])
        self.rows.clear()
        for name, state, elapsed in entries:
            icon = lucide_icon(self.statuses[state], ui_color('text_sub').name(), 16)
            text = f'{name}  ·  {state}'
            if elapsed is not None:
                if elapsed >= 60:
                    minutes, seconds = divmod(int(elapsed), 60)
                    text += f'  ·  {minutes}m {seconds:02d}s'
                else:
                    text += f'  ·  {elapsed:.1f}s'
            self.rows.addItem(QListWidgetItem(icon, text))
        self.rows.verticalScrollBar().setValue(scroll)
        self.summary.setText('Active tasks and recent history' if entries else 'No background tasks yet')
        self.clear_button.setEnabled(bool(self.history))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        button = self.parentWidget().job_status
        corner = button.mapToGlobal(QPoint(button.width(), 0))
        area = button.screen().availableGeometry()
        self.move(max(area.left(), corner.x() - self.width()), max(area.top(), corner.y() - self.height() - 8))
        self.show()
        self.raise_()


class PowerBins:
    def __init__(self,path=None):
        self.path=Path(path) if path else DATA_DIR/"powerbins.json"
        try:self.data=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError):self.data={"folders":["Master"],"media":[]}
    def save(self):
        pending=self.path.with_suffix(".tmp"); pending.write_text(json.dumps(self.data,indent=2),encoding="utf-8"); pending.replace(self.path)
    def add_folder(self,name):
        if name not in self.data["folders"]:self.data["folders"].append(name); self.save()
    def child_folders(self,parent):
        prefix=parent.rstrip("/")+"/"
        return sorted((folder for folder in self.data["folders"] if folder.startswith(prefix) and "/" not in folder[len(prefix):]),key=lambda value:value.casefold())
    def rename_folder(self,folder,new_name):
        if folder=="Master" or not new_name.strip():return folder
        parent=folder.rsplit("/",1)[0] if "/" in folder else ""
        replacement=(parent+"/" if parent else "")+new_name.strip()
        if replacement in self.data["folders"]:return folder
        self.data["folders"]=[replacement+value[len(folder):] if value==folder or value.startswith(folder+"/") else value for value in self.data["folders"]]
        for entry in self.data["media"]:
            value=entry["folder"]
            if value==folder or value.startswith(folder+"/"):entry["folder"]=replacement+value[len(folder):]
        self.save(); return replacement
    def add(self,media,folder):
        self.data["media"]=[e for e in self.data["media"] if not (e["folder"]==folder and (e["media"]["id"]==media.id if media.timeline_preset else e["media"]["path"]==media.path and not e["media"].get("timeline_preset")))]
        self.data["media"].append({"folder":folder,"media":asdict(media)}); self.save()
    def move(self,media,source_folder,destination):
        if source_folder!="project":self.data["media"]=[e for e in self.data["media"] if not(e["folder"]==source_folder and e["media"]["id"]==media.id)]
        self.add(media,destination)
    def delete_folder(self,folder):
        if folder=='Master' or folder not in self.data['folders']:return False
        inside=lambda value:value==folder or value.startswith(folder+'/')
        self.data['folders']=[f for f in self.data['folders'] if not inside(f)]
        self.data['media']=[e for e in self.data['media'] if not inside(e['folder'])]
        self.save(); return True
    def move_folder(self,folder,destination):
        if folder=='Master' or folder not in self.data['folders'] or destination not in self.data['folders']:return None
        if destination==folder or destination.startswith(folder+'/'):return None
        replacement=destination+'/'+folder.rsplit('/',1)[-1]
        if replacement in self.data['folders']:return None
        self.data['folders']=[replacement+f[len(folder):] if f==folder or f.startswith(folder+'/') else f for f in self.data['folders']]
        for entry in self.data['media']:
            f=entry['folder']
            if f==folder or f.startswith(folder+'/'):entry['folder']=replacement+f[len(folder):]
        self.save(); return replacement


class EffectList(QListWidget):
    def __init__(self):
        super().__init__(); self.setDragEnabled(True); self.setObjectName("effectLibrary"); self.setMouseTracking(True)
        self.setAutoScroll(False); self._effect_press=None
    def mousePressEvent(self,event):
        self._effect_press=event.position().toPoint() if event.button()==Qt.LeftButton and self.itemAt(event.position().toPoint()) else None
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.LeftButton:
            from PySide6.QtWidgets import QApplication
            if self._effect_press is not None and (event.position().toPoint()-self._effect_press).manhattanLength()>=QApplication.startDragDistance():
                self._effect_press=None
                self.startDrag(Qt.CopyAction)
            event.accept(); return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        self._effect_press=None; super().mouseReleaseEvent(event)
    def startDrag(self,_):
        if not self.currentItem() or not self.currentItem().data(Qt.UserRole):return
        name=str(self.currentItem().data(Qt.UserRole))
        from .feature_packs import effect_component, available
        key = effect_component(name)
        if key and not available(key):
            from .component_ui import offer
            offer(self.window_,key); return
        mime=QMimeData()
        mime.setData("application/x-kinetic-effect",name.encode())
        from .transitions import TRANSITION_SET
        if name in TRANSITION_SET:
            mime.setData("application/x-kinetic-transition",name.encode())
        drag=QDrag(self); drag.setMimeData(mime)
        drag.setPixmap(self.viewport().grab(self.visualItemRect(self.currentItem())))
        bars=(self.horizontalScrollBar(),self.verticalScrollBar()); positions=[bar.value() for bar in bars]
        try:drag.exec(Qt.CopyAction)
        finally:
            for bar,value in zip(bars,positions):bar.setValue(value)
    def paintEvent(self,event):
        super().paintEvent(event)
        if getattr(self,'visual_library',False):return
        if self.count():
            for index in range(self.count()):
                item=self.item(index)
                if item.data(Qt.UserRole)=="Headline":
                    painter=QPainter(self.viewport()); painter.setRenderHint(QPainter.Antialiasing)
                    rect=self.visualItemRect(item).adjusted(3,2,-3,-2)
                    painter.setPen(QPen(QColor("#91a7c3" if item.isSelected() else "#08090b"),1)); painter.setBrush(QColor("#ffffff")); painter.drawRoundedRect(rect,3,3)
                    font=painter.font(); font.setBold(True); painter.setFont(font); painter.setPen(QColor("#08090b")); painter.drawText(rect,Qt.AlignCenter,"Headline"); painter.end()
                elif not item.data(Qt.UserRole):
                    painter=QPainter(self.viewport()); painter.setRenderHint(QPainter.Antialiasing)
                    rect=self.visualItemRect(item)
                    painter.fillRect(rect,ui_color('bg_panel'))
                    painter.setPen(QPen(ui_color('border_subtle'),1))
                    painter.drawLine(rect.left(),rect.bottom(),rect.right(),rect.bottom())
                    painter.setPen(ui_color('text_sub'))
                    font=painter.font(); font.setBold(True); font.setPointSize(8); painter.setFont(font)
                    painter.drawText(rect.adjusted(10,0,-8,0),Qt.AlignLeft|Qt.AlignVCenter,item.text())
                    painter.end()
            return
        painter=QPainter(self.viewport()); painter.setPen(ui_color('text_sub')); painter.drawText(self.viewport().rect().adjusted(10,10,-10,-10),Qt.AlignCenter|Qt.TextWordWrap,"No matching effects\nTry a different search")


class BinMediaList(MediaList):
    def event(self,event):
        if event.type()==QEvent.ShortcutOverride and event.key()==Qt.Key_Delete:event.accept(); return True
        return super().event(event)
    def __init__(self,panel):
        super().__init__(); self.panel=panel; self.press_position=None; self.dragging=False
        self.bin_drop_hover=False; self.viewport().setAcceptDrops(True); self.viewport().installEventFilter(self)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection); self.setSelectionRectVisible(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel); self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        from .selection_scroll import PoolMarquee
        self.marquee_controller=PoolMarquee(self)
    def paintEvent(self,event):
        super().paintEvent(event)
        if getattr(self,'folder_hover_rect',None):
            painter=QPainter(self.viewport()); painter.setPen(QPen(QColor('#ed806f'),2)); painter.setBrush(QColor(237,128,111,42)); painter.drawRoundedRect(QRectF(self.folder_hover_rect).adjusted(1,1,-1,-1),3,3); painter.end()
        if self.bin_drop_hover:
            painter=QPainter(self.viewport()); painter.setPen(QPen(QColor("#ed806f"),2)); painter.drawRect(self.viewport().rect().adjusted(2,2,-3,-3)); painter.end()
        if self.count():return
        message="No media in this bin\n\nImport media · Ctrl+I"
        if self.panel.is_watch():message="Media added to this folder will appear here automatically."
        painter=QPainter(self.viewport()); painter.setPen(ui_color('text_sub')); painter.drawText(self.viewport().rect().adjusted(12,16,-12,-16),Qt.AlignCenter|Qt.TextWordWrap,message)
    def mousePressEvent(self,event):
        if self.marquee_controller.begin(event):self.press_position=None; return
        self.press_position=event.position().toPoint() if event.button()==Qt.LeftButton and self.itemAt(event.position().toPoint()) else None
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.marquee_controller.move(event.position()):event.accept(); return
        from PySide6.QtWidgets import QApplication
        if not self.dragging and self.press_position is not None and event.buttons()&Qt.LeftButton and (event.position().toPoint()-self.press_position).manhattanLength()>=QApplication.startDragDistance():
            self.dragging=True; self.press_position=None
            try:self.startDrag(Qt.CopyAction)
            finally:self.dragging=False
            return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        self.press_position=None
        if self.marquee_controller.anchor is not None:self.marquee_controller.stop(); event.accept(); return
        super().mouseReleaseEvent(event)
    def wheelEvent(self,event):
        super().wheelEvent(event)
        if self.marquee_controller.anchor is not None:self.marquee_controller.move(event.position())
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Delete:
            folders=[i.data(Qt.UserRole+2) for i in self.selectedItems() if i.data(Qt.UserRole+1)=='folder']
            if folders:self.panel.delete_folders(folders)
            else:self.panel.remove_selected()
            event.accept(); return
        if event.key()==Qt.Key_Escape and self.marquee_controller.anchor is not None:self.marquee_controller.stop(); event.accept(); return
        super().keyPressEvent(event)
    def hideEvent(self,event):self.marquee_controller.stop(); super().hideEvent(event)
    def clear(self):
        if hasattr(self,'marquee_controller'):self.marquee_controller.stop()
        super().clear()
    def dragEnterEvent(self,event):
        if self.panel.is_watch():event.ignore(); return
        if self.panel.is_bin_move(event.mimeData()):self.panel.highlight_drop(self,event); event.acceptProposedAction(); return
        if event.mimeData().hasFormat(binclips.MIME):
            self.bin_drop_hover=self.panel.folder!="project" and self.panel.window.current_page==0; self.viewport().update()
            if self.bin_drop_hover:event.acceptProposedAction()
            else:event.ignore()
        else:super().dragEnterEvent(event)
    def dragMoveEvent(self,event):
        if self.panel.is_watch():event.ignore(); return
        if self.panel.is_bin_move(event.mimeData()):self.panel.highlight_drop(self,event); event.acceptProposedAction(); return
        if event.mimeData().hasFormat(binclips.MIME):self.dragEnterEvent(event); self.panel.highlight_drop(self,event)
        else:super().dragMoveEvent(event)
    def dropEvent(self,event):
        if self.panel.is_watch():event.ignore(); return
        self.folder_hover_rect=None; self.viewport().update()
        if self.panel.is_bin_move(event.mimeData()):
            item=self.itemAt(event.position().toPoint()); folder=item.data(Qt.UserRole+2) if item and item.data(Qt.UserRole+1)=='folder' else self.panel.folder
            changed=self.panel.import_to_master(event.mimeData()) if folder=='project' else self.panel.move_drop(event.mimeData(),folder)
            if changed:event.acceptProposedAction()
            else:event.ignore()
            return
        if event.mimeData().hasFormat(binclips.MIME):
            self.bin_drop_hover=False; self.viewport().update()
            item=self.itemAt(event.position().toPoint()); folder=item.data(Qt.UserRole+2) if item and item.data(Qt.UserRole+1)=="folder" else self.panel.folder
            if self.panel.store_timeline_drop(event.mimeData(),folder):event.acceptProposedAction()
            else:event.ignore()
        else:super().dropEvent(event)
    def eventFilter(self,watched,event):
        # QListView's internal-model drop handling must not reject our external
        # timeline snapshot before it reaches the visible Power Bin drop zone.
        if watched is self.viewport():
            if event.type()==QEvent.DragLeave:
                self.folder_hover_rect=None; self.bin_drop_hover=False; self.viewport().update()
            elif event.type() in {QEvent.DragEnter,QEvent.DragMove,QEvent.Drop} and (event.mimeData().hasFormat(binclips.MIME) or self.panel.is_bin_move(event.mimeData())):
                {QEvent.DragEnter:self.dragEnterEvent,QEvent.DragMove:self.dragMoveEvent,QEvent.Drop:self.dropEvent}[event.type()](event); return True
        return super().eventFilter(watched,event)
    def startDrag(self,actions):
        folders=[i.data(Qt.UserRole+2) for i in self.selectedItems() if i.data(Qt.UserRole+1)=='folder' and i.data(Qt.UserRole+2)]
        if folders:
            self.panel.drag_folders(self,folders); return
        items=self.panel.selected_media_items()
        if not items:return
        ids=[self.panel.materialize(item.data(Qt.UserRole)) for item in items]; ids=[id for id in ids if self.panel.resolve_media(id)]
        if not ids:return
        item=items[0]; media_id=ids[0]; media=self.panel.resolve_media(media_id)
        mime=QMimeData(); mime.setData("application/x-kinetic-media-id",media_id.encode()); mime.setData("application/x-kinetic-media-ids",json.dumps(ids).encode())
        mime.setData("application/x-kinetic-power-source",json.dumps({"folder":self.panel.folder,"path":media.path,"ids":[i.data(Qt.UserRole) for i in items]}).encode())
        drag=QDrag(self); drag.setMimeData(mime); drag.setPixmap(item.icon().pixmap(100,65)); drag.exec(Qt.CopyAction)


class PowerFolderTree(QTreeWidget):
    def drawBranches(self,painter,rect,index):
        # Theme styles can omit the native disclosure glyph; retain Qt's
        # existing branch hit area and expansion behavior with a small chevron.
        if not self.model().hasChildren(index):return
        x=rect.right()-self.indentation()/2; y=rect.center().y()
        painter.save();painter.setPen(QPen(QColor(ui_color('text_sub')),1));painter.setRenderHint(QPainter.Antialiasing)
        if self.isExpanded(index):
            painter.drawLine(round(x-2),round(y-1),round(x),round(y+1));painter.drawLine(round(x),round(y+1),round(x+2),round(y-1))
        else:
            painter.drawLine(round(x-1),round(y-2),round(x+1),round(y));painter.drawLine(round(x+1),round(y),round(x-1),round(y+2))
        painter.restore()
    def paintEvent(self,event):
        super().paintEvent(event)
        if getattr(self,'folder_hover_rect',None):
            painter=QPainter(self.viewport()); painter.setPen(QPen(QColor('#ed806f'),2)); painter.setBrush(QColor(237,128,111,42)); painter.drawRoundedRect(QRectF(self.folder_hover_rect).adjusted(1,1,-1,-1),3,3); painter.end()
    def dragLeaveEvent(self,event):
        self.folder_hover_rect=None; self.viewport().update(); super().dragLeaveEvent(event)
    def event(self,event):
        if event.type()==QEvent.ShortcutOverride and event.key()==Qt.Key_Delete:event.accept(); return True
        return super().event(event)
    def __init__(self,panel):
        super().__init__(); self.setStyleSheet("QTreeWidget#powerFolderTree { padding-left: 6px; }"); self.panel=panel; self.setAcceptDrops(True); self.viewport().setAcceptDrops(True); self.setDropIndicatorShown(True)
        self.setDragEnabled(True); self.setSelectionMode(QAbstractItemView.ExtendedSelection)
    def startDrag(self,actions):self.panel.drag_folders(self,[i.data(0,Qt.UserRole) for i in self.selectedItems()])
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Delete:self.panel.delete_folders([i.data(0,Qt.UserRole) for i in self.selectedItems()]); event.accept(); return
        super().keyPressEvent(event)
    def dragEnterEvent(self,event):
        if self.panel.is_bin_move(event.mimeData()) or event.mimeData().hasFormat(binclips.MIME):event.acceptProposedAction()
    def dragMoveEvent(self,event):
        self.panel.highlight_drop(self,event,True)
        item=self.itemAt(event.position().toPoint())
        if item and item.data(0,Qt.UserRole):event.acceptProposedAction()
        else:event.ignore()
    def dropEvent(self,event):
        self.folder_hover_rect=None; self.viewport().update()
        item=self.itemAt(event.position().toPoint())
        if not item:return
        if event.mimeData().hasFormat(binclips.MIME):
            if self.panel.store_timeline_drop(event.mimeData(),item.data(0,Qt.UserRole)):event.acceptProposedAction()
            return
        if self.panel.move_drop(event.mimeData(),item.data(0,Qt.UserRole)):event.acceptProposedAction()


class ProjectFolderTree(QTreeWidget):
    """Master accepts reference imports; watch rows never write into disk folders."""
    def __init__(self,panel):
        super().__init__(panel); self.panel=panel
        self.setAcceptDrops(True); self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat('application/x-kinetic-media-id') and self.panel.window.current_page==0:event.acceptProposedAction()
        else:event.ignore()
    def dragMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if item and item.data(0,Qt.UserRole)=='project':self.dragEnterEvent(event)
        else:event.ignore()
    def dropEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if item and item.data(0,Qt.UserRole)=='project' and self.panel.import_to_master(event.mimeData()):event.acceptProposedAction()
        else:event.ignore()


class MediaPanel(QWidget):
    def __init__(self,window):
        super().__init__(); self.window=window; self.power=PowerBins(); self.folder="project"
        from .watch_folders import WatchFolders
        self.watch_folders=WatchFolders(self)
        self._thumbnail_rebuild_paths={}; self._thumbnail_view_indexes={}; self._thumbnail_inflight=set(); self._thumbnail_rebuild_failed=set(); self._thumbnail_rebuild_busy=False; self._thumbnail_rebuild_scheduled=False
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        header=QHBoxLayout()
        self.source_tabs=QTabBar(); self.source_tabs.addTab('Project'); self.source_tabs.addTab('Power Bins'); self.source_tabs.setExpanding(False); self.source_tabs.setDrawBase(False)
        header.addWidget(self.source_tabs); header.addStretch()
        from .pool_tools import set_view,AudioThumbnails,GALLERY_CARD,GALLERY_ART
        self.audio_thumbnails=AudioThumbnails(self)
        self.view_button=QToolButton(); self.view_button.clicked.connect(lambda:set_view(self,not self.list_view)); header.addWidget(self.view_button)
        from .ui import tool_button
        header.addWidget(tool_button("folder-open",window.import_media,"Import media · Ctrl+I")); header.addWidget(tool_button("search",self.toggle_search,"Search media")); root.addLayout(header)
        self.search=PanelSearch(); self.search.setPlaceholderText("Search file name"); self.search.hide(); self.search.textChanged.connect(self.refresh); self.search.dismissed.connect(lambda:self.grid.setFocus()); root.addWidget(self.search)
        self._source_folders={0:'project',1:'Master'}
        split=QSplitter(Qt.Horizontal); navigation=QStackedWidget(); navigation.setMinimumWidth(105); navigation.setMaximumWidth(180)
        self.project_tree=ProjectFolderTree(self); self.project_tree.setObjectName("poolFolderTree"); self.project_tree.setHeaderHidden(True); self.project_tree.setMinimumHeight(65); self.project_tree.itemClicked.connect(self.choose_folder); navigation.addWidget(self.project_tree)
        self.project_tree.setContextMenuPolicy(Qt.CustomContextMenu); self.project_tree.customContextMenuRequested.connect(self.project_context)
        lower=QWidget(); lower.setMinimumHeight(105); lower_layout=QVBoxLayout(lower); lower_layout.setContentsMargins(0,0,0,0); lower_layout.setSpacing(0); lower_layout.addWidget(QLabel("Power Bins",objectName="powerBinsTitle"))
        self.tree=PowerFolderTree(self); self.tree.setObjectName("powerFolderTree"); self.tree.setHeaderHidden(True); self.tree.setIndentation(8); lower_layout.addWidget(self.tree); navigation.addWidget(lower); self.navigation_split=navigation
        self.source_tabs.currentChanged.connect(self.set_source_tab)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context); self.tree.itemClicked.connect(self.choose_folder)
        split.addWidget(navigation)
        self.grid=BinMediaList(self); self.grid.setViewMode(QListWidget.IconMode); self.grid.setResizeMode(QListWidget.Adjust); self.grid.setMovement(QListWidget.Static); self.grid.setWrapping(True); self.grid.setIconSize(GALLERY_ART); self.grid.setGridSize(GALLERY_CARD); self.grid.setWordWrap(False); self.grid.setTextElideMode(Qt.ElideRight)
        # Static controls icon rearrangement, not permission to drag into the editor.
        self.grid.setDragEnabled(True); self.grid.setDragDropMode(QAbstractItemView.DragDrop)
        # Icon/static layout resets the viewport's drop flag independently of
        # QListWidget.acceptDrops(). Enable the actual visible surface last.
        self.grid.setAcceptDrops(True); self.grid.viewport().setAcceptDrops(True)
        self.grid.filesDropped.connect(window.add_media_paths); self.grid.importRequested.connect(window.import_media); self.grid.addRequested.connect(self.append_item); self.grid.removeRequested.connect(self.remove); self.grid.itemSelectionChanged.connect(window.media_selected)
        self.grid.itemDoubleClicked.connect(self.open_grid_item)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu); self.grid.customContextMenuRequested.connect(self.media_context)
        pool=QWidget(); pool_layout=QVBoxLayout(pool); pool_layout.setContentsMargins(0,0,0,0); pool_layout.setSpacing(0)
        from .pool_tools import setup_view
        setup_view(self,pool)
        self.watch_status=QLabel(pool); self.watch_status.setWordWrap(True); self.watch_status.hide()
        from .theme_widgets import set_ui_style
        set_ui_style(self.watch_status,'color: @text_sub; padding: 4px 8px;')
        pool_layout.addWidget(self.watch_status)
        self.watch_folders.changed.connect(self.watches_changed)
        split.addWidget(pool); split.setSizes([125,300]); root.addWidget(split,1); self.rebuild_tree()
        from .missing_media_ui import MissingMediaController
        self.missing_media=MissingMediaController(self)
    @staticmethod
    def is_bin_move(mime):return mime.hasFormat('application/x-kinetic-media-id') or mime.hasFormat('application/x-kinetic-bin-folders')
    def highlight_drop(self,view,event,tree=False):
        item=view.itemAt(event.position().toPoint()); view.folder_hover_rect=None
        folder=item.data(0,Qt.UserRole) if tree and item else item.data(Qt.UserRole+2) if item and item.data(Qt.UserRole+1)=='folder' else None
        valid=folder in self.power.data['folders'] and self.window.current_page==0
        if valid and event.mimeData().hasFormat('application/x-kinetic-bin-folders'):
            try:
                sources=json.loads(bytes(event.mimeData().data('application/x-kinetic-bin-folders')))
                valid=all(f!='Master' and folder!=f and not folder.startswith(f+'/') and folder+'/'+f.rsplit('/',1)[-1] not in self.power.data['folders'] for f in sources)
            except (TypeError,ValueError):valid=False
        if valid:view.folder_hover_rect=view.visualItemRect(item)
        view.viewport().update()
    def drag_folders(self,source,folders):
        folders=[f for f in folders if f and f!='Master']
        if not folders:return
        mime=QMimeData(); mime.setData('application/x-kinetic-bin-folders',json.dumps(folders).encode())
        drag=QDrag(source); drag.setMimeData(mime); drag.setPixmap(lucide_icon('folder').pixmap(48,48)); drag.exec(Qt.MoveAction)
    def move_drop(self,mime,destination):
        if destination not in self.power.data['folders'] or self.window.current_page!=0:return False
        changed=False
        try:
            if mime.hasFormat('application/x-kinetic-bin-folders'):
                folders=json.loads(bytes(mime.data('application/x-kinetic-bin-folders')))
                folders=[f for f in folders if not any(f.startswith(other+'/') for other in folders if other!=f)]
                for folder in folders:
                    renamed=self.power.move_folder(folder,destination)
                    if renamed:
                        if self.folder==folder or self.folder.startswith(folder+'/'):self.folder=renamed+self.folder[len(folder):]
                        changed=True
            else:
                raw=bytes(mime.data('application/x-kinetic-power-source'))
                source=json.loads(raw) if raw else {'folder':'project'}
                ids=source.get('ids') or (json.loads(bytes(mime.data('application/x-kinetic-media-ids'))) if mime.hasFormat('application/x-kinetic-media-ids') else [bytes(mime.data('application/x-kinetic-media-id')).decode()])
                for id in ids:
                    entry=next((e for e in self.power.data['media'] if e['folder']==source['folder'] and e['media']['id']==id),None)
                    media=MediaItem(**entry['media']) if entry else self.resolve_media(id)
                    if media:self.power.move(media,source['folder'],destination); changed=True
        except (ValueError,TypeError,KeyError):return False
        if changed:self.rebuild_tree(); self.refresh()
        return changed
    def delete_folders(self,folders):
        if self.window.current_page!=0:return
        valid=[f for f in folders if f!='Master' and f in self.power.data['folders']]
        if not valid:return
        if QMessageBox.question(self,'Remove Power Bin folders','Remove the selected folders and all their bin entries? Original source files and timeline clips will not be deleted.')!=QMessageBox.Yes:return
        for folder in valid:
            if self.power.delete_folder(folder) and (self.folder==folder or self.folder.startswith(folder+'/')):self.folder='Master'
        self.rebuild_tree(); self.refresh(); self.window.statusBar().showMessage('Removed Power Bin folders and entries. Source files are unchanged.',6000)
    def rebuild_tree(self):
        self.tree.clear(); self.project_tree.clear(); project=QTreeWidgetItem(["Master"]); project.setData(0,Qt.UserRole,"project"); self.project_tree.addTopLevelItem(project)
        for key,folder in self.watch_folders.folders.items():
            item=QTreeWidgetItem([Path(folder.path).name or folder.path]); item.setData(0,Qt.UserRole,key)
            item.setIcon(0,lucide_icon('folder')); self.project_tree.addTopLevelItem(item)
        self.update_watch_rows()
        nodes={}
        for folder in sorted(self.power.data["folders"]):
            parent=None; pieces=[]
            for piece in folder.split("/"):
                pieces.append(piece); path="/".join(pieces)
                if path not in nodes:
                    item=QTreeWidgetItem([piece]); item.setData(0,Qt.UserRole,path)
                    if path!='Master':item.setIcon(0,lucide_icon('folder'))
                    if parent:parent.addChild(item)
                    else:self.tree.addTopLevelItem(item)
                    nodes[path]=item
                parent=nodes[path]; parent.setExpanded(True)
    def choose_folder(self,item,*_):
        self.folder=item.data(0,Qt.UserRole) or "project"; self.refresh()
        (self.tree if self.folder=="project" or self.is_watch() else self.project_tree).clearSelection()
    def set_source_tab(self,index):
        folder=self._source_folders.get(index,'project' if index==0 else 'Master')
        if index==0 and folder!='project' and folder not in self.watch_folders.folders:folder='project'
        if index==1 and folder not in self.power.data['folders']:folder='Master'
        self.folder=folder; self.refresh()
    def sync_source_tabs(self):
        index=0 if self.folder=='project' or self.is_watch() else 1
        self._source_folders[index]=self.folder
        self.source_tabs.blockSignals(True); self.source_tabs.setCurrentIndex(index); self.source_tabs.blockSignals(False)
        self.navigation_split.setCurrentIndex(index)
    def is_watch(self):return self.folder in self.watch_folders.folders
    def update_watch_rows(self):
        for n in range(self.project_tree.topLevelItemCount()):
            item=self.project_tree.topLevelItem(n); key=item.data(0,Qt.UserRole)
            if key in self.watch_folders.folders:
                folder=self.watch_folders.folders[key]
                item.setToolTip(0,folder.path+'\n'+self.watch_folders.status(key)+'\nWatches this folder; subfolders are not included.')
            item.setSelected(key==self.folder)
    def watches_changed(self):
        self.update_watch_rows()
        if self.is_watch() and not self.grid.dragging:
            folder=self.watch_folders.folders[self.folder]
            signature=(self.folder,self.watch_folders.status(self.folder),tuple((m.id,m.path,m.thumbnail,m.duration,m.width,m.height) for m in folder.media()))
            if signature!=getattr(self,'_watch_view_signature',None):self.refresh(preserve=True)
    def project_context(self,pos):
        target=self.project_tree.itemAt(pos); key=target.data(0,Qt.UserRole) if target else None
        menu=QMenu(self)
        if target is None:menu.addAction(lucide_icon('folder'),'Watch Folder…',self.add_watch_folder)
        if key in self.watch_folders.folders:
            menu.addAction('Remove Watch Folder',lambda:self.remove_watch_folder(key))
        if menu.isEmpty():menu.deleteLater(); return
        menu.popup(self.project_tree.viewport().mapToGlobal(pos)); self._menu=menu
    def add_watch_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Watch Folder')
        if not path:return
        self.folder=self.watch_folders.add(path); self.rebuild_tree(); self.tree.clearSelection(); self.refresh()
    def remove_watch_folder(self,key):
        if self.folder==key:self.folder='project'
        self.watch_folders.remove(key); self.rebuild_tree(); self.refresh()
        self.window.statusBar().showMessage('Stopped watching folder. Source files and imported media are unchanged.',5000)
    def open_watch_folder(self,key):
        folder=self.watch_folders.folders.get(key)
        if folder:QDesktopServices.openUrl(QUrl.fromLocalFile(folder.path))
    def import_to_master(self,mime):
        if self.window.current_page!=0 or not mime.hasFormat('application/x-kinetic-media-id'):return False
        try:
            ids=json.loads(bytes(mime.data('application/x-kinetic-media-ids'))) if mime.hasFormat('application/x-kinetic-media-ids') else [bytes(mime.data('application/x-kinetic-media-id')).decode()]
            assets=[self.resolve_media(id) for id in ids]
        except (ValueError,TypeError):return False
        from .media_insert import source_key
        changed=False
        for asset in assets:
            if not asset or asset.timeline_preset:continue
            existing=next((m for m in self.window.project.media if source_key(m.path)==source_key(asset.path)),None)
            if existing:
                if existing.pool_hidden:existing.pool_hidden=False; changed=True
            else:
                media=copy.deepcopy(asset); self.window.project.add_media(media)
                changed=True
        if changed:self.window.model_changed(); self.window.refresh_media()
        return any(asset and not asset.timeline_preset for asset in assets)
    def toggle_search(self):self.search.toggle()
    def refresh(self,*_,preserve=False):
        self.sync_source_tabs()
        self.audio_thumbnails.pending.clear()
        for path in self._thumbnail_view_indexes:self._thumbnail_rebuild_paths.pop(path,None)
        self._thumbnail_view_indexes.clear()
        if getattr(self,'_thumbnail_rebuild_project',None) is not self.window.project:
            self._thumbnail_rebuild_project=self.window.project
            cancel=getattr(self,'_thumbnail_rebuild_cancel',None)
            if cancel:cancel.set()
            self._thumbnail_rebuild_paths.clear()
            # A previous project's transient failure must not suppress rebuilding
            # forever when the user returns to a now-readable source.
            self._thumbnail_rebuild_failed.clear()
            view=(self.folder,self.search.text())
            if preserve and self.folder!='project' and not self.is_watch() and getattr(self,'_displayed_view',None)==view:
                self.grid.viewport().update()
                return
        self._displayed_view=(self.folder,self.search.text())
        selected={i.data(Qt.UserRole) for i in self.grid.selectedItems()} if preserve else set()
        current=self.grid.currentItem(); primary=current.data(Qt.UserRole) if current and preserve else None
        scroll=self.grid.verticalScrollBar().value(); horizontal=self.grid.horizontalScrollBar().value()
        self.grid.blockSignals(True); self.grid.clear(); media=[m for m in self.window.project.media if not m.timeline_preset and not m.pool_hidden]
        watching=self.is_watch(); self.watch_status.setVisible(watching)
        if watching:
            media=self.watch_folders.folders[self.folder].media()
            self.watch_status.setText(self.watch_folders.status(self.folder)); self.watch_status.setToolTip(self.watch_folders.folders[self.folder].path)
            self._watch_view_signature=(self.folder,self.watch_status.text(),tuple((m.id,m.path,m.thumbnail,m.duration,m.width,m.height) for m in media))
        else:self._watch_view_signature=None
        if not watching and self.folder!="project":
            media=[MediaItem(**e["media"]) for e in self.power.data["media"] if e["folder"]==self.folder]
            for folder in self.power.child_folders(self.folder):
                name=folder.rsplit("/",1)[-1]; item=QListWidgetItem(name); item.setToolTip("Power Bin folder · double-click to open")
                item.setData(Qt.UserRole+1,"folder"); item.setData(Qt.UserRole+2,folder); item.setIcon(lucide_icon("folder","#aeb1b8",58)); self.grid.addItem(item)
        media=sorted(media,key=lambda value:value.name.casefold())
        for m in media:
            if self.search.text().casefold() not in m.name.casefold():continue
            # Power-bin files remain available to the current project on use.
            item=QListWidgetItem(m.name); item.setToolTip(m.path); item.setData(Qt.UserRole,m.id)
            item.setData(Qt.UserRole+1,"media")
            from .pool_tools import metadata
            item.setData(Qt.UserRole+3,metadata(m))
            from .missing_media import is_missing,label
            if is_missing(m):
                item.setText(label(m)); item.setForeground(QColor('#e5574b')); item.setToolTip(label(m)+'\n'+m.path)
                values=metadata(m); values[0]=label(m); item.setData(Qt.UserRole+3,values); item.setData(Qt.UserRole+4,True)
            elif m.kind=='audio':
                item.setData(Qt.UserRole+5,m.path)
            elif m.kind in ('image','video') and not m.timeline_preset:
                item.setData(Qt.UserRole+6,m)
            item.setIcon(self.media_icon(m,queue=False))
            self.grid.addItem(item)
            if preserve:
                if m.id==primary:self.grid.setCurrentItem(item)
                item.setSelected(m.id in selected)
        self.grid.blockSignals(False)
        if preserve:
            self.grid.doItemsLayout()
            self.grid.verticalScrollBar().setValue(scroll); self.grid.horizontalScrollBar().setValue(horizontal)
    def media_icon(self,media,queue=True):
        from .missing_media import is_missing,offline_icon
        if is_missing(media):return offline_icon(media.kind=='audio')
        if queue:self._request_thumbnail(media)
        if not media.thumbnail and media.kind in ('image','video'):
            from .media import cached_thumbnail
            media.thumbnail=cached_thumbnail(media.path,media.kind)
        if media.kind=="image" and media.thumbnail and Path(media.thumbnail).is_file():
            if not hasattr(self, '_image_icon_cache'):
                self._image_icon_cache = {}
            cache_key = (media.id, media.path, media.thumbnail)
            if cache_key in self._image_icon_cache:
                return self._image_icon_cache[cache_key]
            source=QImage(media.thumbnail); canvas=QPixmap(110,65); canvas.fill(QColor("#08090b"))
            fitted=source.scaled(110,65,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            painter=QPainter(canvas); painter.drawImage((110-fitted.width())//2,(65-fitted.height())//2,fitted); painter.end()
            icon = QIcon(canvas)
            self._image_icon_cache[cache_key] = icon
            return icon
        return QIcon(media.thumbnail) if media.thumbnail and Path(media.thumbnail).exists() else lucide_icon("music-2" if media.kind=="audio" else "captions" if media.kind in {"title","caption"} else "layers")

    def _request_thumbnail(self,media,index=None):
        if media.kind not in ('image','video'):return
        if not media.thumbnail or not Path(media.thumbnail).is_file():
            from .media import planned_thumbnail
            media.thumbnail=planned_thumbnail(media.path,media.kind)
        if Path(media.path).is_file() and (not media.thumbnail or not Path(media.thumbnail).is_file()):
            if media.path not in self._thumbnail_rebuild_failed and media.path not in self._thumbnail_inflight:
                self._thumbnail_rebuild_paths[media.path]=media.kind
                if index is not None:self._thumbnail_view_indexes[media.path]=index
                if not self._thumbnail_rebuild_scheduled and not self._thumbnail_rebuild_busy:
                    self._thumbnail_rebuild_scheduled=True
                    QTimer.singleShot(0,self._start_thumbnail_rebuild)

    def _start_thumbnail_rebuild(self):
        self._thumbnail_rebuild_scheduled=False
        import shiboken6
        def live():return shiboken6.isValid(self) and shiboken6.isValid(self.window) and not getattr(self.window,'_closing',False)
        if not live() or self._thumbnail_rebuild_busy or not self._thumbnail_rebuild_paths:return
        import threading,logging
        from .ui import Worker
        from .media import make_thumbnail
        for path,index in tuple(self._thumbnail_view_indexes.items()):
            if not (self.grid.isVisible() and index.isValid() and self.grid.viewport().rect().intersects(self.grid.visualItemRect(self.grid.item(index.row())))):
                self._thumbnail_view_indexes.pop(path,None)
                self._thumbnail_rebuild_paths.pop(path,None)
        batch=list(self._thumbnail_rebuild_paths.items())[:4]
        if not batch:return
        for path,_ in batch:
            self._thumbnail_rebuild_paths.pop(path,None)
            self._thumbnail_view_indexes.pop(path,None)
        self._thumbnail_inflight={path for path,_ in batch}
        self._thumbnail_rebuild_busy=True
        cancel=threading.Event()
        self._thumbnail_rebuild_cancel=cancel
        self._thumbnail_rebuild_project=self.window.project
        ffmpeg=self.window.settings.get('ffmpeg','ffmpeg')
        def work():
            results=[]
            for path,kind in batch:
                if cancel.is_set():raise InterruptedError('Thumbnail generation cancelled')
                try:thumbnail=make_thumbnail(path,kind,ffmpeg,timeout=20,cancel_check=cancel.is_set)
                except InterruptedError:raise
                except Exception:
                    logging.exception('Could not rebuild media thumbnail: %s',path)
                    thumbnail=''
                results.append((path,thumbnail))
            return results
        def done(results):
            if cancel.is_set() or not live():return
            power_changed=False
            for path,thumbnail in results:
                if not thumbnail:
                    self._thumbnail_rebuild_failed.add(path); continue
                for media in self.window.project.media:
                    if media.path==path:media.thumbnail=thumbnail
                for entry in self.power.data['media']:
                    if entry['media'].get('path')==path:
                        entry['media']['thumbnail']=thumbnail; power_changed=True
            if power_changed:self.power.save()
            self.refresh(preserve=True)
            self.window.timeline.refresh_thumbnails()
        def failed(_):
            if not cancel.is_set() and live():self._thumbnail_rebuild_failed.update(path for path,_ in batch)
        def finished():
            self._thumbnail_rebuild_busy=False
            self._thumbnail_inflight.clear()
            if self._thumbnail_rebuild_paths and live():self._start_thumbnail_rebuild()
        worker=Worker(work);worker.cancel_callback=cancel.set
        worker.signals.result.connect(done);worker.signals.error.connect(failed);worker.signals.finished.connect(finished);self.window.start_worker(worker)
    def displayed_media(self,item):
        id=item.data(Qt.UserRole)
        if self.is_watch():return self.watch_folders.resolve(id)
        if self.folder=="project":return self.window.project.media_by_id(id)
        entry=next((e for e in self.power.data["media"] if e["folder"]==self.folder and e["media"]["id"]==id),None)
        return MediaItem(**entry["media"]) if entry else None
    def rename_media(self,item):
        if self.is_watch():return
        media=self.displayed_media(item)
        if not media:return
        name,ok=QInputDialog.getText(self,"Rename Media","Display name (source file is unchanged)",text=media.name)
        if not ok or not name.strip():return
        if self.folder=="project":media.name=name.strip(); self.window.model_changed()
        else:
            for entry in self.power.data["media"]:
                if entry["folder"]==self.folder and entry["media"]["id"]==media.id:entry["media"]["name"]=name.strip()
            self.power.save()
        self.refresh()
    def open_file_location(self,item):
        media=self.displayed_media(item)
        if not media or not media.path:return
        parent=Path(media.path).resolve().parent
        if parent.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))
        else:self.window.statusBar().showMessage("The source folder could not be found.",4000)
    def power_bin_target(self,global_position):
        if not self.isVisible():return None
        point=self.tree.viewport().mapFromGlobal(global_position)
        if self.tree.isVisible() and self.tree.viewport().rect().contains(point):
            item=self.tree.itemAt(point); return item.data(0,Qt.UserRole) if item else "Master"
        point=self.grid.viewport().mapFromGlobal(global_position)
        if self.folder!="project" and not self.is_watch() and self.grid.viewport().rect().contains(point):return self.folder
        return None
    def begin_timeline_drag(self,timeline):
        timeline.cancel_drag()
        payload=binclips.snapshot(self.window.project,timeline.selected_ids,timeline.selected_caption_ids,timeline.selected_id)
        if not payload:return
        mime=QMimeData(); mime.setData(binclips.MIME,json.dumps(payload).encode("utf-8"))
        name=binclips.asset(payload).name; label="+  "+name; pix=QPixmap(min(420,30+self.fontMetrics().horizontalAdvance(label)),30); pix.fill(QColor("#25272c"))
        painter=QPainter(pix); painter.setPen(QColor("#f3f5f8")); painter.drawText(pix.rect().adjusted(8,0,-8,0),Qt.AlignVCenter,label); painter.end()
        drag=QDrag(timeline); drag.setMimeData(mime); drag.setPixmap(pix); drag.setHotSpot(QPoint(0,15)); drag.exec(Qt.CopyAction)
    def store_timeline_drop(self,mime,folder):
        if folder=="project" or folder not in self.power.data["folders"] or self.window.page_group.checkedId()!=0:return False
        try:
            payload=json.loads(bytes(mime.data(binclips.MIME))); media=binclips.asset(payload)
            # Validate the serialized edit without changing the current project.
            from .model import Project
            binclips.restore(Project(),media,"video_1",0)
        except (ValueError,KeyError,TypeError):return False
        self.power.add(media,folder); self.refresh()
        self.window.statusBar().showMessage("Saved "+media.name+" to Power Bin with its timeline attributes. Original clips are unchanged.",5500); return True
    def materialize(self,media_id):
        """Resolve an asset reference; selection/dragging never imports a preset."""
        if not media_id:return ""
        p=self.window.project
        media=self.resolve_media(media_id)
        if media and not media.timeline_preset:
            from .media_insert import source_key
            existing=next((m for m in p.media if not m.timeline_preset and source_key(m.path)==source_key(media.path)),None)
            if existing:return existing.id
        return media_id
    def resolve_media(self,media_id):
        media=self.window.project.media_by_id(media_id)
        if media:return media
        media=self.watch_folders.resolve(media_id)
        if media:return media
        entry=next((e for e in self.power.data["media"] if e["media"]["id"]==media_id),None)
        return MediaItem(**entry["media"]) if entry else None
    def on_import(self,items):
        if self.folder!="project" and not self.is_watch():
            for item in items:self.power.add(item,self.folder)
    def context(self,pos):
        target=self.tree.itemAt(pos)
        menu=QMenu(self); menu.addAction("Create Folder…",self.new_folder)
        if target and target.data(0,Qt.UserRole)!="Master":
            folder=target.data(0,Qt.UserRole)
            menu.addAction("Rename Folder…",lambda:self.rename_folder(folder))
            menu.addAction('Delete Folder',lambda:self.delete_folders([folder]))
        menu.popup(self.tree.viewport().mapToGlobal(pos)); self._menu=menu
    def new_folder(self):
        parent=self.folder if self.folder in self.power.data['folders'] else "Master"; name,ok=QInputDialog.getText(self,"New Power Bin","Folder name")
        if ok and name.strip():self.power.add_folder(parent+"/"+name.strip()); self.rebuild_tree(); self.refresh()
    def rename_folder(self,folder):
        old_name=folder.rsplit("/",1)[-1]; name,ok=QInputDialog.getText(self,"Rename Power Bin","Folder name",text=old_name)
        if ok and name.strip():
            renamed=self.power.rename_folder(folder,name)
            if self.folder==folder:self.folder=renamed
            elif self.folder.startswith(folder+"/"):self.folder=renamed+self.folder[len(folder):]
            self.rebuild_tree(); self.refresh()
    def open_grid_item(self,item):
        if item.data(Qt.UserRole+1)!="folder":
            media=self.displayed_media(item)
            if media and Path(media.path).is_file():
                from .pool_tools import SourcePreview
                self.window.transport.pause(); dialog=SourcePreview(self,media); dialog.show()
            return
        self.folder=item.data(Qt.UserRole+2); self.refresh()
    def media_context(self,pos):
        menu=QMenu(self); menu.addAction("Import Media…",self.window.import_media); item=self.grid.itemAt(pos)
        if item and not item.isSelected():self.grid.clearSelection(); item.setSelected(True); self.grid.setCurrentItem(item)
        selected=self.selected_media_items()
        from .missing_media import is_missing
        target=self.displayed_media(item) if item and item.data(Qt.UserRole+1)=='media' else None
        if self.is_watch():
            key=self.folder
            menu.clear(); menu.addAction('Open Folder in Explorer',lambda:self.open_watch_folder(key))
            menu.addAction('Refresh Folder',self.watch_folders.schedule)
            menu.popup(self.grid.viewport().mapToGlobal(pos)); self._menu=menu; return
        if target and is_missing(target):
            menu.clear()
            menu.addAction('Remove from '+('Media Pool' if self.folder=='project' else 'Power Bin'),self.remove_selected)
            menu.addAction('Change replacement file…',lambda:self.missing_media.choose_file(target))
            menu.addAction('Change source folder of all missing items…',self.missing_media.choose_folder)
            menu.popup(self.grid.viewport().mapToGlobal(pos)); self._menu=menu; return
        if self.folder!="project":menu.addAction("Create Folder…",self.new_folder)
        if item and item.data(Qt.UserRole+1)=="folder":
            folder=item.data(Qt.UserRole+2); menu.addAction("Open Folder",lambda:self.open_grid_item(item)); menu.addAction("Rename Folder…",lambda:self.rename_folder(folder))
            menu.addAction('Delete Folder',lambda:self.delete_folders([folder]))
        if selected:
            if item and item.data(Qt.UserRole+1)=="media":
                preview_action=menu.addAction('Preview Media',lambda:self.open_grid_item(item)); preview_action.setEnabled(bool(self.displayed_media(item) and Path(self.displayed_media(item).path).is_file()))
                menu.addAction("Rename…",lambda:self.rename_media(item)); location=menu.addAction("Open File Location",lambda:self.open_file_location(item)); location.setEnabled(bool(self.displayed_media(item) and self.displayed_media(item).path))
                if target and not target.compound and not target.timeline_preset:menu.addAction('Change replacement file…',lambda:self.missing_media.choose_file(target))
            menu.addAction(f"Add {len(selected)} selected to Timeline",self.append_selected)
            submenu=menu.addMenu("Add to Power Bin")
            for folder in self.power.data["folders"]:submenu.addAction(folder,lambda f=folder:[self.add_to_power(i,f) for i in self.selected_media_items()])
            menu.addAction(f"Remove {len(selected)} selected from "+("Media Pool" if self.folder=="project" else "Power Bin"),self.remove_selected)
        menu.popup(self.grid.mapToGlobal(pos)); self._menu=menu
    def selected_media_items(self):
        # Stable visible order makes batch placement predictable, including a
        # rubber-band selection. Folders never become timeline clips.
        return [self.grid.item(n) for n in range(self.grid.count()) if self.grid.item(n).isSelected() and self.grid.item(n).data(Qt.UserRole+1)=="media"]
    def append_selected(self):
        ids=[self.materialize(i.data(Qt.UserRole)) for i in self.selected_media_items()]
        self.window.add_media_batch(ids,"",self.window.project.duration)
    def remove_selected(self):
        if getattr(self.window,"current_page",0):return
        if self.is_watch():return
        ids={i.data(Qt.UserRole) for i in self.selected_media_items()}
        from .pool_removal import remove
        remove(self,ids,self.folder)
    def append_item(self,media_id):
        media_id=self.materialize(media_id); p=self.window.project; media=self.resolve_media(media_id)
        if not media:return
        track=(p.audio_tracks if media.kind=="audio" else p.video_tracks)[-1]
        end=max((i.start+i.duration for i in p.timeline if i.track==track),default=0.)
        self.window.add_media_to_track(media_id,track,end)
    def add_to_power(self,item,folder):
        media=self.resolve_media(item.data(Qt.UserRole))
        if media:self.power.add(media,folder)
    def remove(self,id):
        if self.is_watch():return
        from .pool_removal import remove
        remove(self,{id},self.folder)


from .effects_browser import EffectsBrowser


class EffectsPanel(EffectsBrowser):
    def __init__(self, window):
        super().__init__(window, EffectList)


class DeliveryPage:
    def __init__(self,window):
        self.window=window; self.jobs=[]; self.running=False; self.worker=None
        self.settings=QWidget(); root=QVBoxLayout(self.settings); root.addWidget(QLabel("Render Settings — Custom Export",objectName="panelTitle")); body=QWidget(); form=QFormLayout(body)
        from .render_queue import RecentLocations,FixedFormScroll
        self.name=QLineEdit("Untitled Short"); self.location=RecentLocations(window.settings); browse=QPushButton("Browse"); browse.clicked.connect(self.browse)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow("File Name",self.name); form.addRow("Location",self.location); form.addRow("",browse)
        self.codec=SafeComboBox(); self.codec.addItems(["H.264","H.265"]); self.resolution=SafeComboBox(); self.resolution.addItems(["1080 × 1920","720 × 1280"]); self.fps=SafeComboBox(); self.fps.addItems(["60","30"]); self.hardware=SafeComboBox(); self.hardware.addItems(["Auto","NVIDIA","Intel","AMD","CPU"])
        form.addRow("Format",QLabel("MP4")); form.addRow("Codec",self.codec); form.addRow("Encoder",self.hardware); form.addRow("Resolution",self.resolution); form.addRow("Frame Rate",self.fps)
        self.quality=SafeComboBox(); self.quality.addItems(['Automatic quality (recommended)','Custom bitrate'])
        self.quality.setToolTip('Automatic quality preserves detail and lets file size vary. Bitrate controls compression and file size; it is not a render-speed control.')
        form.addRow('Quality',self.quality)
        self.bitrate=SafeDoubleSpinBox(); self.bitrate.setRange(.1,200); self.bitrate.setValue(10); self.bitrate.setSuffix(" Mb/s"); form.addRow("Bitrate",self.bitrate)
        self.bitrate.setEnabled(False);self.bitrate.setToolTip('Video data per second. Higher values usually mean larger files and less compression. Choose Custom bitrate to adjust.')
        self.bitrate.resize(self.bitrate.sizeHint())
        form.setRowVisible(self.bitrate,False)
        self.quality.currentIndexChanged.connect(lambda index:self.bitrate.setEnabled(index==1))
        self.quality.currentIndexChanged.connect(lambda index:form.setRowVisible(self.bitrate,index==1))
        self.burn=QCheckBox("Burn subtitles into video"); self.burn.setChecked(True); form.addRow("",self.burn)
        self.audio=QCheckBox("Export audio"); self.audio.setChecked(True); form.addRow("",self.audio)
        self.estimate=QLabel(); self.estimate.setWordWrap(True); self.estimate.setMinimumWidth(0); form.addRow("Estimate",self.estimate); self.settings_scroll=FixedFormScroll(body); root.addWidget(self.settings_scroll,1)
        self.add=QPushButton("Add to Render Queue"); self.add.clicked.connect(self.add_job); root.addWidget(self.add)
        self.queue=QWidget(); qr=QVBoxLayout(self.queue); qr.addWidget(QLabel("Render Queue",objectName="panelTitle")); self.list=QListWidget(); self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel); qr.addWidget(self.list,1)
        self.progress=QProgressBar(); self.status=QLabel("No jobs queued"); qr.addWidget(self.status); qr.addWidget(self.progress)
        self.render=QPushButton("Render All"); self.render.clicked.connect(self.render_all); qr.addWidget(self.render)
        self.cancel_render=QPushButton("Cancel Render"); self.cancel_render.clicked.connect(self.cancel_current); self.cancel_render.setEnabled(False); qr.addWidget(self.cancel_render)
        self.remove=QPushButton("Remove Selected Job"); self.remove.clicked.connect(self.remove_job); qr.addWidget(self.remove)
        self.list.currentRowChanged.connect(self.update_controls); self.list.itemDoubleClicked.connect(self.job_details)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu); self.list.customContextMenuRequested.connect(self.queue_context)
        self.clock=QTimer(window); self.clock.setInterval(250); self.clock.timeout.connect(self.tick_elapsed)
        self.add.setToolTip("Queue a snapshot of this timeline. Later edits do not change a queued render.")
        self.progress.setValue(0); self.refresh()
        for widget in [self.codec,self.resolution,self.fps,self.hardware]:widget.currentTextChanged.connect(self.refresh_estimate)
        self.bitrate.valueChanged.connect(self.refresh_estimate)
        self.quality.currentIndexChanged.connect(self.refresh_estimate)
    def activate_project(self,project):
        import uuid
        from .render_history import restore
        self.context_id=uuid.uuid4().hex
        active=[j for j in self.jobs if j['state']=='Rendering']
        self.jobs=restore(project.render_history)+active
        # The form belongs to the newly opened document, even when two projects
        # have the same dimensions. A typed output name is never a global default.
        self.name.setText(project.name);self.name.setModified(False)
        from PySide6.QtCore import QSignalBlocker
        controls=[self.codec,self.hardware,self.quality,self.bitrate,self.audio,self.burn]
        blockers=[QSignalBlocker(control) for control in controls]
        self.codec.setCurrentIndex(0);self.hardware.setCurrentText('Auto');self.quality.setCurrentIndex(0)
        self.bitrate.setValue(10);self.bitrate.setEnabled(False);self.audio.setChecked(True);self.burn.setChecked(True)
        del blockers
        # Emit once so the bitrate row visibility follows the restored quality.
        self.quality.currentIndexChanged.emit(0)
        self._project_format=None;self._had_subtitles=True;self.sync_project_settings()
        if not active:
            self.progress.setRange(0,100);self.progress.setValue(0);self.cancel_render.setEnabled(False)
        self.refresh()
    def bind_job(self,job):
        job.setdefault('owner_context',getattr(self,'context_id',''))
        job.setdefault('owner_project',self.window.compounds.root())
        return job
    def history_owner(self,job):
        current=self.window.compounds.root();owner=job.get('owner_project',current)
        same_file=bool(current.path and owner.path and Path(current.path).resolve()==Path(owner.path).resolve() and current.created_at==owner.created_at)
        return current if job.get('owner_context')==getattr(self,'context_id','') or same_file else owner
    def remove_completed_record(self,job):
        if job.get('history_id'):
            from .render_history import remove
            owner=self.history_owner(job);remove(owner,job['history_id'],publish=False);self.publish_history(owner)
    def publish_history(self,owner):
        from .render_history import issue_write,publish_write
        from .ui import Worker
        request=issue_write(owner)
        if request is None:return
        worker=Worker(publish_write,request)
        def ready(success):
            if not success and not self.window.transport.closed:self.window.statusBar().showMessage('Render history changed in this session but could not be written to its project.',7000)
        worker.signals.result.connect(ready);self.window.start_worker(worker)
    def preset(self):
        from .exporter import automatic_bitrate
        from types import SimpleNamespace
        codec='h264' if self.codec.currentIndex()==0 else 'h265'
        automatic=self.quality.currentIndex()==0
        settings=self.window.project.settings;size=self.resolution.currentData() or (settings.width,settings.height)
        target=SimpleNamespace(width=size[0],height=size[1],fps=float(self.fps.currentText() or settings.fps))
        rate=automatic_bitrate(target,codec) if automatic else self.bitrate.value()
        return ExportPreset('Custom Export',codec,rate,192,'Custom','auto' if automatic else 'bitrate')
    def sync_project_settings(self):
        settings=self.window.project.settings; key=(settings.width,settings.height,settings.fps)
        if getattr(self,"_project_format",None)==key:return
        self._project_format=key; self.resolution.blockSignals(True); self.fps.blockSignals(True)
        self.resolution.clear(); self.resolution.addItem(f"Project · {settings.width} × {settings.height}",(settings.width,settings.height))
        smaller=(max(64,round(settings.width/3)*2),max(64,round(settings.height/3)*2))
        self.resolution.addItem(f"Smaller · {smaller[0]} × {smaller[1]}",smaller)
        self.fps.clear(); self.fps.addItems([str(v) for v in sorted({24,25,30,50,60,90,120,144,240,settings.fps},reverse=True)]); self.fps.setCurrentText(str(settings.fps))
        self.resolution.blockSignals(False); self.fps.blockSignals(False); self.refresh_estimate()

    def output_project(self):
        project=copy.deepcopy(self.window.project); size=self.resolution.currentData()
        if size:
            factor=size[0]/project.settings.width
            if factor!=1:
                styles=[project.subtitle_style]+[c.style for c in project.captions]+[i.title_style for i in project.timeline if i.role=="title"]
                seen=set()
                for style in styles:
                    if id(style) in seen:continue
                    seen.add(id(style))
                    for attr in ("size","line_spacing","kerning","outline_width","shadow_x","shadow_y","shadow_blur","background_outline_width","glow_radius"):
                        setattr(style,attr,getattr(style,attr)*factor)
            project.settings.width,project.settings.height=size
        project.settings.fps=float(self.fps.currentText()); return project
    def browse(self):
        path=QFileDialog.getExistingDirectory(self.window,"Export Location",self.location.text())
        if path:self.location.setText(path)
    def refresh_estimate(self,*_):
        p=self.output_project()
        subtitles=any(c.text.strip() and c.end>c.start for c in p.captions)
        self.burn.setEnabled(subtitles); self.burn.setToolTip("Burn subtitle-track text into the video" if subtitles else "No subtitle items in this timeline. Video titles always render.")
        if not subtitles:self.burn.setChecked(False)
        elif not getattr(self,"_had_subtitles",True):self.burn.setChecked(True)
        self._had_subtitles=subtitles
        size,_=estimate(p,self.preset(),self.hardware.currentText()!="CPU")
        self.estimate.setText('Variable file size · automatic quality adapts compression to the video' if self.quality.currentIndex()==0 else f'≈ {size/1024/1024:.1f} MB · render time depends on layers/effects')
    def add_job(self):
        if not self.window.project.timeline:return
        name=self.name.text().strip()
        if not name or any(c in name for c in '<>:"/\\|?*'):return QMessageBox.warning(self.window,"Export name","Enter a valid file name without path characters.")
        output=Path(self.location.text())/(name if name.lower().endswith(".mp4") else name+".mp4")
        if output.exists() and QMessageBox.question(self.window,"Replace output?",f"Replace {output} when this job renders?")!=QMessageBox.Yes:return
        if any(j["output"]==str(output) and j["state"]!="Complete" for j in self.jobs):return QMessageBox.warning(self.window,"Duplicate output","Choose a different file name for this queued job.")
        p=self.output_project()
        self.jobs.append(self.bind_job(dict(project=p,output=str(output),preset=self.preset(),hardware=self.hardware.currentText(),burn=self.burn.isChecked(),audio=self.audio.isChecked(),state="Queued",elapsed=0.))); self.refresh()
    def refresh(self):
        selected=self.list.currentRow(); self.list.clear()
        for index,job in enumerate(self.jobs):
            colors={"Queued":"#bcc9d9","Rendering":"#8dbbe6","Complete":"#8bc6a7","Failed":"#ec998b"}
            color=colors.get(job["state"],"#bcc9d9")
            from .render_queue import RenderJobCard
            item=QListWidgetItem(); item.setData(Qt.AccessibleTextRole,f"Job {index+1} · {job['state']} · {job['output']}"); item.setToolTip(job.get("error") or job["output"]); self.list.addItem(item)
            card=RenderJobCard(job,index+1,self.remove_specific_job); item.setSizeHint(QSize(260,max(104,card.sizeHint().height())+14)); self.list.setItemWidget(item,card)
        self.list.setCurrentRow(max(0,min(selected,len(self.jobs)-1)))
        if not self.running:
            failed=sum(j["state"]=="Failed" for j in self.jobs); completed=sum(j["state"]=="Complete" for j in self.jobs)
            self.status.setText(f"{completed} complete · {failed} failed · {sum(j['state']=='Queued' for j in self.jobs)} queued" if self.jobs else "No jobs queued")
            self.status.setToolTip("Double-click a failed job to see the error. Failed jobs are not retried by Render All." if failed else "")
        self.update_controls()

    def update_controls(self,*_):
        if hasattr(self.window,'page_group'):self.window.page_group.button(0).setEnabled(not self.running)
        index=self.list.currentRow(); selected=self.jobs[index] if 0<=index<len(self.jobs) else None
        self.remove.setEnabled(bool(selected and selected["state"]!="Rendering"))
        self.render.setEnabled(not self.running and any(j["state"]=="Queued" for j in self.jobs))
        self.render.setText("Render All")

    def job_details(self,*_):
        index=self.list.currentRow()
        if not 0<=index<len(self.jobs):return
        job=self.jobs[index]
        box=QMessageBox(self.window); box.setWindowTitle("Render job · "+job["state"]); box.setText(Path(job["output"]).name+"\n"+job["state"])
        box.setInformativeText("The render failed. Review the details, correct the output or media issue, then retry." if job.get("error") else job["output"])
        if job.get("error"):box.setDetailedText(job["error"])
        box.exec()
    def remove_job(self):
        index=self.list.currentRow()
        if 0<=index<len(self.jobs) and self.jobs[index]["state"]!="Rendering":self.remove_completed_record(self.jobs[index]); self.jobs.pop(index); self.refresh()
    def remove_specific_job(self,job):
        index=next((n for n,value in enumerate(self.jobs) if value is job),None)
        if index is not None and job['state']!='Rendering':self.remove_completed_record(job); self.jobs.pop(index); self.refresh()
    def queue_context(self,point):
        item=self.list.itemAt(point)
        if not item:return
        self.list.setCurrentItem(item); job=self.jobs[self.list.row(item)]; menu=QMenu(self.list)
        action=menu.addAction('Open file location',lambda:self.open_job_location(job)); action.setEnabled(job['state']=='Complete')
        action=menu.addAction('Remove from queue',lambda:self.remove_specific_job(job)); action.setEnabled(job['state']!='Rendering')
        menu.addAction('Details…',self.job_details); menu.popup(self.list.viewport().mapToGlobal(point)); self._queue_menu=menu
    def open_job_location(self,job):
        if job['state']!='Complete':return
        folder=Path(job['output']).resolve().parent
        if folder.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:QMessageBox.information(self.window,'Export folder unavailable','The export folder no longer exists: '+str(folder))
    def tick_elapsed(self):
        if self.window.transport.closed:self.clock.stop(); return
        for row,job in enumerate(self.jobs):
            if job['state']=='Rendering':
                widget=self.list.itemWidget(self.list.item(row))
                if widget:widget.update_elapsed()
    def render_all(self):
        if self.running:return
        self.window.transport.pause(); set_page(self.window,1)
        self.running=True; self.render.setEnabled(False); self.next_job()
    def next_job(self):
        job=next((j for j in self.jobs if j["state"]=="Queued"),None)
        if not job:self.running=False; self.clock.stop(); self.refresh(); return
        self.bind_job(job)
        from .ui import Worker
        import threading
        self.render_cancel=threading.Event(); self.cancel_render.setEnabled(True)
        job["state"]="Rendering"; job['started_at']=time.monotonic(); job['elapsed']=0.; self.clock.start(); self.progress.setValue(0); self.refresh(); self.status.setText("Rendering · "+Path(job["output"]).name)
        def run():
            export(job["project"],job["output"],job["preset"],job["burn"],job["hardware"],self.window.settings.get("ffmpeg","ffmpeg"),lambda value,text:self.worker.signals.progress.emit((value,text)),cancel=self.render_cancel,export_audio=job["audio"])
            return job
        self.worker=Worker(run); self.worker.signals.progress.connect(self.render_progress)
        self.worker.signals.result.connect(lambda _:self.complete(job,"Complete")); self.worker.signals.error.connect(lambda detail:self.complete(job,"Failed",detail)); self.window.start_worker(self.worker)
    def render_progress(self,data):
        if self.window.transport.closed:return
        busy=data[0]==0 and ('face/background' in data[1] or 'Checking available' in data[1])
        self.progress.setRange(0,0 if busy else 100)
        if not busy:self.progress.setValue(round(data[0]*100))
        self.status.setText(data[1])
    def complete(self,job,state,error=""):
        if self.window.transport.closed:return
        self.progress.setRange(0,100)
        self.cancel_render.setEnabled(False)
        if getattr(self,'render_cancel',None) and self.render_cancel.is_set():state='Cancelled'; self.running=False
        from .render_queue import elapsed
        job['elapsed']=elapsed(job); job.pop('started_at',None)
        job["state"]=state; job["error"]=error
        if state=="Complete":
            if job.get('owner_context',getattr(self,'context_id',''))==getattr(self,'context_id',''):self.progress.setValue(100)
            from .render_history import add
            owner=self.history_owner(job);add(owner,job,publish=False);self.publish_history(owner)
            try:self.location.remember(Path(job['output']).parent,self.window.settings)
            except OSError:self.window.statusBar().showMessage('Export completed; recent folders could not be saved.',5000)
        if job.get('owner_context',getattr(self,'context_id',''))!=getattr(self,'context_id','') and self.history_owner(job) is not self.window.compounds.root():
            self.jobs=[value for value in self.jobs if value is not job]
            self.progress.setRange(0,100);self.progress.setValue(0)
        if not self.running:self.clock.stop()
        self.refresh()
        if self.running:self.next_job()
    def cancel_current(self):
        if getattr(self,'render_cancel',None):self.render_cancel.set(); self.cancel_render.setEnabled(False); self.status.setText('Cancelling render…')
    def completed(self):
        index=self.list.currentRow(); return self.jobs[index] if 0<=index<len(self.jobs) and self.jobs[index]["state"]=="Complete" else None
    def share(self):
        job=self.completed()
        if not job:return
        from .ui import ExportDialog
        dialog=ExportDialog(job["project"],self.window.settings,self.window); dialog.output=job["output"]; dialog.wireless_share()
        if dialog.share:dialog.share.stop()
        dialog.deleteLater()


def build_workspace(w):
    from .ui import button,tool_button,CaptionPanel
    from .workspace_library import LibraryPanel, LibraryCommand, HEADER_HEIGHT
    central=QWidget(); root=QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0); w.setCentralWidget(central)
    w.edit_actions=[]
    for full_name, lines, icon, callback in (('Generate Captions',('Generate','Captions'),'captions',w.generate_captions),('Generate TTS Dialogue',('Generate','TTS Dialogue'),'mic',w.generate_tts_dialogue),('Download Media',('Download','Media'),'download',w.open_media_downloader)):
        action=LibraryCommand(); action.setText(full_name); action.setAccessibleName(full_name); action.setToolTip(full_name)
        action.setIcon(lucide_icon(icon)); action.setProperty('iconName',icon); action.setIconSize(QSize(18,18))
        action.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); action.setFixedHeight(HEADER_HEIGHT)
        action.setMinimumWidth(max(action.fontMetrics().horizontalAdvance(line) for line in lines)+16)
        action.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed); action.clicked.connect(callback); w.edit_actions.append(action)
    w.header_actions=QWidget(w.menuBar()); w.header_actions_layout=QHBoxLayout(w.header_actions); w.header_actions_layout.setContentsMargins(0,0,4,0); w.header_actions_layout.setSpacing(4)
    w.inspector_toggle=QToolButton(w.header_actions); w.inspector_toggle.setText('Inspector'); w.inspector_toggle.setAccessibleName('Inspector')
    w.inspector_toggle.setIcon(lucide_icon('sliders-horizontal')); w.inspector_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    w.inspector_toggle.setCheckable(True); w.inspector_toggle.setChecked(True); w.inspector_toggle.setProperty('panelToggle',True)
    w.header_actions_layout.addWidget(w.inspector_toggle); w.menuBar().setCornerWidget(w.header_actions,Qt.TopRightCorner)
    w.page_content=QStackedWidget(); root.addWidget(w.page_content,1)
    w.center_split=QSplitter(Qt.Vertical); w.center_split.setObjectName("timelineMainSplit"); w.center_split.setHandleWidth(7); w.center_split.setChildrenCollapsible(False); w.page_content.addWidget(w.center_split)
    w.workspace_split=QSplitter(Qt.Horizontal); w.workspace_split.setChildrenCollapsible(False); w.workspace_split.setHandleWidth(7); w.center_split.addWidget(w.workspace_split)
    w.left_stack=QStackedWidget(); w.left_stack.setMinimumWidth(280); w.workspace_split.addWidget(w.left_stack)
    w.media_panel=MediaPanel(w); w.effects_panel=EffectsPanel(w)
    w.left_panels=LibraryPanel(w,w.media_panel,w.effects_panel,w.edit_actions); w.left_stack.addWidget(w.left_panels)
    w.media_toggle=w.left_panels.buttons['Media']; w.effects_toggle=w.left_panels.buttons['Effects']
    w.media_list=w.media_panel.grid; w.effects_list=w.effects_panel.list
    w.viewer_split=QSplitter(Qt.Horizontal); w.viewer_split.setMinimumHeight(230); w.viewer_split.setChildrenCollapsible(False); w.viewer_split.setHandleWidth(0); w.workspace_split.addWidget(w.viewer_split)
    viewer=QWidget(); viewer.setObjectName("viewerPanel"); vr=QVBoxLayout(viewer); vr.setContentsMargins(0,0,0,0); vr.setSpacing(0)
    w.viewer_header=QWidget(); w.viewer_header.setFixedHeight(HEADER_HEIGHT)
    viewer_header_layout=QVBoxLayout(w.viewer_header); viewer_header_layout.setContentsMargins(0,0,0,0); viewer_header_layout.setSpacing(0); vr.addWidget(w.viewer_header)
    title_row=QHBoxLayout(); title_row.setContentsMargins(8,3,8,0)
    w.project_label=QLabel(w.project.name); w.project_label.setMinimumWidth(0); title_row.addWidget(w.project_label,1)
    w.time_label=CopyTimecodeLabel("00:00:00:00",lambda:w.project.playhead); title_row.addWidget(w.time_label); viewer_header_layout.addLayout(title_row)
    head=QHBoxLayout(); head.setContentsMargins(8,2,8,3); w.viewer_fit=button("Fit",lambda:w.preview.reset_view(),quiet=True); head.addWidget(w.viewer_fit); head.addStretch(); viewer_header_layout.addLayout(head)
    w.preview=PreviewCanvas(); vr.addWidget(w.preview,1)
    from .preview_quality import PreviewQuality
    w.preview_quality=PreviewQuality(w); head.insertWidget(1,w.preview_quality)
    w.preview.transformChanged.connect(w.viewer_transform_changed); w.preview.captionTransformChanged.connect(w.viewer_caption_changed); w.preview.interactionFinished.connect(lambda _:w.model_changed()); w.preview.itemSelected.connect(w.select_item); w.preview.captionSelected.connect(w.select_caption); w.preview.cropRequested.connect(w.frame_source); w.preview.commandRequested.connect(w.viewer_command)
    controls=QHBoxLayout(); controls.addStretch(); controls.addWidget(tool_button("skip-back",lambda:w.seek(max(0,w.project.playhead-1/w.project.settings.fps)),"Previous frame")); controls.addWidget(tool_button("square",w.stop,"Stop · K")); w.play_button=tool_button("play",w.toggle_play,"Play / Pause · Space"); controls.addWidget(w.play_button); controls.addWidget(tool_button("skip-forward",lambda:w.seek(w.project.playhead+1/w.project.settings.fps),"Next frame")); w.loop_button=tool_button("repeat",lambda checked:setattr(w.transport,"loop",checked),"Loop timeline playback",True); controls.addWidget(w.loop_button); controls.addStretch(); vr.addLayout(controls); w.viewer_split.addWidget(viewer)
    tl=QWidget(); tl.setObjectName("timelinePanel"); layout=QVBoxLayout(tl); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0); bar=QHBoxLayout(); bar.setContentsMargins(6,4,14,4)
    w.tool_group=QButtonGroup(w)
    for attr,icon,mode,hint in [("select_tool","mouse-pointer-2","select","Selection · A"),("blade_tool","razor","blade","Cut/Split · B")]:
        b=tool_button(icon,lambda checked=False,m=mode:w.set_timeline_tool(m),hint,True); setattr(w,attr,b); w.tool_group.addButton(b); bar.addWidget(b)
    w.select_tool.setChecked(True)
    w.transform_box_tool=tool_button("box-select",lambda checked:w.preview.set_transform_controls_visible(checked and not w.transport.playing and w.current_page==0),"Show on-screen transform controls",True); w.transform_box_tool.setChecked(True); bar.insertWidget(1,w.transform_box_tool)
    w.crop_tool=tool_button("crop",lambda:w.frame_source(w.timeline.selected_id),"Crop selected clip… · C"); bar.insertWidget(2,w.crop_tool)
    w.auto_layout_tool=tool_button("layers",w.set_auto_layout,"Auto 3-layer layout · new video drops get a blurred background, fitted content and a webcam layer",True); bar.insertWidget(3,w.auto_layout_tool)
    from .timeline_retime_control import TimelineRetimeButton
    w.retime_button=TimelineRetimeButton(w); bar.addWidget(w.retime_button)
    def toggle_links(checked):
        w.timeline.linked_selection=checked
        ids=w.timeline.expanded(w.timeline.selected_ids) if checked else ({w.timeline.selected_id} if w.timeline.selected_id else set())
        w.timeline.select_ids(ids,w.timeline.selected_id)
    w.link_toggle=tool_button("link",toggle_links,"Linked Selection · Ctrl+Shift+L",True); w.link_toggle.setChecked(True)
    w.snap_tool=tool_button("magnet",w.toggle_snapping,"Magnetic Snapping · N",True); w.snap_tool.setChecked(True); bar.addWidget(w.snap_tool); bar.addWidget(w.link_toggle)
    undo_tool=tool_button("rotate-ccw",w.undo,"Undo · Ctrl+Z"); redo_tool=tool_button("rotate-cw",w.redo,"Redo · Ctrl+Shift+Z")
    bar.addWidget(undo_tool); bar.addWidget(redo_tool)
    w.timeline_edit_tools=[w.select_tool,w.transform_box_tool,w.crop_tool,w.auto_layout_tool,w.blade_tool,w.retime_button,w.link_toggle,w.snap_tool,undo_tool,redo_tool]
    w.review_badge=QLabel("REVIEW ONLY · Scrub or play to preview"); w.review_badge.setObjectName("reviewBadge"); w.review_badge.hide(); bar.addWidget(w.review_badge); bar.addStretch()
    from .widgets import slider_to_zoom,zoom_to_slider
    w.timeline_zoom=SafeSlider(Qt.Horizontal); w.timeline_zoom.setRange(0,1000); w.timeline_zoom.setValue(zoom_to_slider(45)); w.timeline_zoom.setFixedWidth(110)
    bar.addWidget(tool_button("zoom-out",lambda:w.timeline_zoom.setValue(w.timeline_zoom.value()-40),"Timeline zoom out")); bar.addWidget(w.timeline_zoom); bar.addWidget(tool_button("zoom-in",lambda:w.timeline_zoom.setValue(w.timeline_zoom.value()+40),"Timeline zoom in"))
    from .monitor_control import MonitorControl
    w.monitor_control=MonitorControl(w); bar.addWidget(w.monitor_control); layout.addLayout(bar)
    w.timeline=TimelineWidget(); w.timeline.itemSelected.connect(w.select_item); w.timeline.playheadChanged.connect(w.seek); w.timeline.scrubFinished.connect(w.finish_scrub); w.timeline.itemChanged.connect(lambda _:w.model_changed()); w.timeline.mediaDropped.connect(w.add_media_to_track); w.timeline.mediaBatchDropped.connect(w.add_media_batch); w.timeline.titleDropped.connect(w.add_title_object); w.timeline.commandRequested.connect(w.timeline_command); w.timeline.bladeRequested.connect(w.split_at); w.timeline.captionBladeRequested.connect(w.split_caption_at); w.timeline.effectDropped.connect(lambda name,id:w.apply_effect_to(name,id)); w.timeline.captionSelected.connect(w.select_caption); w.timeline.transitionSelected.connect(w.select_transition)
    w.timeline.setMinimumHeight(140); tl.setMinimumHeight(185)
    w.timeline.textEditRequested.connect(w.focus_timeline_text)
    w.timeline.effectUsed.connect(w.effects_panel.remember_used)
    for signal in (w.timeline.itemSelected,w.timeline.selectionChanged,w.timeline.captionSelected,w.timeline.transitionSelected):signal.connect(w.retime_button.update_state)
    w.timeline.power_bin_target=w.media_panel.power_bin_target; w.timeline.power_bin_drag_handler=w.media_panel.begin_timeline_drag
    w.timeline.media_resolver=w.media_panel.resolve_media
    from .external_drop import FileDropController
    w.timeline.file_drop_controller=FileDropController(w)
    w.timeline.filesDropped.connect(w.timeline.file_drop_controller.drop)
    def reflect_zoom(value):
        w.timeline_zoom.blockSignals(True); w.timeline_zoom.setValue(zoom_to_slider(value)); w.timeline_zoom.blockSignals(False)
    w.timeline_zoom.valueChanged.connect(lambda value:w.timeline.set_zoom(slider_to_zoom(value))); w.timeline.zoomChanged.connect(reflect_zoom); layout.addWidget(w.timeline); w.center_split.addWidget(tl); w.center_split.setSizes([530,300])
    w.right_stack=QStackedWidget(); w.right_stack.setFixedWidth(350); w.viewer_split.addWidget(w.right_stack); w.viewer_split.setStretchFactor(0,1); w.viewer_split.setStretchFactor(1,0); w.viewer_split.handle(1).setEnabled(False)
    w.inspector=PropertiesPanel(w); w.inspector.changed.connect(w.model_changed); w.inspector.requestCrop.connect(w.frame_source); w.right_stack.addWidget(w.inspector)
    w.inspector.filename.setFixedHeight(30); w.inspector.tabs.tabBar().setFixedHeight(HEADER_HEIGHT-30)
    w.inspector.tabs.tabBar().setDrawBase(False)
    # Existing caption generation commands use this non-visible editing adapter.
    w.caption_panel=CaptionPanel(lambda:w.project); w.caption_panel.changed.connect(w.model_changed); w.caption_panel.seek.connect(w.seek)
    w.normalize=QCheckBox(); w.normalize.setChecked(False); w.noise=QCheckBox(); w.duck=QCheckBox(); w.duck.setChecked(True)
    for box in [w.normalize,w.noise,w.duck]:box.toggled.connect(w.audio_settings)
    w.delivery=DeliveryPage(w); w.left_stack.addWidget(w.delivery.settings); w.right_stack.addWidget(w.delivery.queue)
    footer=QWidget(); footer.setObjectName("pageFooter"); fr=QHBoxLayout(footer); fr.setContentsMargins(0,2,0,2); fr.addStretch(); w.page_group=QButtonGroup(w)
    for label,icon,page in [("Edit","sliders-horizontal",0),("Deliver","download",1)]:
        b=QToolButton(); b.setText(label); b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); b.setCheckable(True); b.setProperty("pageNav",True); b.setProperty("navIcon",icon); b.setFixedSize(100,47); w.page_group.addButton(b,page); fr.addWidget(b)
    update_nav_icons(w)
    w.page_group.button(0).setChecked(True); w.page_group.idClicked.connect(lambda page:set_page(w,page)); fr.addStretch(); root.addWidget(footer)
    w.workspace_split.setSizes([520,960]); w.viewer_split.setSizes([10000,350]); w.workspace_split.setCollapsible(1,False); w.current_page=0
    w.inspector_toggle.toggled.connect(lambda _:update_panels(w))
    w.setStatusBar(QStatusBar())
    w.job_progress=QProgressBar(); w.job_progress.setRange(0,0); w.job_progress.setFixedSize(66,8); w.job_progress.setTextVisible(False)
    w.background_tasks=BackgroundTasks(w)
    w.job_status=QToolButton(); w.job_status.setObjectName("jobStatus")
    w.job_status.setFocusPolicy(Qt.StrongFocus); w.job_status.setCursor(Qt.PointingHandCursor)
    w.job_status.setToolTip("Show active and recent background tasks")
    w.job_status.clicked.connect(w.background_tasks.toggle)
    w.statusBar().addPermanentWidget(w.job_progress); w.statusBar().addPermanentWidget(w.job_status)
    w.update_job_status(); update_panels(w)


def update_panels(w):
    edit=w.current_page==0
    w.left_stack.setVisible(True); w.right_stack.setVisible(not edit or w.inspector_toggle.isChecked())


def set_page(w,page):
    if page not in (0,1):return
    if page!=1 and getattr(getattr(w,'delivery',None),'running',False):
        w.page_group.button(1).setChecked(True); w.statusBar().showMessage('Wait for rendering to finish or cancel it before returning to Edit.',4000); return
    if page and w.current_page==0:
        w._edit_left_width=w.workspace_split.sizes()[0]; w.left_stack.setFixedWidth(360); w.workspace_split.handle(1).setEnabled(False)
    elif not page and w.current_page!=0:
        w.left_stack.setMinimumWidth(280); w.left_stack.setMaximumWidth(16777215); w.workspace_split.handle(1).setEnabled(True)
        w.workspace_split.setSizes([getattr(w,'_edit_left_width',480),max(1,w.workspace_split.width()-getattr(w,'_edit_left_width',480))])
    w.current_page=page; w.left_stack.setCurrentIndex(min(page,1)); w.right_stack.setCurrentIndex(min(page,1)); w.page_group.button(page).setChecked(True)
    w.page_content.setCurrentIndex(0)
    for b in [w.inspector_toggle,*w.edit_actions]:b.setVisible(page==0)
    w.timeline.set_read_only(page!=0); w.preview.set_read_only(page!=0)
    w.preview.set_transform_controls_visible(page==0 and not w.transport.playing and w.transform_box_tool.isChecked())
    w.setAcceptDrops(page==0); w.inspector.setEnabled(page==0)
    for control in w.timeline_edit_tools:control.setEnabled(page==0)
    w.update_keyframe_button()
    for action in getattr(w,"editing_actions",[]):action.setEnabled(page==0)
    for name,action in w.shortcut_actions.items():
        if name in {"export","play_pause","shuttle_back","shuttle_stop","shuttle_forward"}:action.setEnabled(True)
        elif name!="save":action.setEnabled(page==0)
    w.review_badge.setVisible(page!=0)
    w.statusBar().showMessage("Deliver · Timeline locked. Scrub the playhead or use Space to preview." if page else "Edit · Timeline editing enabled",5000)
    if page==1:
        w.delivery.sync_project_settings()
        if not w.delivery.name.isModified():w.delivery.name.setText(w.project.name)
        w.delivery.refresh_estimate()
    update_panels(w)


def update_nav_icons(w, palette: dict = None):
    from .icons import create_nav_icon
    from .theme import get_active_theme_palette
    if palette is None:
        theme_key = getattr(w, "settings", {}).get("ui_theme", "default")
        palette = get_active_theme_palette(theme_key)

    color_map = {
        0: palette.get("nav_edit_color", "#e0796b"),
        1: palette.get("nav_deliver_color", "#68a8df"),
    }
    inactive_color = palette.get("nav_inactive_color", palette.get("icon_color", "#8b919e"))

    if hasattr(w, "page_group") and w.page_group:
        for b in w.page_group.buttons():
            page_id = w.page_group.id(b)
            icon_name = b.property("navIcon")
            if icon_name:
                active_color = color_map.get(page_id, palette.get("accent", "#e0796b"))
                b.setIcon(create_nav_icon(icon_name, inactive_color, active_color, 18))


def refresh_workspace_theme(w, palette: dict):
    from .icons import lucide_icon
    icon_color = palette.get("icon_color", "#d8dae0")
    for btn in w.findChildren(QAbstractButton):
        icon_name = btn.property("iconName")
        if icon_name:
            accent = bool(btn.property("accent"))
            c = '@accent_text' if accent else '@icon_color' if btn.property('editorTool') else icon_color
            sz = btn.iconSize()
            btn.setIcon(lucide_icon(icon_name, c, sz.width() or 18))
    update_nav_icons(w, palette)
    if hasattr(w, 'background_tasks'):
        w.background_tasks.refresh()
