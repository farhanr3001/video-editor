"""Recovery copies presented as dated projects, never as technical file paths."""
from datetime import datetime
from PySide6.QtCore import Qt,Slot
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QTableWidgetItem,QHeaderView,QMessageBox,QAbstractItemView)
from .theme_widgets import set_ui_style
from .icons import lucide_icon
from . import recovery_store as store


class RecoveryDialog(QDialog):
    def __init__(self,window,crash_only=False):
        super().__init__(window);self.owner=window;self.crash_only=crash_only;self.rows=[]
        self.setWindowTitle('Recover your work' if crash_only else 'Recovery copies');self.resize(740,440);self.setMinimumSize(480,300)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,18,18,18);layout.setSpacing(12)
        title=QLabel('Pick up where you left off' if crash_only else 'Your recovery copies');set_ui_style(title,'font-size:18px;font-weight:600;');layout.addWidget(title)
        note=QLabel('An earlier session did not close normally. Choose a copy to recover.' if crash_only else 'Automatic copies of your editing work. Restoring opens a separate unsaved project.');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Project','Saved','Size','Status',''])
        self.table.setShowGrid(False)
        set_ui_style(self.table,'''QTableWidget {outline:0;}
            QTableWidget::item {padding:4px 7px;border:0;background:transparent;color:@text_main;}
            QTableWidget::item:selected {background:@bg_selected;color:@text_selected;border:0;}
            QTableWidget::item:focus {outline:0;border:0;}''')
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.verticalHeader().hide();self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for c in (1,2,3,4):self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.selection_changed);self.table.cellDoubleClicked.connect(lambda *_:self.restore())
        layout.addWidget(self.table,1)
        self.status=QLabel('Finding recovery copies…');self.status.setWordWrap(True);set_ui_style(self.status,'color:@text_sub;');layout.addWidget(self.status)
        actions=QHBoxLayout();refresh=QPushButton('Refresh');refresh.clicked.connect(self.refresh);actions.addWidget(refresh);actions.addStretch()
        close=QPushButton('Not now' if crash_only else 'Close');close.clicked.connect(self.reject);actions.addWidget(close)
        self.restore_button=QPushButton('Restore copy');self.restore_button.setEnabled(False);self.restore_button.clicked.connect(self.restore);actions.addWidget(self.restore_button);layout.addLayout(actions)
        self.refresh()

    def refresh(self):
        from .ui import Worker
        worker=Worker(store.entries);worker.signals.result.connect(self.populate,Qt.QueuedConnection)
        worker.signals.error.connect(self.failed,Qt.QueuedConnection)
        self.owner.start_worker(worker)

    @Slot(str)
    def failed(self,_):self.status.setText('Some recovery copies could not be read. Try refreshing the list.')

    @Slot(object)
    def populate(self,rows):
        self.rows=[row for row in rows if row['crashed']] if self.crash_only else rows
        self.table.setRowCount(len(self.rows))
        for n,row in enumerate(self.rows):
            from .cache_manager import size_text
            values=[row['name'],datetime.fromtimestamp(row['time']).strftime('%d %b %Y  %H:%M:%S'),size_text(row['size']),
                    'Open in a session' if row['active'] else 'Media needs locating' if row.get('missing') else 'Interrupted session' if row['crashed'] else 'Available']
            for c,value in enumerate(values):self.table.setItem(n,c,QTableWidgetItem(value))
            if row.get('missing'):self.table.item(n,3).setToolTip('Some original media is unavailable. The recovery copy is kept so you can reconnect moved files or a disconnected drive after restoring.')
            delete=QPushButton();delete.setIcon(lucide_icon('trash-2'));delete.setToolTip('Delete this recovery copy')
            delete.setAccessibleName('Delete recovery copy '+values[1]);delete.setEnabled(not row['active'])
            delete.clicked.connect(lambda checked=False,r=row:self.delete_copy(r));self.table.setCellWidget(n,4,delete)
        total=sum(row['size'] for row in self.rows)
        from .cache_manager import size_text
        noun='copy' if len(self.rows)==1 else 'copies'
        self.status.setText(f'{len(self.rows)} {noun} · {size_text(total)}. Copies contain editing instructions, not copies of your videos.' if self.rows else 'No recovery copies are available yet.')
        if self.rows:self.table.selectRow(0)
        elif self.crash_only:self.reject()

    def selection_changed(self):self.restore_button.setEnabled(0<=self.table.currentRow()<len(self.rows))
    def delete_copy(self,row):
        if QMessageBox.question(self,'Delete recovery copy?','Delete this dated recovery copy? Your saved project and original media will stay in place.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:store.remove(row['path']);self.refresh()
        except Exception:QMessageBox.information(self,'Copy unavailable','This copy is being used or has already been removed. Refresh the list and try again.')

    def restore(self):
        index=self.table.currentRow()
        if not 0<=index<len(self.rows):return
        if getattr(self.owner.delivery,'running',False):
            QMessageBox.information(self,'Finish the export first','Wait for the current export to finish before restoring a project.');return
        from .model import Project
        try:project=Project.load(self.rows[index]['path'])
        except Exception:QMessageBox.warning(self,'Unable to restore','This recovery copy could not be opened. Try an earlier copy.');return
        if not self.owner.confirm_project_switch():return
        project.path='';self.owner.set_project(project);self.owner._saved_project_key=None;self.owner._saved_close_key=None
        store.acknowledge(self.rows[index]['path'])
        self.owner.statusBar().showMessage('Recovery copy opened. Save it when you are ready.',8000);self.accept()

def show(window,crash_only=False):
    dialog=RecoveryDialog(window,crash_only);dialog.exec()
