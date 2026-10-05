"""Transactional motion composition editor: hierarchy, layers, curves and templates."""
import copy,json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,Signal,QSignalBlocker
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QSplitter,QTreeWidget,QTreeWidgetItem,QLabel,QPushButton,QComboBox,QCheckBox,QPlainTextEdit,QLineEdit,QScrollArea,QDialogButtonBox,QMessageBox,QFileDialog,QColorDialog)
from .controls import SafeDoubleSpinBox
from .motion import validate,default_scene,KINDS,CHANNELS,curve,draw
from .easing import MODES,controls
from .easing_graph import EasingGraph

class MotionPreview(QWidget):
    def __init__(self,editor):super().__init__(editor); self.editor=editor; self.setMinimumSize(230,250)
    def paintEvent(self,event):
        from .theme_widgets import ui_color
        p=QPainter(self); p.fillRect(self.rect(),ui_color('bg_main')); d=self.editor
        ratio=d.owner.project.settings.width/d.owner.project.settings.height
        w=min(self.width(),self.height()*ratio); h=w/ratio
        image=draw(d.scene,d.position,(max(2,round(w)),max(2,round(h))),d.owner.project.settings.fps)
        p.fillRect(round((self.width()-w)/2),round((self.height()-h)/2),round(w),round(h),QColor('#000000'))
        p.drawImage(round((self.width()-w)/2),round((self.height()-h)/2),image)

