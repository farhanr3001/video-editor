"""Marker editing within the transactional tracking draft."""
import copy
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout, QLineEdit, QColorDialog, QCheckBox, QFileDialog
from PySide6.QtGui import QColor, QPixmap, QIcon, QPainter, QPen
from PySide6.QtCore import Qt, QSize, QRectF
from .controls import SafeComboBox, SafeDoubleSpinBox
from .tracking_effect import default_effect, MODES
from .tracking_design import TrackingCheckBox, ColourSwatchButton


class MarkerEditor(QWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        from .tracking_design import TrackingCard,TrackingComboBox
        from PySide6.QtWidgets import QLabel,QMenu,QSizePolicy
        self.setMinimumWidth(270);self.setProperty('trackingBody',True)
        self.dialog=dialog;self.loading=False
        self.markers=copy.deepcopy(dialog.effect.get('markers') or [
            {k:v for k,v in dialog.effect.items() if k not in ('analysis','anchors','markers')}])
        layout=QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);layout.setSpacing(8)
        marker_card=TrackingCard('Markers','layers',self);layout.addWidget(marker_card)
        self.single_label=QLabel(marker_card.body)
        self.single_label.setProperty('trackingHeading',True);marker_card.content.addWidget(self.single_label)
        self.picker=TrackingComboBox(marker_card.body);self.picker.setAccessibleName('Selected marker')
        self.picker.currentIndexChanged.connect(self.refresh);marker_card.content.addWidget(self.picker)
        self.scope=QLabel(marker_card.body);self.scope.setWordWrap(True);marker_card.content.addWidget(self.scope)
        self.scope.setToolTip('Selected frames create appearance keys held until the next key. No selection edits the base style. Choose image is shared by this marker.')
        types=QFormLayout();types.addRow('Marker type',dialog.mode);marker_card.content.addLayout(types)
        self.kind=TrackingComboBox(dialog._hidden_controls)
        self.kind.addItems([mode for mode in MODES if mode!='Follow Crop']);self.kind.hide()
        actions=QHBoxLayout()
        self.add_button=QPushButton('Add marker',marker_card.body)
        from .icons import lucide_icon
        self.add_button.setIcon(lucide_icon('plus'))
        menu=QMenu(self.add_button)
        for mode in MODES:
            if mode=='Follow Crop':continue
            entry=menu.addAction(mode);entry.triggered.connect(lambda _,m=mode:self.add_kind(m))
        self.add_button.setMenu(menu)
        self.remove_button=QPushButton('Remove',marker_card.body);self.remove_button.setIcon(lucide_icon('trash-2'))
        self.remove_button.clicked.connect(self.remove)
        actions.addWidget(self.add_button,1);actions.addWidget(self.remove_button,1);marker_card.content.addLayout(actions)
        self.settings_card=TrackingCard('Marker settings','sliders-horizontal',self,True);layout.addWidget(self.settings_card)
        self.form=QFormLayout();self.form.setVerticalSpacing(7);self.form.setHorizontalSpacing(10)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.settings_card.content.addLayout(self.form)
        self.fields = {}
        for key, title, low, high in [('offset_x','Horizontal offset',-32768,32768), ('offset_y','Vertical offset',-32768,32768),
                ('width','Width (%)',1,1000), ('height','Height (%)',1,1000), ('rotation','Rotation',-3600,3600),
                ('opacity','Opacity (%)',0,100), ('stroke_width','Stroke',0,1024), ('font_size','Text size',4,1024),
                ('arrow_length','Arrow length',1,8192), ('arrow_head','Arrow head',1,2048), ('padding','Padding',0,4096),
                ('blur','Blur',1,500), ('pixel_size','Pixel size',2,512)]:
            control = SafeDoubleSpinBox(self)
            control.setRange(low,high)
            control.setMinimumWidth(65)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            control.valueChanged.connect(lambda value,k=key:self.change(k,value))
            self.form.addRow(title,control)
            self.fields[key] = control
        for key, title in [('label','Text'), ('font','Font')]:
            field = QLineEdit(self)
            field.setMaxLength(512 if key=='label' else 128)
            field.textEdited.connect(lambda value,k=key:self.change(k,value))
            self.form.addRow(title,field)
            self.fields[key] = field
        self.colours={}
        for key, title in [('color','Marker colour'),('label_color','Text colour'),('label_background','Text background')]:
            button = ColourSwatchButton(title)
            button.clicked.connect(lambda _,k=key:self.colour(k))
            self.form.addRow(button)
            self.colours[key]=button
        self.options_card=TrackingCard('Options','sliders-horizontal',self,True);layout.addWidget(self.options_card)
        self.option_form=QFormLayout();self.options_card.content.addLayout(self.option_form)
        self.fill = TrackingCheckBox('Filled shape',self.options_card.body)
        self.fill.toggled.connect(lambda value:self.change('fill',value))
        self.option_form.addRow(self.fill)
        self.follow = TrackingCheckBox('Follow object size',self)
        self.follow.toggled.connect(lambda value:self.change('follow_scale',value))
        self.option_form.addRow(self.follow)
        image = QPushButton('Choose image…',self)
        image.clicked.connect(self.choose_image)
        image.setToolTip('Image asset shared across this marker’s style keys')
        self.form.addRow(image)
        self.image_button=image
        layout.addStretch(1)
        self.dialog.marker_settings_card=self.settings_card;self.dialog.marker_options_card=self.options_card
        self.rebuild()

    def add_kind(self,mode):
        self.kind.setCurrentText(mode);self.add()

    def current(self):
        return self.markers[max(0,self.picker.currentIndex())]

    def displayed(self):
        from .tracking_appearance import evaluate
        return evaluate(self.current(),self.dialog.source_time())

    def write(self,values):
        from .tracking_appearance import edit
        times=self.dialog.selected_frame_times()
        temporal={k:v for k,v in values.items() if k!='image'}
        if times:edit(self.current(),times,temporal)
        else:self.current().update(temporal)
        if 'image' in values:self.current()['image']=values['image']
        self.dialog.effect['markers']=self.markers

    def rebuild(self):
        self.loading = True
        index = self.picker.currentIndex()
        self.picker.clear()
        self.picker.addItems([f'{n+1} · {m["mode"]}' for n,m in enumerate(self.markers)])
        self.picker.setCurrentIndex(max(0,min(index,len(self.markers)-1)))
        self.loading = False
        self.single_label.setText(self.picker.currentText())
        self.single_label.setVisible(len(self.markers)==1);self.picker.setVisible(len(self.markers)>1)
        self.refresh()

    def refresh(self,*_):
        if self.loading:return
        self.loading = True
        marker = self.displayed()
        count=len(self.dialog.selected_frame_times())
        self.scope.setText(f'{count} frame'+('s' if count!=1 else '')+' selected · edits create style keys' if count else 'Base style · select frames to change over time')
        defaults = default_effect(marker['mode'])
        self.dialog.mode.blockSignals(True)
        self.dialog.mode.setCurrentText(marker['mode'])
        self.dialog.mode.blockSignals(False)
        for key,field in self.fields.items():
            value = marker.get(key,defaults[key])
            if isinstance(field,QLineEdit):field.setText(value)
            else:field.setValue(value)
        self.fill.setChecked(marker.get('fill',False))
        self.follow.setChecked(marker.get('follow_scale',True))
        specific = {'font','label','font_size','stroke_width','arrow_length','arrow_head','blur','pixel_size'}
        visible = {'Label':{'font','label','font_size'}, 'Arrow':{'stroke_width','arrow_length','arrow_head'},
                   'Circle':{'stroke_width'}, 'Rectangle':{'stroke_width'}, 'Blur':{'blur'}, 'Pixelate':{'pixel_size'}}.get(marker['mode'],set())
        for key in specific:self.form.setRowVisible(self.fields[key],key in visible)
        self.option_form.setRowVisible(self.fill,marker['mode'] in ('Circle','Rectangle'))
        self.add_button.setEnabled(len(self.markers)<16)
        self.remove_button.setEnabled(len(self.markers)>1)
        self.form.setRowVisible(self.image_button,marker['mode']=='Image')
        for key,button in self.colours.items():self.form.setRowVisible(button,key=='color' or marker['mode']=='Label')
        self.loading = False
        self.single_label.setText(f'{max(0,self.picker.currentIndex())+1} · {marker["mode"]}')
        self.refresh_swatches()

    def change(self,key,value):
        if self.loading:return
        self.write({key:value})
        if key in self.colours:self.refresh_swatches()
        self.dialog.effect['markers'] = self.markers
        self.dialog.refresh_preview()

    def apply_geometry(self,values):
        import math
        changes={}
        for key,value in values.items():
            if not isinstance(value,(int,float)) or not math.isfinite(value):continue
            if key in self.fields:
                field=self.fields[key];changes[key]=max(field.minimum(),min(field.maximum(),value))
            elif key=='label_padding':changes[key]=max(0,min(1024,value))
        self.write(changes)
        self.dialog.effect['markers']=self.markers
        self.refresh()
        self.dialog.refresh_preview()

    def refresh_swatches(self):
        marker=self.displayed()
        defaults=default_effect(marker['mode'])
        for key,button in self.colours.items():
            colour=QColor(marker.get(key,defaults[key]))
            pixmap=QPixmap(60,32);pixmap.fill(Qt.transparent)
            painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor('#777777'),1));painter.setBrush(colour)
            painter.drawRoundedRect(QRectF(1,1,58,30),5,5);painter.end()
            pixmap.setDevicePixelRatio(2)
            button.setIcon(QIcon(pixmap));button.setIconSize(QSize(30,16))
            button.setToolTip(colour.name(QColor.HexArgb))
            button.set_swatch(colour)

    def add(self):
        if len(self.markers)>=16:return
        marker = default_effect(self.kind.currentText())
        marker.pop('analysis',None)
        marker['color'] = '#46e0ad'
        self.markers.append(marker)
        self.dialog.effect['markers'] = self.markers
        self.rebuild()
        self.picker.setCurrentIndex(len(self.markers)-1)
        self.dialog.refresh_preview()

    def remove(self):
        if len(self.markers)<=1:return
        self.markers.pop(self.picker.currentIndex())
        self.dialog.effect['markers'] = self.markers
        self.rebuild()
        self.dialog.refresh_preview()

    def colour(self,key):
        colour = QColorDialog.getColor(QColor(self.displayed().get(key,'#ffffff')),self)
        if colour.isValid():self.change(key,colour.name())

    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose tracked image','','Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.change('image',path)
