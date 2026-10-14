"""Input routing and hierarchical layer controls owned by one motion dialog."""
import copy
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QApplication,QTreeWidget,QAbstractItemView,QMenu,QLineEdit,QPlainTextEdit,QTextEdit,QAbstractSpinBox,QComboBox
from .motion import validate

class MotionLayerTree(QTreeWidget):
    def __init__(self,editor):
        super().__init__(editor); self.editor=editor
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove); self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu); self.customContextMenuRequested.connect(self.menu)
    def menu(self,point):
        hit=self.itemAt(point)
        if hit and not hit.isSelected():self.editor.select_node(hit.data(0,Qt.UserRole))
        menu=QMenu(self)
        menu.addAction('Add layer',self.editor.add)
        if hit:
            menu.addSeparator()
            for label,fn in [('Duplicate selected branches',self.editor.duplicate),('Remove selected branches',self.editor.remove),('Move up',lambda:self.editor.reorder(-1)),('Move down',lambda:self.editor.reorder(1))]:menu.addAction(label,fn)
        menu.exec(self.viewport().mapToGlobal(point))
    def dropEvent(self,event):
        if event.source()!=self:event.ignore(); return
        hit=self.itemAt(event.position().toPoint()); target=hit.data(0,Qt.UserRole) if hit else None
        roots=self.editor.selection_roots(); ids=self.editor.branch(); nodes=self.editor.scene['nodes']
        if not roots or target in ids:event.ignore(); return
        before=copy.deepcopy(self.editor.scene); stage=copy.deepcopy(before)
        by_id={n['id']:n for n in stage['nodes']}
        position=self.dropIndicatorPosition()
        parent=target if target and position==QAbstractItemView.OnItem else by_id[target].get('parent','') if target else ''
        for node_id in roots:by_id[node_id]['parent']=parent
        moving=[n for n in stage['nodes'] if n['id'] in ids]; remaining=[n for n in stage['nodes'] if n['id'] not in ids]
        index=next((i for i,n in enumerate(remaining) if n['id']==target),len(remaining))
        if target and position in (QAbstractItemView.BelowItem,QAbstractItemView.OnItem):index+=1
        stage['nodes']=remaining[:index]+moving+remaining[index:]
        try:stage=validate(stage)
        except (ValueError,KeyError,TypeError):event.ignore(); return
        self.editor.begin_edit(); self.editor.scene=stage; self.editor.rebuild(); self.editor.end_edit(); event.acceptProposedAction()

def motion_key(editor,event):
    key=event.key(); mods=event.modifiers(); ctrl=bool(mods&Qt.ControlModifier); shift=bool(mods&Qt.ShiftModifier)
    if ctrl and key==Qt.Key_Z:return lambda:editor.local_history(1 if shift else -1)
    focus=QApplication.focusWidget()
    if isinstance(focus,(QLineEdit,QPlainTextEdit,QTextEdit,QAbstractSpinBox)) or isinstance(focus,QComboBox):return None
    if mods&Qt.AltModifier:return None
    if key==Qt.Key_Space and not ctrl:return editor.toggle
    if key==Qt.Key_Home:return lambda:editor.navigate('start')
    if key==Qt.Key_End:return lambda:editor.navigate('end')
    if key in (Qt.Key_Left,Qt.Key_Right):return lambda:editor.navigate('key' if shift else 'frame',-1 if key==Qt.Key_Left else 1)
    if ctrl and key==Qt.Key_D:return editor.duplicate
    if ctrl and key==Qt.Key_A:return lambda:editor.select_nodes([n['id'] for n in editor.scene['nodes']])
    if key in (Qt.Key_Delete,Qt.Key_Backspace):
        if focus is editor.timeline:return None  # Timeline owns keyframe deletion.
        return editor.remove
    return None

class MotionInputRouter:
    """Mixin: application filter claims keys only inside this active dialog."""
    def eventFilter(self,watched,event):
        if event.type() in (QEvent.ShortcutOverride,QEvent.KeyPress) and self.isVisible() and QApplication.activeWindow() is self and getattr(watched,'window',lambda:None)() is self:
            action=motion_key(self,event)
            if action:
                event.accept()
                if event.type()==QEvent.KeyPress:action()
                return True
        return super().eventFilter(watched,event)
