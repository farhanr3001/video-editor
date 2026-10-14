"""Discoverable preset controls shared by the graphic inspector."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget,QFormLayout,QVBoxLayout,QLabel,QLineEdit,QPushButton,QColorDialog,QFileDialog
from PySide6.QtGui import QColor
from .controls import SafeDoubleSpinBox,SafeComboBox
from .motion_presets import fields

class PresetControls(QWidget):
    def __init__(self,apply,parent=None):
        super().__init__(parent); self.apply=apply; self.preset=''; self.controls={}; self.busy=False
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        self.heading=QLabel(self); self.heading.setWordWrap(True); root.addWidget(self.heading)
        self.body=QWidget(self); self.form=QFormLayout(self.body); self.form.setContentsMargins(0,0,0,0); root.addWidget(self.body)
        self.error=QLabel(self); self.error.setWordWrap(True); root.addWidget(self.error)
    def refresh(self,data):
        name=data.get('preset',''); self.busy=True
        if name!=self.preset:
            while self.form.rowCount():self.form.removeRow(0)
            self.controls={}; self.preset=name
            if name:
                for key,field in fields(name).items():
                    kind=field['type']
                    if kind=='number':
                        control=SafeDoubleSpinBox(self.body); control.setRange(field['min'],field['max']); control.setDecimals(3 if key in ('entry','exit','roll_duration') else 0); control.valueChanged.connect(lambda v,k=key:self.edited(k,v))
                    elif kind=='choice':
                        control=SafeComboBox(self.body); control.addItems(field['choices']); control.currentTextChanged.connect(lambda v,k=key:self.edited(k,v))
                    elif kind in ('color','image'):
                        control=QPushButton(self.body); control.clicked.connect(lambda _,k=key,t=kind:self.choose(k,t))
                    else:
                        control=QLineEdit(self.body); control.setMaxLength(256); control.editingFinished.connect(lambda k=key,c=control:self.edited(k,c.text()))
                    control.setObjectName('preset_'+key); self.controls[key]=control; self.form.addRow(field['label'],control)
        if name:
            self.heading.setText(name+' · Editable preset'); values=data['parameters']
            for key,control in self.controls.items():
                blocker=QSignalBlocker(control); value=values[key]
                if isinstance(control,SafeDoubleSpinBox):control.setValue(value)
                elif isinstance(control,SafeComboBox):control.setCurrentText(value)
                elif isinstance(control,QLineEdit):control.setText(value)
                else:control.setText(value if key!='image' else ('Choose image…' if not value else 'Replace image…')); control.setToolTip(value)
                del blocker
        self.busy=False; self.setVisible(bool(name))
    def edited(self,key,value):
        if self.busy:return
        try:self.apply({key:value}); self.error.clear()
        except (ValueError,TypeError,KeyError) as error:self.error.setText(str(error))
    def choose(self,key,kind):
        if kind=='image':
            path,_=QFileDialog.getOpenFileName(self,'Choose product image','','Images (*.png *.jpg *.jpeg *.webp *.bmp)')
            if path:self.edited(key,path)
        else:
            color=QColorDialog.getColor(QColor(self.controls[key].text()),self,'Graphic colour')
            if color.isValid():self.edited(key,color.name())
