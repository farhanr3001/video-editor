"""Local project gallery. Project deletion is a recoverable file move only."""
import hashlib,os,json,uuid
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QUrl,QRectF
from PySide6.QtGui import QImage,QIcon,QPixmap,QDesktopServices,QPainter,QColor,QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QListWidgetItem,QListView,QFileDialog,QMessageBox,QMenu,QLineEdit)
from .config import CACHE_DIR,save_settings
from .icons import lucide_icon
from .model import Project


def folder(settings):
    return Path(settings.get('project_folder') or Path.home()/'Documents'/'Kinetic Cut'/'Projects')


def thumbnail_path(path):
    key=hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode()).hexdigest()
    return CACHE_DIR/'projects'/(key+'.png')


def tile_icon(image=None,new=False):
    """Equal-sized gallery cards, with aspect-fit media and a real New tile."""
    pix=QPixmap(210,125); pix.fill(QColor('#18191c')); painter=QPainter(pix)
    if image is not None and not image.isNull():
        size=image.size(); size.scale(208,123,Qt.KeepAspectRatio)
        painter.drawImage(QRectF((210-size.width())/2,(125-size.height())/2,size.width(),size.height()),image)
    elif new:
        painter.setRenderHint(QPainter.Antialiasing); painter.setPen(QPen(QColor('#c3c7ce'),3))
        painter.drawLine(89,62,121,62); painter.drawLine(105,46,105,78)
    else:lucide_icon('film').paint(painter,85,42,40,40)
    painter.setPen(QColor('#41434a')); painter.setBrush(Qt.NoBrush); painter.drawRect(0,0,209,124); painter.end()
    return QIcon(pix)


def remember(window,path,capture=False):
    path=str(Path(path).resolve()); recent=window.settings.get('recent_projects',[])
    if not window.settings.get('project_folder'):window.settings['project_folder']=str(Path(path).parent)
    window.settings['last_open_project_dir']=str(Path(path).parent)
    window.settings['recent_projects']=[path]+[p for p in recent if os.path.normcase(p)!=os.path.normcase(path)][:99]
    save_settings(window.settings)
    if capture:
        # The cached composition is not part of the project or its source media.
        preview=window.preview; controls=preview.transform_controls_visible
        try:
            preview.set_transform_controls_visible(False)
            image=preview.grab().toImage().copy(preview.composition_rect().toAlignedRect())
            target=thumbnail_path(path); target.parent.mkdir(parents=True,exist_ok=True)
            image.scaled(400,240,Qt.KeepAspectRatio,Qt.SmoothTransformation).save(str(target))
        finally:preview.set_transform_controls_visible(controls)


def project_paths(settings,current=''):
    root=folder(settings); paths=list(root.glob('*.kcut')) if root.is_dir() else []
    paths += [Path(p) for p in settings.get('recent_projects',[])]+([Path(current)] if current else [])
    found={}
    for path in paths:
        if path.is_file() and '.KineticCut Trash' not in path.parts and 'unit-test-home' not in path.parts:
            found[os.path.normcase(str(path.resolve()))]=path.resolve()
    return sorted(found.values(),key=lambda p:p.stat().st_mtime,reverse=True)


def recoverable_delete(path):
    path=Path(path).resolve()
    if not path.is_file() or path.suffix.lower()!='.kcut':raise ValueError('Select an existing Kinetic Cut project.')
    trash=path.parent/'.KineticCut Trash'; trash.mkdir(exist_ok=True)
    destination=trash/(path.stem+'-'+uuid.uuid4().hex[:8]+'.kcut')
    path.rename(destination)
    return destination


