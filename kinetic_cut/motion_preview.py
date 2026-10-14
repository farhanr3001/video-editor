"""Composition preview selection, transform handles and centre alignment guides."""
import copy,math
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPointF,QSignalBlocker
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QPlainTextEdit
from .motion import draw,curve
from .motion_geometry import layout

class MotionPreview(QWidget):
    def __init__(self,editor):
        super().__init__(editor); self.editor=editor; self.drag=None; self.guides=set(); self.view_scale=1.; self.pan=QPointF(); self._frame_key=None; self._frame=None
        self.setMinimumSize(220,210); self.setMouseTracking(True); self.setFocusPolicy(Qt.StrongFocus)
        self.setObjectName('motion_preview'); self.setAccessibleName('Composition preview with layer transform handles')
    def canvas_rect(self):
        w,h=self.editor.owner.project.settings.width,self.editor.owner.project.settings.height; factor=min(self.width()/w,self.height()/h)
        factor*=self.view_scale
        return QRectF((self.width()-w*factor)/2+self.pan.x(),(self.height()-h*factor)/2+self.pan.y(),w*factor,h*factor)
    def set_zoom(self,value):self.view_scale=max(.25,min(4,float(value))); self.update()
    def safe_rect(self):
        r=self.canvas_rect()
        return r.adjusted(r.width()*.12,r.height()*.18,-r.width()*.12,-r.height()*.18)
    def fit(self):
        self.pan=QPointF(); self.view_scale=1.
        blocker=QSignalBlocker(self.editor.preview_zoom); self.editor.preview_zoom.setValue(1); del blocker; self.update()
    def wheelEvent(self,event):
        before=self.to_scene(event.position()); self.set_zoom(self.view_scale*(1.15 if event.angleDelta().y()>0 else 1/1.15))
        self.pan+=event.position()-self.from_scene(before)
        blocker=QSignalBlocker(self.editor.preview_zoom); self.editor.preview_zoom.setValue(self.view_scale); del blocker; event.accept()
    def to_scene(self,point):
        r=self.canvas_rect(); w,h=self.editor.scene['canvas']; return QPointF((point.x()-r.x())*w/r.width(),(point.y()-r.y())*h/r.height())
    def from_scene(self,point):
        r=self.canvas_rect(); w,h=self.editor.scene['canvas']; return QPointF(r.x()+point.x()*r.width()/w,r.y()+point.y()*r.height()/h)
    def geometry(self):return layout(self.editor.scene,self.editor.position)
    def handles(self,entry):
        r=entry['world'].mapRect(entry['local'].boundingRect())
        points=[r.topLeft(),r.topRight(),r.bottomRight(),r.bottomLeft()]
        result={str(i):self.from_scene(point) for i,point in enumerate(points)}
        top=self.from_scene(QPointF(r.center().x(),r.top())); result['rotate']=top-QPointF(0,22)
        return result
    def paintEvent(self,event):
        from .theme_widgets import ui_color
        p=QPainter(self); p.fillRect(self.rect(),ui_color('bg_main')); d=self.editor; r=self.canvas_rect()
        p.fillRect(r,QColor('#111317')); factor=min(1,math.sqrt(4_000_000/max(1,r.width()*r.height())))
        size=(max(2,round(r.width()*factor)),max(2,round(r.height()*factor)))
        assets=[]
        for node in d.scene['nodes']:
            if node['kind']=='image':
                try:
                    stat=Path(node.get('source','')).stat(); assets.append((node['id'],stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
                except OSError:assets.append((node['id'],None))
        key=(d.render_revision,d.position,size,d.owner.project.settings.fps,tuple(assets))
        if key!=self._frame_key:self._frame=draw(d.scene,d.position,size,d.owner.project.settings.fps); self._frame_key=key
        p.drawImage(r,self._frame)
        # The safe area is a guide only, never part of the composition/export.
        if d.safe.isChecked():
            p.setPen(QPen(QColor(255,255,255,80),1,Qt.DashLine)); p.setBrush(Qt.NoBrush)
            p.drawRect(self.safe_rect())
        entries,_=self.geometry(); entry=entries.get(d.node_id)
        for node_id in d.selected_ids-{d.node_id}:
            other=entries.get(node_id)
            if other and other['visible'] and not other['local'].isEmpty():
                rect=other['hit'].boundingRect(); p.setPen(QPen(QColor('#63b0ff'),1)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(self.from_scene(rect.topLeft()),self.from_scene(rect.bottomRight())))
        if entry and entry['visible'] and not entry['local'].isEmpty():
            rect=entry['world'].mapRect(entry['local'].boundingRect()); a=self.from_scene(rect.topLeft()); b=self.from_scene(rect.bottomRight())
            p.setPen(QPen(QColor('#63b0ff'),1)); p.setBrush(Qt.NoBrush); p.drawRect(QRectF(a,b))
            for name,point in self.handles(entry).items():
                p.setBrush(QColor('#3d8cff') if self.drag and self.drag['mode']==name else QColor('#f5f6fa'))
                if name=='rotate':p.drawEllipse(point,4,4)
                else:p.drawRect(QRectF(point.x()-4,point.y()-4,8,8))
        if self.guides:
            p.setPen(QPen(QColor('#398fff'),1))
            if 'x' in self.guides:p.drawLine(QPointF(r.center().x(),r.top()),QPointF(r.center().x(),r.bottom()))
            if 'y' in self.guides:p.drawLine(QPointF(r.left(),r.center().y()),QPointF(r.right(),r.center().y()))
        if self.drag and self.drag['mode']=='marquee':
            p.setPen(QPen(QColor('#63b0ff'),1)); p.setBrush(QColor(61,140,255,35)); p.drawRect(QRectF(self.drag['press'],self.drag['end']).normalized())
    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton:self.drag=dict(mode='pan',press=event.position(),original=QPointF(self.pan)); return
        if event.button()!=Qt.LeftButton:return
        self.setFocus(); d=self.editor; d.pause(); entries,ordered=self.geometry(); selected=entries.get(d.node_id); mode='move'
        if selected and selected['visible']:
            for name,point in self.handles(selected).items():
                if (point-event.position()).manhattanLength()<=10:mode=name; break
        if mode=='move':
            point=self.to_scene(event.position())
            picked=next((node_id for node_id in reversed(ordered) if entries[node_id]['visible'] and entries[node_id]['node']['kind']!='group' and entries[node_id]['hit'].contains(point)),None)
            if not picked:
                self.drag=dict(mode='marquee',press=event.position(),end=event.position(),previous=set(d.selected_ids) if event.modifiers()&Qt.ControlModifier else set()); self.update(); return
            if event.modifiers()&Qt.ControlModifier:
                ids=set(d.selected_ids); ids.symmetric_difference_update({picked}); d.select_nodes(ids,picked); self.update(); return
            if picked not in d.selected_ids:d.select_node(picked)
            else:d.select_nodes(d.selected_ids,picked)
            selected=entries[picked]
        if not selected:return
        inverse,ok=selected['parent'].inverted()
        if not ok:return
        d.begin_edit(); self.drag=dict(mode=mode,node=copy.deepcopy(d.node()),entry=selected,press=self.to_scene(event.position()),inverse=inverse,selection=set(d.selected_ids),nodes={i:copy.deepcopy(entries[i]['node']) for i in d.selection_roots()},entries=entries)
    def mouseMoveEvent(self,event):
        if not self.drag:return
        if self.drag['mode']=='marquee':self.drag['end']=event.position(); self.update(); return
        if self.drag['mode']=='pan':self.pan=self.drag['original']+event.position()-self.drag['press']; self.update(); return
        d=self.editor; old=self.drag['node']; mode=self.drag['mode']; point=self.to_scene(event.position()); inverse=self.drag['inverse']; values={}
        if mode=='move':
            delta=inverse.map(point)-inverse.map(self.drag['press']); values={'x':curve(old,'x',d.position)+delta.x(),'y':curve(old,'y',d.position)+delta.y()}; self.guides=set()
            # Small snap threshold in display pixels, independent of zoom/canvas.
            world_delta=point-self.drag['press']; bounds=self.drag['entry']['hit'].boundingRect().translated(world_delta)
            w,h=d.scene['canvas']; correction=QPointF()
            if abs(bounds.center().x()-w/2)*self.canvas_rect().width()/w<5:correction.setX(w/2-bounds.center().x()); self.guides.add('x')
            if abs(bounds.center().y()-h/2)*self.canvas_rect().height()/h<5:correction.setY(h/2-bounds.center().y()); self.guides.add('y')
            adjust=inverse.map(point+correction)-inverse.map(point); values['x']+=adjust.x(); values['y']+=adjust.y()
        elif mode=='rotate':
            origin=self.drag['entry']['world'].map(self.drag['entry']['local'].boundingRect().center()); center=inverse.map(origin); a=inverse.map(self.drag['press'])-center; b=inverse.map(point)-center
            values={'rotation':curve(old,'rotation',d.position)+math.degrees(math.atan2(b.y(),b.x())-math.atan2(a.y(),a.x()))}
        else:
            center=self.drag['entry']['hit'].boundingRect().center(); before=self.drag['press']-center; after=point-center
            ratio=max(.01,min(100,math.hypot(after.x(),after.y())/max(.01,math.hypot(before.x(),before.y()))))
            if old['kind']=='text':values={'font_size':max(1,min(100000,curve(old,'font_size',d.position)*ratio))}
            else:values={'scale':max(.001,min(100,curve(old,'scale',d.position)*ratio)),'scale_y':max(.001,min(100,curve(old,'scale_y',d.position)*ratio))}
        primary=d.node_id; selection=set(d.selected_ids)
        for node_id,original in self.drag['nodes'].items():
            d.node_id=node_id; d.selected_ids={node_id}
            changes=values
            if mode=='move':
                inv,ok=self.drag['entries'][node_id]['parent'].inverted()
                if not ok:continue
                shift=inv.map(point+correction)-inv.map(self.drag['press'])
                changes={'x':curve(original,'x',d.position)+shift.x(),'y':curve(original,'y',d.position)+shift.y()}
            elif mode=='rotate':changes={'rotation':curve(original,'rotation',d.position)+values['rotation']-curve(old,'rotation',d.position)}
            elif original['kind']=='text':changes={'font_size':max(1,min(100000,curve(original,'font_size',d.position)*ratio))}
            else:changes={channel:max(.001,min(100,curve(original,channel,d.position)*ratio)) for channel in ('scale','scale_y')}
            for channel,value in changes.items():d.change(channel,value)
        d.node_id=primary; d.selected_ids=selection
        d.refresh()
    def mouseReleaseEvent(self,event):
        if self.drag and self.drag['mode']=='marquee':
            rect=QRectF(self.to_scene(self.drag['press']),self.to_scene(event.position())).normalized(); entries,ordered=self.geometry()
            ids={i for i in ordered if entries[i]['visible'] and entries[i]['node']['kind']!='group' and entries[i]['hit'].intersects(rect)}
            self.editor.select_nodes(ids|self.drag['previous'])
        elif self.drag and self.drag['mode']!='pan':self.editor.end_edit()
        self.drag=None; self.guides=set(); self.update()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.drag:
            if self.drag['mode']=='pan':self.pan=self.drag['original']
            else:self.editor.cancel_edit()
            self.drag=None; self.guides=set(); self.update(); return
        super().keyPressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        entries,ordered=self.geometry(); point=self.to_scene(event.position())
        node_id=next((i for i in reversed(ordered) if entries[i]['visible'] and entries[i]['node']['kind']=='text' and entries[i]['hit'].contains(point)),None)
        if not node_id:return
        self.drag=None; self.editor.end_edit(); self.editor.select_node(node_id); self.editor.pause()
        rect=entries[node_id]['hit'].boundingRect(); display=QRectF(self.from_scene(rect.topLeft()),self.from_scene(rect.bottomRight())).normalized()
        edit=InlineMotionText(self,self.editor,node_id); self.inline_editor=edit
        edit.setGeometry(display.adjusted(-4,-4,4,4).toAlignedRect()); edit.setMinimumSize(100,42); edit.show(); edit.setFocus(); edit.selectAll()

class InlineMotionText(QPlainTextEdit):
    def __init__(self,preview,editor,node_id):
        super().__init__(preview); self.editor=editor; self.node_id=node_id; self.finished=False
        self.setPlainText(editor.node().get('text','')); editor.begin_edit()
        self.textChanged.connect(lambda:editor.change('text',self.toPlainText()))
        self.setToolTip('Ctrl+Enter to finish · Escape to cancel')
    def finish(self,cancel=False):
        if self.finished:return
        self.finished=True
        self.parentWidget().inline_editor=None
        if cancel:self.editor.cancel_edit()
        else:self.editor.end_edit()
        self.hide(); self.deleteLater(); self.editor.preview.setFocus(); self.editor.refresh()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:self.finish(True); return
        if event.key() in (Qt.Key_Return,Qt.Key_Enter) and event.modifiers()&Qt.ControlModifier:self.finish(); return
        super().keyPressEvent(event)
    def focusOutEvent(self,event):
        super().focusOutEvent(event); self.finish()
