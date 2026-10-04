"""Small queue widgets and recent export destinations."""
from .theme_widgets import set_ui_style
import os,time
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QEvent
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QToolButton,QSizePolicy,QComboBox,QScrollArea,QLayout
from .controls import SafeComboBox
from .icons import lucide_icon,resource_path

class FixedFormScroll(QScrollArea):
    """Only scroll vertically; recompute wrapping instead of hiding wide rows."""
    def __init__(self,body):
        super().__init__(); self.setWidgetResizable(True); self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.layout().setSizeConstraint(QLayout.SetNoConstraint); body.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Minimum)
        self.setWidget(body); self.viewport().installEventFilter(self)
    def eventFilter(self,watched,event):
        if watched is self.viewport() and event.type()==QEvent.Resize:
            body=self.widget(); width=event.size().width(); body.setFixedWidth(width)
            height=body.layout().totalHeightForWidth(width)
            body.setMinimumHeight(max(0,height if height>=0 else body.layout().minimumSize().height()))
        return super().eventFilter(watched,event)

class RecentLocations(SafeComboBox):
    def __init__(self,settings):
        super().__init__(); self.setEditable(True); self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert); self.setMaxVisibleItems(5); self.setMinimumWidth(0)
        self.setCompleter(None)
        arrow=resource_path('assets','icons','dropdown-chevron.svg').as_posix()
        set_ui_style(self, 'QComboBox::down-arrow { image: url("@arrow_combo"); width: 12px; height: 12px; } QComboBox::drop-down { width: 22px; }')
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon); self.setMinimumContentsLength(8)
        self.addItems(settings.get('export_recent_locations',[])[:5]); self.setEditText(self.itemText(0) or str(Path.home()/'Videos'))
    def text(self):return self.currentText()
    def setText(self,value):self.setEditText(value)
    def remember(self,folder,settings):
        from .config import save_settings
        folder=str(Path(folder).resolve()); key=os.path.normcase(os.path.normpath(folder))
        history=[folder]+[v for v in settings.get('export_recent_locations',[]) if os.path.normcase(os.path.normpath(v))!=key]
        settings['export_recent_locations']=history[:5]; current=self.currentText(); self.clear(); self.addItems(history[:5]); self.setEditText(current); save_settings(settings)

def elapsed(job):return max(0,time.monotonic()-job['started_at']) if job.get('started_at') is not None else job.get('elapsed',0.)
def elapsed_text(job):
    if job.get('state')=='Failed':return 'RENDER FAILED'
    seconds=int(elapsed(job)); hours,seconds=divmod(seconds,3600); minutes,seconds=divmod(seconds,60)
    return 'Time elapsed: '+(f'{hours}h ' if hours else '')+(f'{minutes}m ' if minutes or hours else '')+f'{seconds}s'

class RenderJobCard(QWidget):
    def __init__(self,job,number,remove):
        super().__init__(); self.job=job; root=QHBoxLayout(self); root.setContentsMargins(10,8,6,8)
        icon=QLabel(); icon.setPixmap(lucide_icon('download','#85afc3').pixmap(20,20)); root.addWidget(icon)
        column=QVBoxLayout(); column.setSpacing(2); root.addLayout(column,1)
        for value in (f'Job {number} · {job["state"]}',job['project'].name,job['output']):
            label=QLabel(value); label.setTextFormat(Qt.PlainText); label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred); label.setToolTip(value); column.addWidget(label)
        self.timer=QLabel(elapsed_text(job)); set_ui_style(self.timer, 'color:@text_main'); column.addWidget(self.timer)
        self.remove_button=QToolButton(self); self.remove_button.setText('×'); self.remove_button.setAccessibleName('Remove queued render'); self.remove_button.setToolTip('Remove this queued job'); self.remove_button.setFixedSize(22,22)
        self.remove_button.setVisible(job['state'] in {'Queued','Cancelled','Failed'}); self.remove_button.clicked.connect(lambda:remove(job)); root.addWidget(self.remove_button,0,Qt.AlignTop)
    def update_elapsed(self):self.timer.setText(elapsed_text(self.job))
