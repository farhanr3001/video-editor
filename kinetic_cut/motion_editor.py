"""Transactional motion composition editor: hierarchy, layers, curves and templates."""
import copy,json,time
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,Signal,QSignalBlocker
from PySide6.QtGui import QPainter,QColor,QShortcut,QKeySequence
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QSplitter,QTreeWidget,QTreeWidgetItem,QLabel,QPushButton,QComboBox,QCheckBox,QPlainTextEdit,QLineEdit,QScrollArea,QDialogButtonBox,QMessageBox,QFileDialog,QColorDialog,QTabWidget)
from .controls import SafeDoubleSpinBox
from .motion import validate,default_scene,KINDS,CHANNELS,curve,draw
from .easing import MODES,controls
from .easing_graph import EasingGraph

from .motion_preview import MotionPreview
from .motion_controls import MotionLayerTree,MotionInputRouter

class MotionEasingGraph(EasingGraph):
    def __init__(self,editor,parent):super().__init__(editor.selected_key,parent); self.editor=editor
    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if self.drag is not None:self.editor.begin_edit()
    def mouseReleaseEvent(self,event):super().mouseReleaseEvent(event); self.editor.end_edit()

class MotionEditor(MotionInputRouter,QDialog):
    def __init__(self,owner,item):
        super().__init__(owner); self.owner=owner; self.original=copy.deepcopy(item); self.scene=validate(item.graphic_data.get('scene',default_scene()))
        self.scene.setdefault('canvas',[owner.project.settings.width,owner.project.settings.height])
        self.position=item.in_point; self.updating=False; self.node_id=''; self.selected_ids=set(); self.setWindowTitle('Motion Composition'); self.resize(1180,820)
        self._undo=[]; self._redo=[]; self._edit_before=None; self._history_busy=False
        self.render_revision=0
        self.setWindowModality(Qt.WindowModal)
        root=QVBoxLayout(self); workspace=QSplitter(Qt.Vertical,self); root.addWidget(workspace,1)
        split=QSplitter(Qt.Horizontal,workspace)
        left=QWidget(split); layout=QVBoxLayout(left); layout.setContentsMargins(0,0,0,0)
        self.tree=MotionLayerTree(self); self.tree.setHeaderLabel('Composition layers'); self.tree.currentItemChanged.connect(self.selected); self.tree.itemSelectionChanged.connect(self.selection_changed); layout.addWidget(self.tree,1)
        self.kind=QComboBox(left); self.kind.addItems(KINDS); layout.addWidget(self.kind)
        from .icons import lucide_icon
        layer_tools=QHBoxLayout(); layer_tools.setSpacing(2)
        for label,icon,fn in [('Add layer','plus',self.add),('Duplicate branch','layers',self.duplicate),('Remove branch','trash-2',self.remove),('Move up','chevron-up',lambda:self.reorder(-1)),('Move down','chevron-down',lambda:self.reorder(1)),('Load template…','folder-open',self.load_template),('Save template…','save',self.save_template)]:
            button=QPushButton(left); button.setIcon(lucide_icon(icon)); button.setToolTip(label); button.setAccessibleName(label); button.setFixedWidth(26); button.clicked.connect(fn); layer_tools.addWidget(button)
        layout.addLayout(layer_tools)
        split.addWidget(left)
        centre=QWidget(split); middle=QVBoxLayout(centre); middle.setContentsMargins(0,0,0,0)
        self.preview=MotionPreview(self); middle.addWidget(self.preview,1)
        view_tools=QHBoxLayout(); fit=QPushButton('Fit',centre); fit.clicked.connect(self.preview.fit); view_tools.addWidget(fit)
        view_tools.addWidget(QLabel('Canvas zoom',centre)); self.preview_zoom=SafeDoubleSpinBox(centre); self.preview_zoom.setRange(.25,4); self.preview_zoom.setSingleStep(.25); self.preview_zoom.setValue(1); self.preview_zoom.setSuffix(' ×'); self.preview_zoom.valueChanged.connect(self.preview.set_zoom); view_tools.addWidget(self.preview_zoom)
        self.preview.setToolTip('Click a layer to select · Drag handles to resize · Wheel to zoom · Middle-drag to pan')
        middle.addLayout(view_tools)
        playback=QHBoxLayout()
        from .icons import lucide_icon
        for label,icon,fn in [('Start','skip-back',lambda:self.navigate('start')),('Previous frame','chevron-left',lambda:self.navigate('frame',-1))]:
            button=QPushButton(centre); button.setIcon(lucide_icon(icon)); button.setToolTip(label); button.clicked.connect(fn); playback.addWidget(button)
        self.play=QPushButton('Play',centre); self.play.clicked.connect(self.toggle); playback.addWidget(self.play)
        for label,icon,fn in [('Next frame','chevron-right',lambda:self.navigate('frame',1)),('End','skip-forward',lambda:self.navigate('end'))]:
            button=QPushButton(centre); button.setIcon(lucide_icon(icon)); button.setToolTip(label); button.clicked.connect(fn); playback.addWidget(button)
        self.time=SafeDoubleSpinBox(centre); self.time.setDecimals(3); self.time.setRange(item.in_point,item.in_point+item.source_duration); self.time.setValue(item.in_point); self.time.setSuffix(' s'); self.time.setSingleStep(item.speed/owner.project.settings.fps); self.time.valueChanged.connect(self.seek); playback.addWidget(self.time); middle.addLayout(playback)
        self.timer=QTimer(self); self.timer.setInterval(round(1000/owner.project.settings.fps)); self.timer.timeout.connect(self.tick)
        self.timer.setTimerType(Qt.PreciseTimer)
        options=QHBoxLayout(); self.loop=QCheckBox('Loop',centre); options.addWidget(self.loop)
        self.safe=QCheckBox('Platform safe area',centre); self.safe.setChecked(True); self.safe.toggled.connect(self.preview.update); options.addWidget(self.safe)
        for label,fn in [('Previous key',lambda:self.navigate('key',-1)),('Next key',lambda:self.navigate('key',1))]:
            button=QPushButton(label,centre); button.clicked.connect(fn); options.addWidget(button)
        middle.addLayout(options)
        split.addWidget(centre)
        right=QWidget(); form=QFormLayout(right); self.form=form
        self.name=QPlainTextEdit(right); self.name.setMaximumHeight(74); self.name.textChanged.connect(self.text_changed); form.addRow('Text',self.name)
        self.parent=QComboBox(right); self.parent.currentIndexChanged.connect(self.parent_changed); form.addRow('Parent',self.parent)
        self.font=QComboBox(right)
        from PySide6.QtGui import QFontDatabase
        self.font.addItems(QFontDatabase.families()); self.font.currentTextChanged.connect(lambda v:self.change('font',v)); form.addRow('Font',self.font)
        self.text_mode=QComboBox(right); self.text_mode.addItems(('none','character','word','typewriter','counter','rolling')); self.text_mode.currentTextChanged.connect(self.text_mode_changed); form.addRow('Text animation',self.text_mode)
        self.layer_name=QLineEdit(right); self.layer_name.textChanged.connect(lambda v:self.change('name',v)); form.addRow('Layer name',self.layer_name)
        self.image_fit=QComboBox(right); self.image_fit.addItems(('contain','cover','stretch')); self.image_fit.currentTextChanged.connect(lambda v:self.change('image_fit',v)); form.addRow('Image fit',self.image_fit)
        self.image_button=QPushButton('Choose image…',right); self.image_button.clicked.connect(self.choose_image); form.addRow(self.image_button)
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
        self.scale_link=QCheckBox('Link scale X / Y',right); self.scale_link.setChecked(True); self.scale_link.setToolTip('Resize both scale axes proportionally'); form.insertRow(form.getWidgetPosition(self.spins['scale_y'])[0]+1,self.scale_link)
        self.scale_link.toggled.connect(lambda value:self.change('scale_linked',value))
        self.key_value=SafeDoubleSpinBox(right); self.key_value.setRange(-1e12,1e12); self.key_value.setDecimals(3); self.key_value.valueChanged.connect(lambda v:self.change(self.channel.currentText(),v)); form.addRow('Channel value',self.key_value)
        self.mode=QComboBox(right); self.mode.addItems(MODES); self.mode.currentTextChanged.connect(self.change_mode); form.addRow('To next key',self.mode)
        self.graph=MotionEasingGraph(self,right); self.graph.changed.connect(self.graph_changed); form.addRow(self.graph)
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
        tabs=QTabWidget(split); tabs.setMinimumWidth(340)
        animation={self.text_mode,self.entry_easing,self.caret,self.number_grouping,self.channel,self.auto,self.key_value,self.mode,self.graph,self.keys,*self.bezier,*[edit for _,edit in self.counter_affixes]}
        animation.update(self.spins[n] for n in ('stagger','entry_duration','entry_y','entry_rotation','entry_scale','reveal','caret_period','number','number_decimals'))
        geometry={self.advanced,self.samples,self.shutter,self.shadow,self.shadow_color,*self.shadow_spins.values(),*[self.spins[n] for n in ('trim','morph')]}
        pages={}; self._property_labels={}
        for label in ('Layer','Animation','Geometry'):
            page=QWidget(); page_form=QFormLayout(page); page_form.setContentsMargins(8,8,8,8)
            scroll=QScrollArea(tabs); scroll.setWidgetResizable(True); scroll.setWidget(page); tabs.addTab(scroll,label); pages[label]=(page,page_form)
        while form.rowCount():
            row=form.takeRow(0); field=row.fieldItem.widget(); label=row.labelItem.widget() if row.labelItem else None
            page_name='Animation' if field in animation or isinstance(field,QPushButton) and field.text() in ('Add / update key','Remove key') else 'Geometry' if field in geometry or isinstance(field,QPushButton) and field.text()=='Apply geometry' else 'Layer'
            page,page_form=pages[page_name]; field.setParent(page)
            if label:label.setParent(page); self._property_labels[field]=label; page_form.addRow(label,field)
            else:page_form.addRow(field)
        self.property_tabs=tabs; right.deleteLater(); split.addWidget(tabs); split.setSizes([190,570,360])
        from .motion_audio_ui import SoundCuePanel
        self.sound_panel=SoundCuePanel(self); tabs.addTab(self.sound_panel,'Sound')
        from .motion_timeline import MotionTimeline
        bottom=QWidget(workspace); bottom_layout=QVBoxLayout(bottom); bottom_layout.setContentsMargins(0,0,0,0)
        tools=QHBoxLayout(); self.undo_button=QPushButton('Undo',bottom); self.redo_button=QPushButton('Redo',bottom)
        self.undo_button.clicked.connect(lambda:self.local_history(-1)); self.redo_button.clicked.connect(lambda:self.local_history(1))
        tools.addWidget(self.undo_button); tools.addWidget(self.redo_button)
        tools.addWidget(QLabel('Drag diamonds to retime keys · Drag layer edges to trim',bottom)); tools.addStretch()
        self.zoom=SafeDoubleSpinBox(bottom); self.zoom.setRange(1,20); self.zoom.setValue(1); self.zoom.setSuffix(' ×'); self.zoom.valueChanged.connect(lambda v:self.timeline.set_zoom(v)); tools.addWidget(QLabel('Timeline zoom')); tools.addWidget(self.zoom)
        bottom_layout.addLayout(tools); self.timeline=MotionTimeline(self); bottom_layout.addWidget(self.timeline,1); workspace.setSizes([590,210])
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        footer=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel,self); footer.accepted.connect(self.accept); footer.rejected.connect(self.reject); root.addWidget(footer)
        self.rebuild()
    def node(self):return next((n for n in self.scene['nodes'] if n['id']==self.node_id),None)
    def selected_nodes(self):
        ids=self.selected_ids if self.node_id in self.selected_ids else {self.node_id}
        return [n for n in self.scene['nodes'] if n['id'] in ids]
    def selection_roots(self):
        selected={n['id'] for n in self.selected_nodes()}; by_id={n['id']:n for n in self.scene['nodes']}
        def nested(node):
            parent=node.get('parent','')
            while parent:
                if parent in selected:return True
                parent=by_id.get(parent,{}).get('parent','')
            return False
        return [n['id'] for n in self.selected_nodes() if not nested(n)]
    def selection_changed(self):
        if self.updating:return
        self.selected_ids={i.data(0,Qt.UserRole) for i in self.tree.selectedItems()}
        if self.node_id not in self.selected_ids:self.node_id=next(iter(self.selected_ids),'')
        self.refresh()
    def select_nodes(self,ids,primary=None):
        valid={n['id'] for n in self.scene['nodes']}; self.selected_ids=set(ids)&valid
        self.node_id=primary if primary in self.selected_ids else next((n['id'] for n in self.scene['nodes'] if n['id'] in self.selected_ids),'')
        self.updating=True
        iterator=__import__('PySide6.QtWidgets',fromlist=['QTreeWidgetItemIterator']).QTreeWidgetItemIterator(self.tree)
        current=None
        while iterator.value():
            item=iterator.value(); item.setSelected(item.data(0,Qt.UserRole) in self.selected_ids)
            if item.data(0,Qt.UserRole)==self.node_id:current=item
            iterator+=1
        if current:
            from PySide6.QtCore import QItemSelectionModel
            self.tree.setCurrentItem(current,0,QItemSelectionModel.NoUpdate)
        self.updating=False; self.refresh()
    def label_for_field(self,field):return self._property_labels.get(field) if hasattr(self,'_property_labels') else self.form.labelForField(field)
    def rebuild(self):
        if hasattr(self,'sound_panel'):self.sound_panel.refresh()
        self.updating=True; self.tree.clear(); items={}
        for node in self.scene['nodes']:
            item=QTreeWidgetItem([node.get('name',node['id'])+' · '+node['kind']]); item.setData(0,Qt.UserRole,node['id']); items[node['id']]=item
        self._tree_items=items
        for node in self.scene['nodes']:
            parent=node.get('parent','')
            if parent:items[parent].addChild(items[node['id']])
            else:self.tree.addTopLevelItem(items[node['id']])
        self.tree.expandAll(); self.updating=False
        chosen=items.get(self.node_id) or next(iter(items.values()),None)
        if chosen:self.select_nodes((self.selected_ids&set(items)) or {chosen.data(0,Qt.UserRole)},chosen.data(0,Qt.UserRole))
        else:self.node_id=''; self.refresh()
    def selected(self,item,*_):
        if self.updating:return
        self.node_id=item.data(0,Qt.UserRole) if item else ''; self.refresh()
    def select_node(self,node_id):
        self.select_nodes([node_id],node_id)
    def seek(self,t):
        self.position=max(self.original.in_point,min(self.original.in_point+self.original.source_duration,t))
        if abs(self.time.value()-self.position)>1e-6:
            blocker=QSignalBlocker(self.time); self.time.setValue(self.position); del blocker
        if self.timer.isActive():self.preview.update(); self.timeline.viewport().update()
        else:self.refresh()
        self.sound_panel.playback.sync(self.scene,self.position,self.timer.isActive(),self.original.speed)
    def pause(self):
        self.timer.stop(); self.play.setText('Play')
        if hasattr(self,'sound_panel'):self.sound_panel.playback.sync(self.scene,self.position,False)
    def toggle(self):
        if self.timer.isActive():self.pause(); self.refresh(); return
        if self.position>=self.time.maximum():self.seek(self.time.minimum())
        self._play_origin=self.position; self._play_started=time.perf_counter(); self.timer.start(); self.play.setText('Pause')
    def tick(self):
        value=self._play_origin+(time.perf_counter()-self._play_started)*self.original.speed
        if value>=self.time.maximum():
            if self.loop.isChecked():value=self.time.minimum()+(value-self.time.minimum())%max(.001,self.original.source_duration)
            else:value=max(self.time.minimum(),self.time.maximum()-self.original.speed/max(1,self.owner.project.settings.fps)); self.pause()
        self.seek(value)
    def navigate(self,kind,direction=1):
        self.pause(); lo,hi=self.time.minimum(),self.time.maximum()
        step=self.original.speed/max(1,self.owner.project.settings.fps)
        if kind=='start':value=lo
        elif kind=='end':value=max(lo,hi-step)
        elif kind=='frame':value=self.position+direction*self.original.speed/max(1,self.owner.project.settings.fps)
        else:
            keys=[k['time'] for k in (self.node() or {}).get('keyframes',{}).get(self.channel.currentText(),[]) if lo<=k['time']<=hi]
            possible=[t for t in keys if (t-self.position)*direction>1e-5]; value=(min(possible) if direction>0 else max(possible)) if possible else (hi if direction>0 else lo)
        self.seek(max(lo,min(hi,value)))
    def begin_edit(self):
        if self._edit_before is None and not self._history_busy:self._edit_before=copy.deepcopy(self.scene)
    def end_edit(self):
        before=self._edit_before; self._edit_before=None
        if before is not None and before!=self.scene:
            self.render_revision+=1
            self.push_history(self._undo,before); self._redo.clear()
        if hasattr(self,'undo_button'):self.undo_button.setEnabled(bool(self._undo)); self.redo_button.setEnabled(bool(self._redo))
    def cancel_edit(self):
        if self._edit_before is not None:self.scene=self._edit_before; self._edit_before=None; self.rebuild()
    def local_history(self,direction):
        inline=getattr(self.preview,'inline_editor',None)
        if inline is not None:inline.finish()
        if self._edit_before is not None:
            self.cancel_edit(); self.preview.drag=None; self.timeline.drag=None; return
        self.pause(); stack=self._undo if direction<0 else self._redo; target=self._redo if direction<0 else self._undo
        if not stack:return
        self.push_history(target,copy.deepcopy(self.scene)); self.scene=stack.pop()[0]; self._edit_before=None; self.rebuild()
        self.undo_button.setEnabled(bool(self._undo)); self.redo_button.setEnabled(bool(self._redo))
    def push_history(self,stack,scene):
        stack.append((scene,len(json.dumps(scene,separators=(',',':'))))); total=sum(size for _,size in stack)
        while len(stack)>1 and (len(stack)>50 or total>16*1024**2):total-=stack.pop(0)[1]
    def choose_image(self):
        if not self.node() or self.node()['kind']!='image':return
        path,_=QFileDialog.getOpenFileName(self,'Choose layer image','','Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.change('source',path); self.refresh()
    def refresh(self):
        self.updating=True; node=self.node() or {}
        self.tree.setHeaderLabel('Composition layers'+(f' · {len(self.selected_ids)} selected' if len(self.selected_ids)>1 else ''))
        self.parent.setEnabled(len(self.selected_ids)<=1); self.layer_name.setEnabled(len(self.selected_ids)<=1)
        self.advanced.setEnabled(len(self.selected_ids)<=1)
        self.scale_link.setChecked(node.get('scale_linked',True))
        self.name.setPlainText(node.get('text','')); self.name.setEnabled(node.get('kind')=='text')
        self.layer_name.setText(node.get('name',node.get('id','')))
        self.image_fit.setCurrentText(node.get('image_fit','stretch'))
        for field in (self.image_fit,self.image_button):
            field.setVisible(node.get('kind')=='image'); label=self.label_for_field(field)
            if label:label.setVisible(node.get('kind')=='image')
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
            field.setVisible(text); label=self.label_for_field(field)
            if label:label.setVisible(text)
        for name,spin in self.spins.items():
            visible=(text if name in ('font_size','tracking','stagger','entry_duration','entry_y','entry_rotation','entry_scale') else kind!='group' if name in ('stroke_width','width','height') else kind in ('path','ellipse','rectangle') if name=='trim' else kind=='path' if name=='morph' else kind=='rectangle' if name=='radius' else True)
            if name in ('number','number_decimals'):visible=text and node.get('text_mode')=='counter'
            if name in ('reveal','caret_period'):visible=text and node.get('text_mode')=='typewriter'
            spin.setVisible(visible); self.label_for_field(spin).setVisible(visible)
        for field in (self.caret,):field.setVisible(text and node.get('text_mode')=='typewriter')
        for field in (self.number_grouping,*[edit for _,edit in self.counter_affixes]):
            field.setVisible(text and node.get('text_mode')=='counter'); label=self.label_for_field(field)
            if label:label.setVisible(field.isVisibleTo(self))
        shape=kind in ('rectangle','ellipse','path'); self.shadow.setVisible(shape); self.shadow.setChecked(node.get('shadow',{}).get('enabled',False))
        self.shadow_color.setVisible(shape and self.shadow.isChecked())
        for name,spin in self.shadow_spins.items():
            spin.setValue(node.get('shadow',{}).get(name,{'opacity':20,'blur':20,'x':0,'y':8}[name])); spin.setVisible(shape and self.shadow.isChecked()); self.label_for_field(spin).setVisible(shape and self.shadow.isChecked())
        key=self.selected_key(); self.mode.setCurrentText((key or {}).get('interpolation','Linear')); self.mode.setEnabled(bool(key))
        self.key_value.setValue(curve(node,self.channel.currentText(),self.position))
        handles=controls((key or {}).get('bezier'))
        for spin,v in zip(self.bezier,handles):spin.setValue(v); spin.setEnabled(bool(key and key.get('interpolation')=='Bezier'))
        self.keys.clear()
        for k in node.get('keyframes',{}).get(self.channel.currentText(),[]):self.keys.addItem(f'{k["time"]:.3f}s · {k["value"]:.3f}',k['time'])
        self.keys.setCurrentIndex(self.keys.findData(self.position))
        self.advanced.setPlainText(json.dumps({k:node[k] for k in ('path','path_to','mask','gradient','source') if k in node},indent=2))
        self.samples.setValue(self.scene['motion_blur']['samples']); self.shutter.setValue(self.scene['motion_blur']['shutter'])
        self.updating=False; self.render_revision+=1; self.graph.update(); self.preview.update()
        if hasattr(self,'timeline'):self.timeline.refresh()
    def change(self,name,value):
        if self.updating or not self.node():return
        self.pause()
        if len(self.selected_nodes())>1 and name not in ('name','parent'):
            selected=self.selected_nodes(); primary=self.node_id; selection=set(self.selected_ids)
            for node in selected:
                self.node_id=node['id']; self.selected_ids={node['id']}; self.change(name,value)
            self.node_id=primary; self.selected_ids=selection
            return
        node=self.node()
        if name in ('scale','scale_y') and node.get('scale_linked',True):
            other='scale_y' if name=='scale' else 'scale'
            old=curve(node,name,self.position); companion=curve(node,other,self.position)
            node['scale_linked']=False
            try:self.change(other,companion*value/old if abs(old)>1e-12 else companion+value-old)
            finally:node['scale_linked']=True
            self.updating=True
            try:self.spins[other].setValue(curve(node,other,self.position))
            finally:self.updating=False
        if name in CHANNELS and self.auto.isChecked():self.put_key(name,value)
        elif name in CHANNELS:
            key=next((k for k in node.get('keyframes',{}).get(name,[]) if abs(k['time']-self.position)<.00001),None)
            if key:key['value']=value
            elif node.get('keyframes',{}).get(name):
                delta=value-curve(node,name,self.position)
                for k in node['keyframes'][name]:k['value']+=delta
            else:node[name]=value
        else:node[name]=value
        if name=='name' and node['id'] in self._tree_items:self._tree_items[node['id']].setText(0,str(value)+' · '+node['kind'])
        self.render_revision+=1; self.preview.update(); self.graph.update()
        if hasattr(self,'timeline'):self.timeline.refresh()
    def text_changed(self):self.change('text',self.name.toPlainText())
    def text_mode_changed(self,value):
        if not self.updating:self.change('text_mode',value); self.refresh()
    def shadow_changed(self,name,value):
        if not self.updating and self.node():
            for node in self.selected_nodes():
                if node['kind'] in ('rectangle','ellipse','path'):node.setdefault('shadow',{})[name]=value
            self.render_revision+=1; self.preview.update()
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
        primary=self.node_id; channel=self.channel.currentText()
        for node in self.selected_nodes():
            self.node_id=node['id']; self.put_key(channel,curve(node,channel,self.position))
        self.node_id=primary; self.refresh()
    def remove_key(self):
        selected={node['id'] for node in self.selected_nodes()}; channel=self.channel.currentText()
        for node in self.selected_nodes():
            keys=node.get('keyframes',{}).get(self.channel.currentText(),[]); keys[:]=[k for k in keys if abs(k['time']-self.position)>.00001]
        if 'sound_cues' in self.scene:
            self.scene['sound_cues']=[c for c in self.scene['sound_cues'] if not(c.get('event')=='keyframe' and c.get('node_id') in selected and c.get('channel')==channel and abs(c.get('key_time',-1)-self.position)<.00001)]
            self.sound_panel.refresh()
        self.refresh()
    def change_mode(self,mode):
        if not self.updating:
            for node in self.selected_nodes():
                for key in node.get('keyframes',{}).get(self.channel.currentText(),[]):
                    if abs(key['time']-self.position)<.00001:key['interpolation']=mode
            self.refresh()
    def graph_changed(self):
        key=self.selected_key()
        if key:
            for node in self.selected_nodes():
                for other in node.get('keyframes',{}).get(self.channel.currentText(),[]):
                    if abs(other['time']-self.position)<.00001:
                        other['interpolation']=key.get('interpolation','Linear')
                        if 'bezier' in key:other['bezier']=list(key['bezier'])
        self.refresh()
    def bezier_changed(self):
        if self.updating or not self.selected_key():return
        values=[s.value() for s in self.bezier]
        try:values=controls(values)
        except ValueError:return
        for node in self.selected_nodes():
            for key in node.get('keyframes',{}).get(self.channel.currentText(),[]):
                if abs(key['time']-self.position)<.00001:key['bezier']=list(values)
        self.graph.update(); self.preview.update()
    def jump_key(self,index):
        if not self.updating and index>=0:self.seek(self.keys.itemData(index))
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
        self.scene['nodes'].append(node); self.node_id=node['id']; self.selected_ids={node['id']}; self.rebuild()
    def branch(self):
        ids={n['id'] for n in self.selected_nodes()}
        while True:
            more={n['id'] for n in self.scene['nodes'] if n.get('parent') in ids}
            if more<=ids:return ids
            ids|=more
    def duplicate(self):
        if not self.node():return
        from .model import uid
        ids=self.branch(); names={i:uid()[:8] for i in ids}; copies=[]
        cues=[copy.deepcopy(c) for c in self.scene.get('sound_cues',[]) if c.get('event','time')!='time' and c.get('node_id') in ids]
        if len(cues)+len(self.scene.get('sound_cues',[]))>32:
            QMessageBox.warning(self,'Sound cue limit','Duplicating this branch would exceed 32 sound cues. Remove a cue first.'); return
        for cue in cues:cue['id']=uid(); cue['node_id']=names[cue['node_id']]
        if cues:self.scene['sound_cues'].extend(cues)
        for node in self.scene['nodes']:
            if node['id'] in ids:
                n=copy.deepcopy(node); n['id']=names[n['id']]; n['parent']=names.get(n.get('parent'),n.get('parent','')); copies.append(n)
        self.scene['nodes'].extend(copies); self.selected_ids={names[i] for i in self.selected_ids if i in names}; self.node_id=names[self.node_id]; self.rebuild()
    def remove(self):
        ids=self.branch(); self.scene['nodes']=[n for n in self.scene['nodes'] if n['id'] not in ids]
        if 'sound_cues' in self.scene:self.scene['sound_cues']=[c for c in self.scene['sound_cues'] if c.get('event','time')=='time' or c.get('node_id') not in ids]
        self.node_id=''; self.selected_ids=set(); self.rebuild()
    def reorder(self,direction):
        roots=set(self.selection_roots()); nodes=self.scene['nodes']; parents={n.get('parent','') for n in nodes if n['id'] in roots}
        for parent in parents:
            siblings=[n['id'] for n in nodes if n.get('parent','')==parent]
            indices=range(1,len(siblings)) if direction<0 else range(len(siblings)-2,-1,-1)
            for i in indices:
                neighbor=i+direction
                if siblings[i] in roots and siblings[neighbor] not in roots:siblings[i],siblings[neighbor]=siblings[neighbor],siblings[i]
            by_id={n['id']:n for n in nodes}; descendants={i:{i} for i in siblings}
            for i in siblings:
                while True:
                    more={n['id'] for n in nodes if n.get('parent') in descendants[i]}
                    if more<=descendants[i]:break
                    descendants[i]|=more
            all_ids=set().union(*descendants.values()) if descendants else set()
            at=next((i for i,n in enumerate(nodes) if n['id'] in all_ids),len(nodes))
            branches=[n for i in siblings for n in nodes if n['id'] in descendants[i]]
            remaining=[n for n in nodes if n['id'] not in all_ids]; nodes=remaining[:at]+branches+remaining[at:]
        self.scene['nodes']=nodes; self.rebuild()
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
                from .motion_audio import rebase
                rebase(self.scene,Path(path).parent)
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
                from .motion_audio import rebase
                rebase(scene,Path(path).parent,True)
                for node in scene['nodes']:
                    if node.get('kind')=='image' and node.get('source'):
                        try:node['source']=os.path.relpath(node['source'],Path(path).parent)
                        except ValueError:pass
                Path(path).write_text(json.dumps(scene,indent=2),encoding='utf-8')
            except (ValueError,OSError) as error:QMessageBox.warning(self,'Could not save template',str(error))
    def accept(self):
        if self.sound_panel.pending is not None:
            self.property_tabs.setCurrentWidget(self.sound_panel); self.sound_panel.status.setText('Wait for sound import to finish before saving the composition.'); return
        current=self.owner.project.item_by_id(self.original.id)
        if current!=self.original or self.owner.current_page!=0 or self.owner.project.track_states.get(self.original.track,{}).get('locked'):
            QMessageBox.warning(self,'Composition changed','The composition changed or its track is locked. Reopen the editor.'); return
        try:scene=validate(self.scene)
        except (ValueError,TypeError,KeyError) as error:QMessageBox.warning(self,'Invalid composition',str(error)); return
        current.graphic_data['scene']=scene; self.owner.model_changed(); super().accept()
    def done(self,result):
        from PySide6.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self); self.timer.stop(); self.sound_panel.close_audio(); super().done(result)

def _local_edit(method):
    def wrapped(self,*args,**kwargs):
        # Qt drops surplus signal arguments for fixed-signature Python slots.
        # Preserve that behavior after adding the transactional wrapper.
        args=args[:method.__code__.co_argcount-1]
        if self.updating:return method(self,*args,**kwargs)
        owned=self._edit_before is None
        if owned:self.begin_edit()
        try:return method(self,*args,**kwargs)
        finally:
            if owned:self.end_edit()
    return wrapped

for _method in ('change','shadow_changed','put_key','add_key','remove_key','change_mode','bezier_changed','parent_changed','add','duplicate','remove','reorder','apply_geometry','blur_changed','load_template'):
    setattr(MotionEditor,_method,_local_edit(getattr(MotionEditor,_method)))