class MotionEditor(QDialog):
    def __init__(self,owner,item):
        super().__init__(owner); self.owner=owner; self.original=copy.deepcopy(item); self.scene=validate(item.graphic_data.get('scene',default_scene()))
        self.scene.setdefault('canvas',[owner.project.settings.width,owner.project.settings.height])
        self.position=item.in_point; self.updating=False; self.node_id=''; self.setWindowTitle('Motion Composition'); self.resize(1180,820)
        self.setWindowModality(Qt.WindowModal)
        root=QVBoxLayout(self); split=QSplitter(Qt.Horizontal,self); root.addWidget(split,1)
        left=QWidget(split); layout=QVBoxLayout(left); layout.setContentsMargins(0,0,0,0)
        self.tree=QTreeWidget(left); self.tree.setHeaderLabel('Composition layers'); self.tree.currentItemChanged.connect(self.selected); layout.addWidget(self.tree,1)
        self.kind=QComboBox(left); self.kind.addItems(KINDS); layout.addWidget(self.kind)
        for label,fn in [('Add layer',self.add),('Duplicate branch',self.duplicate),('Remove branch',self.remove),('Move up',lambda:self.reorder(-1)),('Move down',lambda:self.reorder(1)),('Load template…',self.load_template),('Save template…',self.save_template)]:
            button=QPushButton(label,left); button.clicked.connect(fn); layout.addWidget(button)
        split.addWidget(left)
        centre=QWidget(split); middle=QVBoxLayout(centre); middle.setContentsMargins(0,0,0,0)
        self.preview=MotionPreview(self); middle.addWidget(self.preview,1)
        playback=QHBoxLayout(); self.play=QPushButton('Play',centre); self.play.clicked.connect(self.toggle); playback.addWidget(self.play)
        self.time=SafeDoubleSpinBox(centre); self.time.setDecimals(3); self.time.setRange(item.in_point,item.in_point+item.source_duration); self.time.setValue(item.in_point); self.time.setSuffix(' s'); self.time.setSingleStep(item.speed/owner.project.settings.fps); self.time.valueChanged.connect(self.seek); playback.addWidget(self.time); middle.addLayout(playback)
        self.timer=QTimer(self); self.timer.setInterval(round(1000/owner.project.settings.fps)); self.timer.timeout.connect(self.tick)
        split.addWidget(centre)
        right=QWidget(); form=QFormLayout(right); self.form=form
        self.name=QPlainTextEdit(right); self.name.setMaximumHeight(74); self.name.textChanged.connect(self.text_changed); form.addRow('Text',self.name)
        self.parent=QComboBox(right); self.parent.currentIndexChanged.connect(self.parent_changed); form.addRow('Parent',self.parent)
        self.font=QComboBox(right)
        from PySide6.QtGui import QFontDatabase
        self.font.addItems(QFontDatabase.families()); self.font.currentTextChanged.connect(lambda v:self.change('font',v)); form.addRow('Font',self.font)
        self.text_mode=QComboBox(right); self.text_mode.addItems(('none','character','word','typewriter','counter')); self.text_mode.currentTextChanged.connect(self.text_mode_changed); form.addRow('Text animation',self.text_mode)
        self.text_align=QComboBox(right); self.text_align.addItems(('left','center','right')); self.text_align.currentTextChanged.connect(lambda v:self.change('text_align',v)); form.addRow('Text alignment',self.text_align)
        self.caret=QCheckBox('Blinking typing caret',right); self.caret.toggled.connect(lambda v:self.change('caret',v)); form.addRow(self.caret)
        self.number_grouping=QCheckBox('Group thousands',right); self.number_grouping.toggled.connect(lambda v:self.change('number_grouping',v)); form.addRow(self.number_grouping)
        self.counter_affixes=[]
        for key,label in [('number_prefix','Counter prefix'),('number_suffix','Counter suffix')]:
            edit=QLineEdit(right); edit.setMaxLength(256); edit.textChanged.connect(lambda v,k=key:self.change(k,v)); form.addRow(label,edit); self.counter_affixes.append((key,edit))
        self.entry_easing=QComboBox(right); self.entry_easing.addItems(MODES); self.entry_easing.currentTextChanged.connect(lambda v:self.change('entry_easing',v)); form.addRow('Text entry easing',self.entry_easing)
        self.bold=QCheckBox('Bold',right); self.bold.toggled.connect(lambda v:self.change('bold',v)); form.addRow(self.bold)
        self.visible=QCheckBox('Visible',right); self.visible.toggled.connect(lambda v:self.change('visible',v)); form.addRow(self.visible)
        self.spins={}
        for name in (*CHANNELS,'start','end','anchor_x','anchor_y','stagger','entry_duration','entry_y','entry_rotation','entry_scale','caret_period','number_decimals'):
            spin=SafeDoubleSpinBox(right); spin.setRange(-100000,100000); spin.setDecimals(3); spin.setSingleStep(.01 if name in ('scale','scale_y','trim','morph','stagger','entry_duration') else 1)
            spin.setObjectName('motion_'+name); spin.valueChanged.connect(lambda v,n=name:self.change(n,v)); form.addRow(name.replace('_',' ').title(),spin); self.spins[name]=spin
        self.spins['number'].setRange(-1e12,1e12); self.spins['number_decimals'].setRange(0,6); self.spins['number_decimals'].setDecimals(0)
        self.spins['caret_period'].setRange(.1,10); self.spins['reveal'].setRange(0,1)
        for channel in ('fill','stroke'):
            row=QWidget(right); buttons=QHBoxLayout(row); buttons.setContentsMargins(0,0,0,0)
            button=QPushButton('Choose colour…',row); button.clicked.connect(lambda _,c=channel:self.choose_colour(c)); buttons.addWidget(button)
            clear=QPushButton('None',row); clear.clicked.connect(lambda _,c=channel:self.change(c,'none')); buttons.addWidget(clear); form.addRow(channel.title(),row)
        self.shadow=QCheckBox('Soft shape shadow',right); self.shadow.toggled.connect(lambda v:self.shadow_changed('enabled',v)); form.addRow(self.shadow)
        self.shadow_color=QPushButton('Choose shadow colour…',right); self.shadow_color.clicked.connect(self.choose_shadow_colour); form.addRow(self.shadow_color)
        self.shadow_spins={}
        for name,default,low,high in [('opacity',20,0,100),('blur',20,0,128),('x',0,-10000,10000),('y',8,-10000,10000)]:
            spin=SafeDoubleSpinBox(right); spin.setRange(low,high); spin.setValue(default); spin.valueChanged.connect(lambda v,n=name:self.shadow_changed(n,v)); form.addRow('Shadow '+name,spin); self.shadow_spins[name]=spin
        self.channel=QComboBox(right); self.channel.addItems(CHANNELS); self.channel.currentTextChanged.connect(lambda _:self.refresh()); form.addRow('Animation channel',self.channel)
        self.auto=QCheckBox('Auto-key numeric changes',right); form.addRow(self.auto)
        self.mode=QComboBox(right); self.mode.addItems(MODES); self.mode.currentTextChanged.connect(self.change_mode); form.addRow('To next key',self.mode)
        self.graph=EasingGraph(self.selected_key,right); self.graph.changed.connect(self.graph_changed); form.addRow(self.graph)
        self.bezier=[]
        for n,label in enumerate(('Handle 1 time','Handle 1 value','Handle 2 time','Handle 2 value')):
            spin=SafeDoubleSpinBox(right); spin.setRange(0,1) if n%2==0 else spin.setRange(-4,4); spin.setDecimals(3); spin.setSingleStep(.01); spin.valueChanged.connect(self.bezier_changed); form.addRow(label,spin); self.bezier.append(spin)
        self.keys=QComboBox(right); self.keys.currentIndexChanged.connect(self.jump_key); form.addRow('Keys',self.keys)
        for label,fn in [('Add / update key',self.add_key),('Remove key',self.remove_key)]:
            b=QPushButton(label,right); b.clicked.connect(fn); form.addRow(b)
        self.advanced=QPlainTextEdit(right); self.advanced.setPlaceholderText('Path, path_to, mask, gradient or image source JSON'); self.advanced.setMaximumHeight(150); form.addRow('Geometry / mask',self.advanced)
        b=QPushButton('Apply geometry',right); b.clicked.connect(self.apply_geometry); form.addRow(b)
        self.samples=SafeDoubleSpinBox(right); self.samples.setRange(1,12); self.samples.setDecimals(0); self.samples.valueChanged.connect(self.blur_changed); form.addRow('Blur samples',self.samples)
        self.shutter=SafeDoubleSpinBox(right); self.shutter.setRange(0,360); self.shutter.setSuffix(' °'); self.shutter.valueChanged.connect(self.blur_changed); form.addRow('Shutter angle',self.shutter)
        scroll=QScrollArea(split); scroll.setWidgetResizable(True); scroll.setWidget(right); scroll.setMinimumWidth(340); split.addWidget(scroll); split.setSizes([200,590,380])
        footer=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel,self); footer.accepted.connect(self.accept); footer.rejected.connect(self.reject); root.addWidget(footer)
        self.rebuild()
    def node(self):return next((n for n in self.scene['nodes'] if n['id']==self.node_id),None)
    def rebuild(self):
        self.updating=True; self.tree.clear(); items={}
        for node in self.scene['nodes']:
            item=QTreeWidgetItem([node.get('name',node['id'])+' · '+node['kind']]); item.setData(0,Qt.UserRole,node['id']); items[node['id']]=item
        for node in self.scene['nodes']:
            parent=node.get('parent','')
            if parent:items[parent].addChild(items[node['id']])
            else:self.tree.addTopLevelItem(items[node['id']])
        self.tree.expandAll(); self.updating=False
        chosen=items.get(self.node_id) or next(iter(items.values()),None)
        if chosen:self.tree.setCurrentItem(chosen)
        else:self.node_id=''; self.refresh()
    def selected(self,item,*_):
        if self.updating:return
        self.node_id=item.data(0,Qt.UserRole) if item else ''; self.refresh()
    def seek(self,t):self.position=t; self.refresh()
    def toggle(self):self.timer.stop() if self.timer.isActive() else self.timer.start(); self.play.setText('Pause' if self.timer.isActive() else 'Play')
    def tick(self):self.time.setValue(self.original.in_point+(self.position-self.original.in_point+self.original.speed/self.owner.project.settings.fps)%max(.001,self.original.source_duration))
    def refresh(self):
        self.updating=True; node=self.node() or {}
        self.name.setPlainText(node.get('text','')); self.name.setEnabled(node.get('kind')=='text')
        self.font.setCurrentText(node.get('font','Arial')); self.text_mode.setCurrentText(node.get('text_mode','none'))
        self.text_align.setCurrentText(node.get('text_align','center')); self.caret.setChecked(node.get('caret',False)); self.number_grouping.setChecked(node.get('number_grouping',True))
        for key,edit in self.counter_affixes:edit.setText(node.get(key,''))
        self.entry_easing.setCurrentText(node.get('entry_easing','Ease Out')); self.bold.setChecked(node.get('bold',True)); self.visible.setChecked(node.get('visible',True))
        self.parent.clear(); self.parent.addItem('None','')
        for n in self.scene['nodes']:
            if n['id']!=self.node_id:self.parent.addItem(n['id'],n['id'])
        self.parent.setCurrentIndex(max(0,self.parent.findData(node.get('parent',''))))
        defaults={'end':self.original.in_point+self.original.source_duration,'entry_duration':.4,'entry_y':60,'entry_scale':.85,'stagger':.04,'caret_period':.8}
        for name,spin in self.spins.items():
            value=curve(node,name,self.position) if name in CHANNELS else node.get(name,defaults.get(name,0))
            if name=='reveal' and node.get('text_mode')=='typewriter' and 'reveal' not in node and not node.get('keyframes',{}).get('reveal'):
                from .motion_text import graphemes,revealed_text
                value=len(graphemes(revealed_text(node,self.position)))/max(1,len(graphemes(node.get('text',''))))
            spin.setValue(value)
        kind=node.get('kind'); text=kind=='text'
        for field in (self.name,self.font,self.text_mode,self.text_align,self.entry_easing,self.bold):
            field.setVisible(text); label=self.form.labelForField(field)
            if label:label.setVisible(text)
        for name,spin in self.spins.items():
            visible=(text if name in ('font_size','tracking','stagger','entry_duration','entry_y','entry_rotation','entry_scale') else kind!='group' if name in ('stroke_width','width','height') else kind in ('path','ellipse','rectangle') if name=='trim' else kind=='path' if name=='morph' else kind=='rectangle' if name=='radius' else True)
            if name in ('number','number_decimals'):visible=text and node.get('text_mode')=='counter'
            if name in ('reveal','caret_period'):visible=text and node.get('text_mode')=='typewriter'
            spin.setVisible(visible); self.form.labelForField(spin).setVisible(visible)
        for field in (self.caret,):field.setVisible(text and node.get('text_mode')=='typewriter')
        for field in (self.number_grouping,*[edit for _,edit in self.counter_affixes]):
            field.setVisible(text and node.get('text_mode')=='counter'); label=self.form.labelForField(field)
            if label:label.setVisible(field.isVisibleTo(self))
        shape=kind in ('rectangle','ellipse','path'); self.shadow.setVisible(shape); self.shadow.setChecked(node.get('shadow',{}).get('enabled',False))
        self.shadow_color.setVisible(shape and self.shadow.isChecked())
        for name,spin in self.shadow_spins.items():
            spin.setValue(node.get('shadow',{}).get(name,{'opacity':20,'blur':20,'x':0,'y':8}[name])); spin.setVisible(shape and self.shadow.isChecked()); self.form.labelForField(spin).setVisible(shape and self.shadow.isChecked())
        key=self.selected_key(); self.mode.setCurrentText((key or {}).get('interpolation','Linear')); self.mode.setEnabled(bool(key))
        handles=controls((key or {}).get('bezier'))
        for spin,v in zip(self.bezier,handles):spin.setValue(v); spin.setEnabled(bool(key and key.get('interpolation')=='Bezier'))
        self.keys.clear()
        for k in node.get('keyframes',{}).get(self.channel.currentText(),[]):self.keys.addItem(f'{k["time"]:.3f}s · {k["value"]:.3f}',k['time'])
        self.keys.setCurrentIndex(self.keys.findData(self.position))
        self.advanced.setPlainText(json.dumps({k:node[k] for k in ('path','path_to','mask','gradient','source') if k in node},indent=2))
        self.samples.setValue(self.scene['motion_blur']['samples']); self.shutter.setValue(self.scene['motion_blur']['shutter'])
        self.updating=False; self.graph.update(); self.preview.update()
    def change(self,name,value):
        if self.updating or not self.node():return
        self.timer.stop(); self.play.setText('Play')
        node=self.node()
        if name in CHANNELS and self.auto.isChecked():self.put_key(name,value)
        elif name in CHANNELS:
            key=next((k for k in node.get('keyframes',{}).get(name,[]) if abs(k['time']-self.position)<.00001),None)
            if key:key['value']=value
            else:node[name]=value
        else:node[name]=value
        self.preview.update(); self.graph.update()
    def text_changed(self):self.change('text',self.name.toPlainText())
    def text_mode_changed(self,value):
        if not self.updating:self.change('text_mode',value); self.refresh()
    def shadow_changed(self,name,value):
        if not self.updating and self.node():
            self.node().setdefault('shadow',{})[name]=value; self.preview.update()
            if name=='enabled':self.refresh()
    def choose_shadow_colour(self):
        if not self.node():return
        color=QColorDialog.getColor(QColor(self.node().get('shadow',{}).get('color','#000000')),self,'Shadow colour')
        if color.isValid():self.shadow_changed('color',color.name())
    def selected_key(self):
        node=self.node() or {}; return next((k for k in node.get('keyframes',{}).get(self.channel.currentText(),[]) if abs(k['time']-self.position)<.00001),None)
    def put_key(self,name,value):
        keys=self.node().setdefault('keyframes',{}).setdefault(name,[]); previous=next((k for k in keys if abs(k['time']-self.position)<=.00001),{})
        keys[:]=[k for k in keys if abs(k['time']-self.position)>.00001]
        key=dict(time=self.position,value=value,interpolation=self.mode.currentText())
        if key['interpolation']=='Bezier':key['bezier']=controls(previous.get('bezier'))
        keys.append(key); keys.sort(key=lambda k:k['time'])
    def add_key(self):
        if self.node():self.put_key(self.channel.currentText(),self.spins[self.channel.currentText()].value()); self.refresh()
    def remove_key(self):
        if self.node():
            keys=self.node().get('keyframes',{}).get(self.channel.currentText(),[]); keys[:]=[k for k in keys if abs(k['time']-self.position)>.00001]; self.refresh()
    def change_mode(self,mode):
        if not self.updating and self.selected_key():self.selected_key()['interpolation']=mode; self.refresh()
    def graph_changed(self):self.refresh()
    def bezier_changed(self):
        if self.updating or not self.selected_key():return
        values=[s.value() for s in self.bezier]
        try:self.selected_key()['bezier']=controls(values)
        except ValueError:return
        self.graph.update(); self.preview.update()
    def jump_key(self,index):
        if not self.updating and index>=0:self.time.setValue(self.keys.itemData(index))
    def parent_changed(self,index):
        if self.updating or not self.node():return
        previous=self.node().get('parent',''); self.node()['parent']=self.parent.currentData() or ''
        try:validate(self.scene)
        except ValueError:self.node()['parent']=previous
        self.rebuild()
    def choose_colour(self,name):
        if not self.node():return
        color=QColorDialog.getColor(QColor(self.node().get(name,'#ffffff')),self,'Layer colour')
        if color.isValid():self.change(name,color.name())
    def add(self):
        from .model import uid
        node=dict(id=uid()[:8],kind=self.kind.currentText(),x=self.owner.project.settings.width/2,y=self.owner.project.settings.height/2,fill='#e8ff69',text='YOUR TEXT')
        self.scene['nodes'].append(node); self.node_id=node['id']; self.rebuild()
    def branch(self):
        ids={self.node_id}
        while True:
            more={n['id'] for n in self.scene['nodes'] if n.get('parent') in ids}
            if more<=ids:return ids
            ids|=more
    def duplicate(self):
        if not self.node():return
        from .model import uid
        ids=self.branch(); names={i:uid()[:8] for i in ids}; copies=[]
        for node in self.scene['nodes']:
            if node['id'] in ids:
                n=copy.deepcopy(node); n['id']=names[n['id']]; n['parent']=names.get(n.get('parent'),n.get('parent','')); copies.append(n)
        self.scene['nodes'].extend(copies); self.node_id=names[self.node_id]; self.rebuild()
    def remove(self):
        ids=self.branch(); self.scene['nodes']=[n for n in self.scene['nodes'] if n['id'] not in ids]; self.node_id=''; self.rebuild()
    def reorder(self,direction):
        node=self.node()
        if node:
            index=self.scene['nodes'].index(node); target=max(0,min(len(self.scene['nodes'])-1,index+direction)); self.scene['nodes'].pop(index); self.scene['nodes'].insert(target,node); self.rebuild()
    def apply_geometry(self):
        if not self.node():return
        try:
            raw=json.loads(self.advanced.toPlainText())
            if not isinstance(raw,dict) or any(k not in ('path','path_to','mask','gradient','source') for k in raw):raise ValueError('Use path, path_to, mask, gradient or source fields')
            scene=copy.deepcopy(self.scene); node=next(n for n in scene['nodes'] if n['id']==self.node_id)
            for k in ('path','path_to','mask','gradient','source'):node.pop(k,None)
            node.update(raw); self.scene=validate(scene); self.refresh()
        except (ValueError,KeyError,TypeError) as error:QMessageBox.warning(self,'Invalid geometry',str(error))
    def blur_changed(self):
        if not self.updating:self.scene['motion_blur']={'samples':round(self.samples.value()),'shutter':self.shutter.value()}; self.preview.update()
    def load_template(self):
        path,_=QFileDialog.getOpenFileName(self,'Load motion template','','Motion templates (*.json)')
        if path:
            try:
                self.scene=validate(json.loads(Path(path).read_text(encoding='utf-8-sig')))
                for node in self.scene['nodes']:
                    if node.get('kind')=='image' and node.get('source') and not Path(node['source']).is_absolute():node['source']=str((Path(path).parent/node['source']).resolve())
                self.rebuild()
            except (ValueError,OSError) as error:QMessageBox.warning(self,'Invalid template',str(error))
    def save_template(self):
        path,_=QFileDialog.getSaveFileName(self,'Save motion template','','Motion templates (*.json)')
        if path:
            import os
            try:
                scene=validate(self.scene)
                for node in scene['nodes']:
                    if node.get('kind')=='image' and node.get('source'):
                        try:node['source']=os.path.relpath(node['source'],Path(path).parent)
                        except ValueError:pass
                Path(path).write_text(json.dumps(scene,indent=2),encoding='utf-8')
            except (ValueError,OSError) as error:QMessageBox.warning(self,'Could not save template',str(error))
    def accept(self):
        current=self.owner.project.item_by_id(self.original.id)
        if current!=self.original or self.owner.current_page!=0 or self.owner.project.track_states.get(self.original.track,{}).get('locked'):
            QMessageBox.warning(self,'Composition changed','The composition changed or its track is locked. Reopen the editor.'); return
        try:scene=validate(self.scene)
        except (ValueError,TypeError,KeyError) as error:QMessageBox.warning(self,'Invalid composition',str(error)); return
        current.graphic_data['scene']=scene; self.owner.model_changed(); super().accept()
    def done(self,result):self.timer.stop(); super().done(result)
