"""Native composition layer/timing lanes with editable keyframe diamonds."""
import copy,math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QPainter,QPen,QPolygonF,QColor
from PySide6.QtWidgets import QAbstractScrollArea

class MotionTimeline(QAbstractScrollArea):
    HEADER=176; RULER=28; ROW=27
    def __init__(self,editor):
        super().__init__(editor); self.editor=editor; self.zoom=1.; self.drag=None
        self.setMinimumHeight(170); self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setMouseTracking(True); self.viewport().setAttribute(Qt.WA_OpaquePaintEvent)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.setObjectName('motion_timeline'); self.setAccessibleName('Motion layers and keyframes')
        self.rows=[]; self.refresh()
    def bounds(self):return self.editor.original.in_point,self.editor.original.in_point+self.editor.original.source_duration
    def scale(self):
        lo,hi=self.bounds(); return max(8,(self.viewport().width()-self.HEADER-24)/max(.01,hi-lo))*self.zoom
    def x(self,t):return self.HEADER+(t-self.bounds()[0])*self.scale()-self.horizontalScrollBar().value()
    def at(self,x):
        lo,hi=self.bounds(); step=self.editor.original.speed/max(1,self.editor.owner.project.settings.fps)
        value=lo+(x-self.HEADER+self.horizontalScrollBar().value())/self.scale()
        return max(lo,min(hi,lo+round((value-lo)/step)*step))
    def refresh(self):
        self.rows=[]
        for node in self.editor.scene['nodes']:
            self.rows.append((node['id'],''))
            channels=set(node.get('keyframes',{}))
            if node['id']==self.editor.node_id:channels.add(self.editor.channel.currentText())
            for channel in sorted(channels):
                if channel:self.rows.append((node['id'],channel))
        self.rows.extend(('__sound__'+c['id'],'sound') for c in self.editor.scene.get('sound_cues',[]))
        lo,hi=self.bounds(); self.verticalScrollBar().setRange(0,max(0,len(self.rows)*self.ROW+self.RULER-self.viewport().height()))
        self.verticalScrollBar().setPageStep(max(1,self.viewport().height()-self.RULER)); self.verticalScrollBar().setSingleStep(self.ROW)
        self.horizontalScrollBar().setRange(0,max(0,round((hi-lo)*self.scale()-(self.viewport().width()-self.HEADER-24))))
        self.viewport().update()
    def resizeEvent(self,event):super().resizeEvent(event); self.refresh()
    def row_rect(self,index):return QRectF(0,self.RULER+index*self.ROW-self.verticalScrollBar().value(),self.viewport().width(),self.ROW)
    def node(self,node_id):return next(n for n in self.editor.scene['nodes'] if n['id']==node_id)
    def paintEvent(self,event):
        from .theme_widgets import ui_color
        p=QPainter(self.viewport()); p.fillRect(self.viewport().rect(),ui_color('bg_main')); p.setRenderHint(QPainter.Antialiasing)
        lo,hi=self.bounds(); width=self.viewport().width()
        p.save(); p.setClipRect(QRectF(0,self.RULER,width,self.viewport().height()-self.RULER))
        for index,(node_id,channel) in enumerate(self.rows):
            r=self.row_rect(index)
            if r.bottom()<self.RULER or r.top()>self.viewport().height():continue
            if channel=='sound':
                from .motion_audio import at
                from pathlib import Path
                cue=next(c for c in self.editor.scene['sound_cues'] if '__sound__'+c['id']==node_id)
                stamp=at(cue,self.editor.scene)
                p.fillRect(r,ui_color('bg_panel')); p.setPen(ui_color('text_main'))
                p.drawText(QRectF(8,r.top(),self.HEADER-16,r.height()),Qt.AlignVCenter,p.fontMetrics().elidedText('♪ '+Path(cue['source']).name,Qt.ElideRight,self.HEADER-16))
                if stamp is not None:
                    p.save(); p.setClipRect(QRectF(self.HEADER,r.top(),width-self.HEADER,r.height()),Qt.IntersectClip)
                    p.setBrush(ui_color('accent')); p.setPen(Qt.NoPen)
                    p.drawRoundedRect(QRectF(self.x(stamp),r.top()+6,max(2,cue['duration']*self.scale()),r.height()-12),3,3); p.restore()
                continue
            node=self.node(node_id); chosen=node_id==self.editor.node_id
            p.fillRect(r,ui_color('bg_panel') if chosen else ui_color('bg_main'))
            p.setPen(ui_color('border')); p.drawLine(r.bottomLeft(),r.bottomRight())
            p.save(); p.setClipRect(QRectF(self.HEADER,r.top(),width-self.HEADER,r.height()),Qt.IntersectClip)
            if not channel:
                start=max(lo,node.get('start',0)); end=min(hi,node.get('end',hi)); bar=QRectF(self.x(start),r.top()+5,max(1,self.x(end)-self.x(start)),r.height()-10)
                p.setPen(Qt.NoPen); p.setBrush(QColor('#3c6c90') if node.get('visible',True) else ui_color('border')); p.drawRoundedRect(bar,3,3)
                p.setPen(QPen(QColor('#58a9ff'),2 if chosen else 1)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(bar,3,3)
            else:
                p.setPen(QPen(ui_color('text_sub'),1)); p.drawLine(QPointF(self.HEADER,r.center().y()),QPointF(width,r.center().y()))
                for key in node.get('keyframes',{}).get(channel,[]):
                    x=self.x(key['time'])
                    if x<self.HEADER-6 or x>width+6:continue
                    selected=chosen and channel==self.editor.channel.currentText() and abs(key['time']-self.editor.position)<1e-5
                    p.setPen(QPen(QColor('#0c1720'),1)); p.setBrush(QColor('#ffe600') if selected else QColor('#79baff'))
                    p.drawPolygon(QPolygonF([QPointF(x,r.center().y()-5),QPointF(x+5,r.center().y()),QPointF(x,r.center().y()+5),QPointF(x-5,r.center().y())]))
            p.restore(); p.fillRect(QRectF(0,r.top(),self.HEADER,r.height()),ui_color('bg_panel'))
            p.setPen(ui_color('text_main')); label=('   '+channel.replace('_',' ').title()) if channel else node.get('name',node_id)
            p.drawText(QRectF(10,r.top(),self.HEADER-16,r.height()),Qt.AlignVCenter,p.fontMetrics().elidedText(label,Qt.ElideRight,self.HEADER-16))
        p.restore(); p.fillRect(QRectF(0,0,width,self.RULER),ui_color('bg_panel'))
        step=next((s for s in (.1,.25,.5,1,2,5,10,30,60,120,300) if s*self.scale()>=65),300)
        begin=max(lo,lo+self.horizontalScrollBar().value()/self.scale())
        for n in range(math.floor(begin/step),math.ceil(hi/step)+1):
            x=self.x(n*step)
            if x<self.HEADER:continue
            if x>width:break
            p.setPen(ui_color('text_sub')); p.drawLine(round(x),20,round(x),self.RULER)
            p.drawText(QRectF(x+4,0,65,20),Qt.AlignVCenter,f'{n*step:g}s')
        x=self.x(self.editor.position)
        if self.HEADER<=x<=width:
            p.setPen(QPen(QColor('#f04d5b'),1)); p.drawLine(round(x),0,round(x),self.viewport().height())
        p.setPen(ui_color('text_main')); p.drawText(QRectF(8,0,self.HEADER-12,self.RULER),Qt.AlignVCenter,'Layers / animated properties')
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return super().mousePressEvent(event)
        self.setFocus(); pos=event.position(); self.editor.pause()
        if pos.y()<self.RULER:self.drag={'mode':'scrub'}; self.editor.seek(self.at(pos.x())); return
        index=int((pos.y()-self.RULER+self.verticalScrollBar().value())//self.ROW)
        if not 0<=index<len(self.rows):return
        node_id,channel=self.rows[index]
        if channel=='sound':
            panel=self.editor.sound_panel; self.editor.property_tabs.setCurrentWidget(panel)
            for row in range(panel.rows.count()):
                if '__sound__'+panel.rows.item(row).data(Qt.UserRole)==node_id:panel.rows.setCurrentRow(row); break
            if pos.x()>=self.HEADER:self.editor.seek(self.at(pos.x()))
            return
        self.editor.select_node(node_id)
        if channel:self.editor.channel.setCurrentText(channel)
        if pos.x()<self.HEADER:return
        node=self.node(node_id); r=self.row_rect(index); lo,hi=self.bounds()
        key=next((k for k in node.get('keyframes',{}).get(channel,[]) if abs(self.x(k['time'])-pos.x())<8),None) if channel else None
        if key:
            self.editor.begin_edit(); self.editor.seek(key['time'])
            self.drag=dict(mode='key',node_id=node_id,channel=channel,key=key,original=copy.deepcopy(key),press=pos.x(),cues=copy.deepcopy(self.editor.scene.get('sound_cues',[])))
        elif not channel and self.x(max(lo,node.get('start',0)))<=pos.x()<=self.x(min(hi,node.get('end',hi))):
            self.editor.begin_edit(); start=node.get('start',0); end=node.get('end',hi)
            mode='start' if abs(pos.x()-self.x(start))<7 else 'end' if abs(pos.x()-self.x(end))<7 else 'layer'
            ids={node_id}
            while True:
                more={n['id'] for n in self.editor.scene['nodes'] if n.get('parent') in ids}
                if more<=ids:break
                ids|=more
            self.drag=dict(mode=mode,node_id=node_id,original=copy.deepcopy(node),branch={n['id']:copy.deepcopy(n) for n in self.editor.scene['nodes'] if n['id'] in ids},press=pos.x(),start=start,end=min(end,hi),cues=copy.deepcopy(self.editor.scene.get('sound_cues',[])))
        else:self.drag={'mode':'scrub'}; self.editor.seek(self.at(pos.x()))
    def mouseMoveEvent(self,event):
        if not self.drag:return super().mouseMoveEvent(event)
        d=self.drag
        if d['mode']=='scrub':self.editor.seek(self.at(event.position().x())); return
        if abs(event.position().x()-d['press'])<3 and not d.get('moved'):return
        d['moved']=True; node=self.node(d['node_id']); value=self.at(event.position().x()); lo,hi=self.bounds()
        if d['mode']=='key':
            for cue in self.editor.scene.get('sound_cues',[]):
                original=next((c for c in d['cues'] if c['id']==cue['id']),{})
                if original.get('event')=='keyframe' and original.get('node_id')==d['node_id'] and original.get('channel')==d['channel'] and abs(original.get('key_time',-1)-d['original']['time'])<1e-7:cue['key_time']=value
            d['key']['time']=value; keys=node['keyframes'][d['channel']]
            keys[:]=[k for k in keys if k is d['key'] or abs(k['time']-value)>1e-5]; keys.sort(key=lambda k:k['time']); self.editor.seek(value)
        else:
            step=self.editor.original.speed/max(1,self.editor.owner.project.settings.fps)
            if d['mode']=='start':node['start']=max(0,min(value,d['end']-step))
            elif d['mode']=='end':node['end']=max(d['start']+step,value)
            else:
                delta=round((event.position().x()-d['press'])/self.scale()/step)*step; delta=max(-d['start'],min(hi-d['end'],delta))
                node['start']=d['start']+delta; node['end']=d['end']+delta
                for node_id,before in d['branch'].items():
                    changed=self.node(node_id)
                    if node_id!=node['id']:
                        changed['start']=before.get('start',0)+delta
                        if 'end' in before:changed['end']=before['end']+delta
                    changed['keyframes']=copy.deepcopy(before.get('keyframes',{}))
                    for keys in changed['keyframes'].values():
                        for k in keys:k['time']+=delta
                for cue in self.editor.scene.get('sound_cues',[]):
                    original=next((c for c in d['cues'] if c['id']==cue['id']),{})
                    if original.get('event')=='keyframe' and original.get('node_id') in d['branch']:cue['key_time']=original['key_time']+delta
            self.editor.refresh()
        self.viewport().update(); self.editor.preview.update()
    def mouseReleaseEvent(self,event):
        if self.drag and self.drag['mode']!='scrub':self.editor.end_edit()
        self.drag=None; self.editor.refresh()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.drag:
            self.editor.cancel_edit(); self.drag=None; return
        if event.key()==Qt.Key_Delete:self.editor.remove_key(); return
        super().keyPressEvent(event)
    def set_zoom(self,value):self.zoom=max(1,min(20,value)); self.refresh()
