"""Toolbar access to the same retime-controls action used by Ctrl+R."""
from PySide6.QtCore import QEvent,QSize
from PySide6.QtWidgets import QToolButton,QToolTip
from .icons import lucide_icon

class TimelineRetimeButton(QToolButton):
    def __init__(self,owner):
        super().__init__(owner); self.owner=owner; self.setIcon(lucide_icon('timer'))
        self.setIconSize(QSize(18,18)); self.setProperty('iconName','timer'); self.setProperty('editorTool',True)
        self.setAccessibleName('Re-time controls'); self.clicked.connect(lambda:self.owner.timeline.toggle_retime())
        self.setEnabled(False); self.setToolTip('select a media to re-time first')
    def update_state(self,*_):
        w=self.owner; timeline=getattr(w,'timeline',None)
        selected=bool(timeline and w.project and any(w.project.item_by_id(i) for i in timeline.selected_ids))
        editable=getattr(w,'current_page',0)==0 and timeline and not timeline.read_only
        self.setEnabled(bool(selected and editable))
        self.setToolTip('Re-time controls · Ctrl+R' if selected and editable else 'select a media to re-time first' if not selected else 'Re-time controls are available in Edit')
    def event(self,event):
        # Qt suppresses ordinary tooltip events for disabled controls on some
        # Windows styles. Keep the reason discoverable while the button is gray.
        if event.type()==QEvent.ToolTip:
            QToolTip.showText(event.globalPos(),self.toolTip(),self); event.accept(); return True
        return super().event(event)
