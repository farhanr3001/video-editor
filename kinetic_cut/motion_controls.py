"""Input routing and hierarchical layer controls owned by one motion dialog."""
import copy
from PySide6.QtCore import Qt,QEvent,QRectF,QPoint
from PySide6.QtGui import QDrag,QPainter,QPen,QColor,QPixmap,QPalette
from PySide6.QtWidgets import QApplication,QTreeWidget,QAbstractItemView,QMenu,QLineEdit,QPlainTextEdit,QTextEdit,QAbstractSpinBox,QComboBox
from .motion import validate

class MotionLayerTree(QTreeWidget):
    def __init__(self,editor):
        super().__init__(editor); self.editor=editor
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove); self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(False); self.drop_preview=None
        self.setToolTip('Drag between rows to reorder · Drop onto a group to nest · Drag left to move out of a group')
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
    def startDrag(self,supported):
        # Own the drag lifecycle: Qt's default InternalMove may remove the newly
        # rebuilt selected rows after our atomic custom drop has already finished.
        mime=self.mimeData(self.selectedItems())
        if mime is None:return
        drag=QDrag(self); drag.setMimeData(mime)
        count=len(self.editor.selection_roots()); label=f'{count} layer'+('s' if count!=1 else '')
        image=QPixmap(130,28); image.fill(Qt.transparent); painter=QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing); painter.setPen(Qt.NoPen); painter.setBrush(self.palette().highlight()); painter.drawRoundedRect(image.rect(),5,5)
        painter.setPen(self.palette().highlightedText().color()); painter.drawText(image.rect(),Qt.AlignCenter,label); painter.end()
        drag.setPixmap(image); drag.setHotSpot(QPoint(12,14))
        self._drag_scene_before=copy.deepcopy(self.editor.scene); self._drag_roots=list(self.editor.selection_roots())
        try:drag.exec(Qt.MoveAction)
        finally:self._drag_scene_before=None; self.clear_drop_preview()

    def clear_drop_preview(self):
        self.drop_preview=None; self.viewport().update()

    def drop_plan(self,point):
        hit=self.itemAt(point); nodes={n['id']:n for n in self.editor.scene['nodes']}
        if not self.editor.selection_roots():return None
        if hit is None:plan=dict(mode='root',anchor=None,parent='')
        else:
            rect=self.visualItemRect(hit); fraction=(point.y()-rect.top())/max(1,rect.height())
            target=hit.data(0,Qt.UserRole)
            if nodes[target]['kind']=='group' and .25<=fraction<=.75 and point.x()>=rect.left()+12:
                plan=dict(mode='inside',anchor=target,parent=target)
            else:
                # Horizontal position deliberately chooses the nesting level.
                # Moving left of a child snaps to its ancestor's sibling level.
                while hit.parent() and point.x()<self.visualItemRect(hit).left()-4:hit=hit.parent()
                target=hit.data(0,Qt.UserRole)
                plan=dict(mode='before' if fraction<.5 else 'after',anchor=target,parent=nodes[target].get('parent',''))
        moving=set(self.editor.branch())
        if plan['anchor'] in moving or plan['parent'] in moving:return None
        return plan

    def dragEnterEvent(self,event):
        if event.source()==self:event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        if event.source()!=self:self.clear_drop_preview(); event.ignore(); return
        super().dragMoveEvent(event)  # Keep Qt's edge auto-scroll.
        self.drop_preview=self.drop_plan(event.position().toPoint()); self.viewport().update()
        if self.drop_preview:event.acceptProposedAction()
        else:event.ignore()

    def dragLeaveEvent(self,event):
        self.clear_drop_preview(); super().dragLeaveEvent(event)

    def branch_bottom(self,item):
        bottom=self.visualItemRect(item).bottom(); pending=[item]
        while pending:
            parent=pending.pop()
            if not parent.isExpanded():continue
            for index in range(parent.childCount()):
                child=parent.child(index); rect=self.visualItemRect(child)
                if not rect.isEmpty():bottom=max(bottom,rect.bottom()); pending.append(child)
        return bottom

    def paintEvent(self,event):
        super().paintEvent(event)
        plan=self.drop_preview
        if not plan:return
        painter=QPainter(self.viewport()); painter.setRenderHint(QPainter.Antialiasing)
        from .theme import get_active_theme_palette
        color=QColor(get_active_theme_palette(self.editor.owner.settings.get('ui_theme','default'))['accent']); edge=color.lighter(120) if color.lightness()<125 else color.darker(115)
        anchor=self.editor._tree_items.get(plan['anchor']); rect=self.visualItemRect(anchor) if anchor else self.viewport().rect().adjusted(4,4,-4,-4)
        if plan['mode']=='inside':
            fill=QColor(color); fill.setAlpha(65); painter.setBrush(fill); painter.setPen(QPen(edge,2)); painter.drawRoundedRect(QRectF(rect).adjusted(1,1,-2,-1),3,3)
            y=self.branch_bottom(anchor); painter.setPen(QPen(edge,3)); painter.drawLine(rect.left()+self.indentation(),y,self.viewport().width()-5,y)
            label='Inside '+anchor.text(0).split(' · ')[0]; y+=4
        else:
            y=(rect.top() if plan['mode']=='before' else self.branch_bottom(anchor)) if anchor else self.viewport().height()-30
            left=rect.left() if anchor else 5
            painter.setPen(QPen(edge,3)); painter.drawLine(left,y,self.viewport().width()-5,y)
            painter.setBrush(edge); painter.drawEllipse(QPoint(left,y),3,3)
            where=(self.editor._tree_items[plan['parent']].text(0).split(' · ')[0] if plan['parent'] else 'root')
            label=('Before ' if plan['mode']=='before' else 'After ')+anchor.text(0).split(' · ')[0]+' · '+where if anchor else 'Root level · append'
            y+=4
        height=self.fontMetrics().height()+8; width=min(self.viewport().width()-8,self.fontMetrics().horizontalAdvance(label)+14)
        y=max(1,min(y,self.viewport().height()-height-1)); bubble=QRectF(4,y,width,height)
        painter.setPen(QPen(edge,1)); painter.setBrush(self.palette().base()); painter.drawRoundedRect(bubble,3,3)
        painter.setPen(self.palette().text().color()); painter.drawText(bubble.adjusted(6,0,-5,0),Qt.AlignVCenter,self.fontMetrics().elidedText(label,Qt.ElideRight,max(1,int(width)-12)))
        painter.end()

    def dropEvent(self,event):
        snapshot=getattr(self,'_drag_scene_before',None)
        if snapshot is not None and (snapshot!=self.editor.scene or self._drag_roots!=self.editor.selection_roots()):
            self.clear_drop_preview(); event.ignore(); return
        plan=self.drop_plan(event.position().toPoint()) if event.source()==self else None
        self.clear_drop_preview()
        if not plan:event.ignore(); return
        roots=self.editor.selection_roots(); ids=set(self.editor.branch())
        before=copy.deepcopy(self.editor.scene); stage=copy.deepcopy(before)
        by_id={n['id']:n for n in stage['nodes']}
        for node_id in roots:
            if plan['parent']:by_id[node_id]['parent']=plan['parent']
            else:by_id[node_id].pop('parent',None)
        moving=[n for n in stage['nodes'] if n['id'] in ids]; remaining=[n for n in stage['nodes'] if n['id'] not in ids]
        anchor=plan['anchor']; index=next((i for i,n in enumerate(remaining) if n['id']==anchor),len(remaining))
        if anchor and plan['mode'] in ('after','inside'):
            branch={anchor}
            for _ in remaining:
                added={n['id'] for n in remaining if n.get('parent') in branch}
                if added<=branch:break
                branch|=added
            index=max(i for i,n in enumerate(remaining) if n['id'] in branch)+1
        stage['nodes']=remaining[:index]+moving+remaining[index:]
        try:stage=validate(stage)
        except (ValueError,KeyError,TypeError):event.ignore(); return
        if stage!=before:
            self.editor.begin_edit(); self.editor.scene=stage; self.editor.rebuild(); self.editor.end_edit()
        event.acceptProposedAction()

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
        if hasattr(editor,'sound_panel') and focus is editor.sound_panel.rows:return editor.sound_panel.delete
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
