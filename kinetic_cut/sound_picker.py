"""Read-only browser of the editor's existing sound sources."""
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QSplitter,QTreeWidget,
    QTreeWidgetItem,QDialogButtonBox,QLabel,QLineEdit,QHeaderView)
from .icons import lucide_icon


class SoundBinPicker(QDialog):
    def __init__(self,owner,initial='project',parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose composition sound'); self.resize(660,420)
        self.setMinimumSize(440,300); self.path=''; self.owner=owner
        self.pool=owner.media_panel
        root=QVBoxLayout(self)
        self.search=QLineEdit(self); self.search.setPlaceholderText('Search sounds in this folder'); root.addWidget(self.search)
        split=QSplitter(Qt.Horizontal,self); root.addWidget(split,1)
        self.tree=QTreeWidget(split); self.tree.setHeaderHidden(True); self.tree.setIndentation(12)
        self.tree.setObjectName('powerFolderTree')
        self.rows=QTreeWidget(split); self.rows.setHeaderLabels(['Name','Duration']); self.rows.setRootIsDecorated(False)
        self.rows.setIconSize(QSize(70,42)); self.thumbnail_rows=[]
        self.thumbnail_timer=QTimer(self); self.thumbnail_timer.setInterval(120); self.thumbnail_timer.timeout.connect(self.update_thumbnails)
        self.rows.header().setSectionResizeMode(0,QHeaderView.Stretch)
        self.rows.header().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        split.setSizes([180,440])
        self.note=QLabel('Choose an audible source up to 60 seconds long.',self); self.note.setWordWrap(True); root.addWidget(self.note)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Cancel,self)
        self.confirm=self.buttons.addButton('Confirm',QDialogButtonBox.AcceptRole); self.confirm.setEnabled(False)
        root.addWidget(self.buttons); self.buttons.rejected.connect(self.reject); self.buttons.accepted.connect(self.accept)
        media_root=QTreeWidgetItem(self.tree,['Media Pool']); media_root.setFlags(media_root.flags() & ~Qt.ItemIsSelectable)
        master=QTreeWidgetItem(media_root,['Master']); master.setData(0,Qt.UserRole,'project')
        for key,folder in self.pool.watch_folders.folders.items():
            row=QTreeWidgetItem(media_root,[Path(folder.path).name or folder.path]); row.setData(0,Qt.UserRole,key); row.setIcon(0,lucide_icon('folder'))
        power_root=QTreeWidgetItem(self.tree,['Power Bins']); power_root.setFlags(power_root.flags() & ~Qt.ItemIsSelectable)
        nodes={}
        for folder in sorted(self.pool.power.data['folders']):
            parent_node=power_root; parts=[]
            for piece in folder.split('/'):
                parts.append(piece); key='/'.join(parts)
                if key not in nodes:
                    row=QTreeWidgetItem(parent_node,[piece]); row.setData(0,Qt.UserRole,key); row.setIcon(0,lucide_icon('folder')); nodes[key]=row
                parent_node=nodes[key]
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self.refresh); self.search.textChanged.connect(self.refresh)
        self.rows.currentItemChanged.connect(self.selected)
        self.tree.setCurrentItem(nodes.get('Master',master) if initial=='power' else master)

    def refresh(self,*_):
        from .model import MediaItem
        from .pool_tools import metadata
        self.thumbnail_timer.stop(); self.thumbnail_rows=[]
        self.rows.clear(); self.path=''; self.confirm.setEnabled(False)
        row=self.tree.currentItem(); folder=row.data(0,Qt.UserRole) if row else None
        if folder=='project':media=[m for m in self.owner.project.media if not m.pool_hidden]
        elif folder in self.pool.watch_folders.folders:media=self.pool.watch_folders.folders[folder].media()
        else:media=[MediaItem(**entry['media']) for entry in self.pool.power.data['media'] if entry['folder']==folder]
        for media_item in sorted(media,key=lambda m:m.name.casefold()):
            if not (media_item.kind=='audio' or media_item.has_audio) or self.search.text().casefold() not in media_item.name.casefold():continue
            row=QTreeWidgetItem(self.rows,[media_item.name,metadata(media_item)[1]]); row.setIcon(0,lucide_icon('audio-waveform'))
            reason=('Saved timeline clips are not standalone sound sources.' if media_item.timeline_preset else
                'Source file is unavailable.' if not Path(media_item.path).is_file() else
                'Choose a sound up to 60 seconds long.' if not .01<media_item.duration<=60 else '')
            row.setToolTip(0,media_item.path+('\n'+reason if reason else ''))
            row.setData(0,Qt.UserRole,media_item.path if not reason else '')
            if reason:row.setFlags(row.flags() & ~Qt.ItemIsEnabled)
            elif media_item.kind=='audio' or media_item.has_audio:self.thumbnail_rows.append((row,media_item))
        self.update_thumbnails()

    def update_thumbnails(self):
        pending=[]; thumbnails=self.pool.audio_thumbnails
        for row,media in self.thumbnail_rows:
            icon=thumbnails.icon(media)
            if icon.isNull():pending.append((row,media))
            else:row.setIcon(0,icon)
        self.thumbnail_rows=pending
        if pending and (thumbnails.busy or thumbnails.pending):self.thumbnail_timer.start()
        else:self.thumbnail_timer.stop()

    def done(self,result):
        self.thumbnail_timer.stop(); super().done(result)

    def selected(self,*_):
        row=self.rows.currentItem(); self.path=(row.data(0,Qt.UserRole) or '') if row else ''
        self.confirm.setEnabled(bool(self.path))

    def accept(self):
        if self.path and Path(self.path).is_file():super().accept()
        else:self.note.setText('This source is no longer available. Choose another sound.'); self.confirm.setEnabled(False)