class ProjectManagerDialog(QDialog):
    def __init__(self,window):
        super().__init__(window); self.window=window; self.choice=None; self._generation=0
        self.setWindowTitle('Project Manager'); self.resize(940,620)
        root=QVBoxLayout(self); top=QHBoxLayout(); root.addLayout(top)
        self.location=QLabel(str(folder(window.settings))); self.location.setWordWrap(True); top.addWidget(self.location,1)
        browse=QPushButton('Project folder…'); browse.clicked.connect(self.choose_folder); top.addWidget(browse)
        reveal=QPushButton('Open folder'); reveal.clicked.connect(self.open_folder); top.addWidget(reveal)
        self.list_toggle=QPushButton('List view'); self.list_toggle.setCheckable(True); self.list_toggle.toggled.connect(self.set_list); top.addWidget(self.list_toggle)
        self.search=QLineEdit(); self.search.setPlaceholderText('Search projects'); self.search.textChanged.connect(self.filter); root.addWidget(self.search)
        self.items=QListWidget(); self.items.setResizeMode(QListView.Adjust); self.items.setMovement(QListView.Static); self.items.setSpacing(10); self.items.setWordWrap(True)
        self.items.setContextMenuPolicy(Qt.CustomContextMenu); self.items.customContextMenuRequested.connect(self.context_menu)
        self.items.itemDoubleClicked.connect(self.activate); root.addWidget(self.items,1)
        self.status=QLabel(''); root.addWidget(self.status)
        bottom=QHBoxLayout(); root.addLayout(bottom)
        other=QPushButton('Open project elsewhere…'); other.clicked.connect(self.open_other); bottom.addWidget(other)
        recovery=QPushButton('Open Recovery File…'); recovery.setIcon(lucide_icon('rotate-ccw', '#d9ff43')); recovery.setToolTip('Open autosaved or crash-backup project from app data'); recovery.clicked.connect(self.open_recovery); bottom.addWidget(recovery)
        refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh); bottom.addWidget(refresh); bottom.addStretch()
        close=QPushButton('Close'); close.clicked.connect(self.reject); bottom.addWidget(close)
        self.set_list(bool(window.settings.get('project_manager_list',False))); self.list_toggle.setChecked(bool(window.settings.get('project_manager_list',False))); self.refresh()

    def open_recovery(self):
        from .config import DATA_DIR, AUTOSAVE_PATH, CACHE_DIR
        import time
        from PySide6.QtGui import QCursor
        candidates = []
        for p in [DATA_DIR / "recovery_backup_user_work.kcut", AUTOSAVE_PATH]:
            if p.is_file() and p.stat().st_size > 50 and p not in candidates:
                candidates.append(p)
        rec_dir = CACHE_DIR / "recovered"
        if rec_dir.is_dir():
            for p in sorted(rec_dir.glob("*.kcut"), key=lambda x: x.stat().st_mtime, reverse=True):
                if p not in candidates:
                    candidates.append(p)
        root_dir = folder(self.window.settings)
        if root_dir.is_dir():
            for p in root_dir.glob("Recovered*.kcut"):
                if p not in candidates:
                    candidates.append(p)

        if not candidates:
            path, _ = QFileDialog.getOpenFileName(self, "Open Recovery File", str(DATA_DIR), "Kinetic Cut (*.kcut);;All Files (*)")
            if path:
                self.choice = path
                self.accept()
            return

        menu = QMenu(self)
        for c in candidates:
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                mtime = time.strftime("%b %d %I:%M %p", time.localtime(c.stat().st_mtime))
                label = f"{c.stem} — {data.get('name', 'Project')} ({len(data.get('timeline', []))} clips · {mtime})"
            except Exception:
                label = f"{c.name} ({c.stat().st_size} bytes)"
            menu.addAction(label, lambda p=str(c.resolve()): self._activate_path(p))
        menu.addSeparator()
        menu.addAction("Browse all recovery files in Data folder…", lambda: self._browse_recovery())
        menu.exec(QCursor.pos())

    def _activate_path(self, path: str):
        self.choice = path
        self.accept()

    def _browse_recovery(self):
        from .config import DATA_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Open Recovery File", str(DATA_DIR), "Kinetic Cut (*.kcut);;All Files (*)")
        if path:
            self.choice = path
            self.accept()

    def set_list(self,enabled):
        self.items.setViewMode(QListView.ListMode if enabled else QListView.IconMode)
        self.items.setIconSize(QSize(76,48) if enabled else QSize(210,125))
        self.items.setGridSize(QSize() if enabled else QSize(225,165))
        self.list_toggle.setText('Gallery view' if enabled else 'List view')
        self.window.settings['project_manager_list']=enabled; save_settings(self.window.settings)

    def refresh(self):
        from .ui import Worker
        self._generation+=1; generation=self._generation; self.items.clear()
        new=QListWidgetItem(tile_icon(new=True),'New Project'); new.setData(Qt.UserRole,''); new.setToolTip('Double-click to choose project settings and start a new project'); self.items.addItem(new)
        self.status.setText('Loading projects and thumbnails…')
        settings=dict(self.window.settings); current=self.window.project.path
        def scan():
            result=[]
            for path in project_paths(settings,current):
                try:
                    project=Project.load(path); image=QImage(str(thumbnail_path(path)))
                    if image.isNull():
                        for clip in project.timeline:
                            media=project.media_by_id(clip.media_id)
                            if not media:continue
                            image=QImage(media.path if media.kind=='image' else media.thumbnail or '')
                            if not image.isNull():break
                    name=path.stem if project.name in {'Untitled Short','Untitled Project'} else project.name
                    result.append((str(path),name,image.scaled(400,240,Qt.KeepAspectRatio,Qt.SmoothTransformation) if not image.isNull() else image,''))
                except Exception as error:result.append((str(path),path.stem,QImage(),str(error)))
            return result
        def loaded(rows):
            if generation!=self._generation:return
            for path,name,image,error in rows:
                icon=tile_icon(image)
                item=QListWidgetItem(icon,name); item.setData(Qt.UserRole,path); item.setToolTip(path+('\nCannot read project: '+error if error else '')); self.items.addItem(item)
            self.status.setText(f'{len(rows)} saved projects · Double-click to open'); self.filter()
        worker=Worker(scan); worker.signals.result.connect(loaded); worker.signals.error.connect(lambda text:self.status.setText('Could not load projects: '+text[-350:])); self.window.start_worker(worker)

    def filter(self,*_):
        query=self.search.text().casefold()
        for n in range(1,self.items.count()):
            item=self.items.item(n); item.setHidden(query not in (item.text()+' '+item.data(Qt.UserRole)).casefold())

    def activate(self,item):self.choice=item.data(Qt.UserRole); self.accept()
    def open_other(self):
        start_dir = self.window.settings.get("last_open_project_dir") or str(folder(self.window.settings))
        if not Path(start_dir).is_dir():
            start_dir = str(folder(self.window.settings))
        path,_=QFileDialog.getOpenFileName(self,'Open project',start_dir,'Kinetic Cut (*.kcut)')
        if path:
            self.window.settings["last_open_project_dir"] = str(Path(path).parent)
            save_settings(self.window.settings)
            self.choice=path; self.accept()
    def choose_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Projects folder',str(folder(self.window.settings)))
        if path:self.window.settings['project_folder']=path; save_settings(self.window.settings); self.location.setText(path); self.refresh()
    def open_folder(self):
        path=folder(self.window.settings); path.mkdir(parents=True,exist_ok=True); QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def context_menu(self,pos):
        item=self.items.itemAt(pos)
        if not item:return
        path=item.data(Qt.UserRole); menu=QMenu(self); menu.addAction('Open' if path else 'New Project',lambda:self.activate(item))
        if path:
            menu.addAction('Open file location',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))))
            action=menu.addAction('Delete project…',lambda:self.delete_project(path)); action.setEnabled(os.path.normcase(str(Path(path).resolve()))!=os.path.normcase(str(Path(self.window.project.path).resolve())) if self.window.project.path else True)
        menu.exec(self.items.viewport().mapToGlobal(pos))
    def delete_project(self,path):
        if QMessageBox.question(self,'Delete project','Move this project to .KineticCut Trash beside its file?\n\n'+path+'\n\nSource media is not removed. You can restore the project by moving it back.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            target=recoverable_delete(path); self.refresh(); self.status.setText('Recoverable project moved to '+str(target))
        except Exception as error:QMessageBox.warning(self,'Delete failed',str(error))
