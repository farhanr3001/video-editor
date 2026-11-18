"""Plain-language application information and verified file repair."""
import json,os,platform,re,sys,threading,zipfile
from pathlib import Path
from PySide6.QtCore import Qt,Slot
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,QFileDialog,QMessageBox
from .controls import SafeComboBox
from .theme_widgets import set_ui_style,set_ui_icon
from .version import VERSION


class AboutDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.owner=window;self.setWindowTitle('About Kinetic Cut');self.resize(430,280);self.setMinimumWidth(350)
        layout=QVBoxLayout(self);layout.setContentsMargins(22,22,22,22);layout.setSpacing(12)
        title=QLabel('Kinetic Cut');set_ui_style(title,'font-size:24px;font-weight:700;');layout.addWidget(title)
        layout.addWidget(QLabel('Create. Edit. Share.'));layout.addWidget(QLabel('Version '+VERSION))
        self.status=QLabel('Checking for updates…');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.channel=SafeComboBox();self.channel.addItem('Stable updates (recommended)','stable');self.channel.addItem('Preview updates (early access)','preview')
        set_ui_style(self.channel,'QComboBox {combobox-popup:0;min-height:28px;}')
        self.channel.setCurrentIndex(1 if window.settings.get('update_channel')=='preview' else 0)
        self.channel.currentIndexChanged.connect(self.change_channel);layout.addWidget(self.channel)
        hint=QLabel('Preview updates may contain unfinished changes. Switching to Stable keeps your installed version until a newer stable update is available.');hint.setWordWrap(True);set_ui_style(hint,'color:@text_sub;font-size:11px;');layout.addWidget(hint)
        row=QHBoxLayout();check=QPushButton('Check for updates');check.clicked.connect(lambda:window.check_for_updates());row.addWidget(check);row.addStretch();close=QPushButton('Close');close.clicked.connect(self.accept);row.addWidget(close);layout.addLayout(row)
        self.generation=0;self.check()
    def change_channel(self):
        from .config import save_settings
        self.owner.settings['update_channel']=self.channel.currentData();save_settings(self.owner.settings);self.check()
    def check(self):
        from .ui import Worker
        from .updates import check
        self.generation+=1;generation=self.generation;channel=self.channel.currentData();self.status.setText('Checking for updates…')
        def work():
            try:return generation,check(channel=channel),True
            except Exception:return generation,None,False
        worker=Worker(work);worker.signals.result.connect(self.checked,Qt.QueuedConnection);worker.signals.error.connect(self.failed,Qt.QueuedConnection);self.owner.start_worker(worker)
    @Slot(object)
    def checked(self,result):
        generation,release,success=result
        if generation!=self.generation:return
        if not success:self.failed('');return
        self.status.setText(('Preview update ' if release.preview else 'Update ')+release.version+' is available.' if release else 'You are up to date for this update channel.')
    @Slot(str)
    def failed(self,_):self.status.setText('Unable to check right now. Your installed version is shown above.')


class RepairDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.owner=window;self.cancel=threading.Event();self.running=False;self.setWindowTitle('Repair Kinetic Cut');self.resize(470,250);self.setMinimumWidth(350)
        layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,20);layout.setSpacing(12)
        title=QLabel('Get Kinetic Cut working again');set_ui_style(title,'font-size:18px;font-weight:600;');layout.addWidget(title)
        note=QLabel('Check for missing or damaged application files and replace them with verified copies. Your projects, original media, settings and optional downloads stay in place.');note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel('An internet connection is needed.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.bar=QProgressBar();self.bar.hide();layout.addWidget(self.bar)
        layout.addStretch()
        row=QHBoxLayout();report=QPushButton('Save support report…');report.clicked.connect(lambda:save_support_report(window,self));row.addWidget(report);row.addStretch()
        close=QPushButton('Close');close.clicked.connect(self.reject);row.addWidget(close)
        self.button=QPushButton('Repair application');self.button.clicked.connect(self.start);row.addWidget(self.button);layout.addLayout(row)
    def start(self):
        if self.running:return
        if not getattr(sys,'frozen',False):self.status.setText('Application repair is available in the installed app. Support reports are available here.');return
        from .ui import Worker
        self.running=True;self.cancel.clear();self.button.setEnabled(False);self.bar.show();self.bar.setRange(0,0);self.status.setText('Checking application files…')
        root=Path(sys.executable).parent;cancel=self.cancel
        def work():
            from .application_repair import prepare
            return prepare(root,cancel,lambda value,text:worker.signals.progress.emit(value))
        worker=Worker(work);worker.cancel_callback=cancel.set;worker.signals.result.connect(self.ready,Qt.QueuedConnection)
        worker.signals.error.connect(self.failed,Qt.QueuedConnection);worker.signals.progress.connect(self.progress,Qt.QueuedConnection);self.owner.start_worker(worker)
    @Slot(int)
    def progress(self,value):self.bar.setRange(0,100);self.bar.setValue(value);self.status.setText('Preparing verified repair files…')
    @Slot(object)
    def ready(self,path):
        self.running=False;self.bar.hide();self.button.setEnabled(True)
        if self.cancel.is_set():return
        if path is None:self.status.setText('Your application files are healthy. No repair was needed.');return
        if path.get('unpublished'):
            self.status.setText('This app includes local improvements that have not been published yet. Repair will be available after that update is released. Your current app has been kept.');return
        self.accept()
        from .update_ui import UpdateController
        controller=getattr(self.owner,'_repair_controller',None)
        if controller is None:controller=self.owner._repair_controller=UpdateController(self.owner)
        progress=QProgressBar(self.owner);progress.hide()
        controller.ready(path['path'],progress,incremental=path['incremental'],repair=True)
    @Slot(str)
    def failed(self,error):
        import logging
        logging.error('Application repair failed: %s',error);self.running=False;self.bar.hide();self.button.setEnabled(True)
        if not self.cancel.is_set():self.status.setText('Repair could not finish. Check your connection and try again. Your application files have not been changed.')
    def reject(self):self.cancel.set();super().reject()
    def closeEvent(self,event):self.cancel.set();super().closeEvent(event)


def support_report(destination,summary,log_directory):
    """Strict allowlist, no projects/settings/media; redact paths and credentials."""
    def scrub(text):
        text=re.sub(r'(?:https?|wss?)://\S+','[address removed]',text)
        text=re.sub(r'(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\t\"<>]*','[path removed]',text)
        text=re.sub(r'''(?i)["']?(?:authorization|api.?key|token|password)["']?\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n,}]+)''','[credential removed]',text)
        text=re.sub(r'\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b','[email removed]',text)
        return text
    destination=Path(destination);pending=destination.with_suffix(destination.suffix+'.partial')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('system.json',json.dumps(summary,indent=2))
        for name in ('application.log','crash-trace.log','user-actions.log'):
            path=Path(log_directory)/name
            if not path.is_file() or path.is_symlink():continue
            with path.open('rb') as stream:stream.seek(max(0,path.stat().st_size-500_000));data=stream.read(500_000)
            archive.writestr(name,scrub(data.decode('utf-8',errors='replace')))
    pending.replace(destination)
    return str(destination)

def save_support_report(window,parent=None):
    parent=parent or window
    if QMessageBox.question(parent,'Save support report?','Create a report with app version, Windows information and recent error logs? Projects, media, scripts and settings are excluded. Nothing is sent automatically.',QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)!=QMessageBox.Yes:return
    path,_=QFileDialog.getSaveFileName(parent,'Save support report','KineticCut-support.zip','ZIP archive (*.zip)')
    if not path:return
    from .config import DATA_DIR
    from .ui import Worker
    summary=dict(version=VERSION,system=platform.system(),release=platform.release(),python=platform.python_version())
    worker=Worker(support_report,path,summary,DATA_DIR)
    worker.signals.result.connect(lambda _:QMessageBox.information(window,'Report saved','Your support report is ready. You can share it when asking for help.'))
    worker.signals.error.connect(lambda _:QMessageBox.warning(window,'Unable to save','Choose another location and try again.'))
    window.start_worker(worker)

def install_menu(window):
    menu=window.menuBar().addMenu('Help')
    for text,callback in (
        ('Repair application…',lambda:RepairDialog(window).exec()),
        ('Recovery copies…',lambda:__import__('kinetic_cut.recovery_ui',fromlist=['show']).show(window)),
        ('Save support report…',lambda:save_support_report(window)),
        ('About Kinetic Cut…',lambda:AboutDialog(window).exec())):
        menu.addAction(text,callback)
