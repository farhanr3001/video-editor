"""Inspector controls for the lightweight light/colour effects."""
from PySide6.QtWidgets import QWidget,QFormLayout,QPushButton,QColorDialog
from PySide6.QtGui import QColor
from .creative_effects import CONTROLS,COLORS,values,default_effect
from .finishing_effects import CHOICES
from .controls import SafeComboBox

class CreativeControls(QWidget):
    def __init__(self,inspector):
        from .properties import ValueRow
        super().__init__(inspector);self.inspector=inspector;self.rows={}
        self.form=QFormLayout(self);self.form.setContentsMargins(0,0,0,0)
        self.current_name=None
        self.reset=QPushButton('Reset effect');self.reset.clicked.connect(self.reset_effect);self.form.addRow(self.reset);self.hide()

    def build(self,name):
        from .properties import ValueRow
        for row in self.rows.values():self.form.removeRow(row)
        self.rows={};self.current_name=name
        controls=CONTROLS[name]
        for key,label,low,high,default,step in [*controls,('mix','Mix (%)',0,100,100,1)]:
            if (name,key) in CHOICES:
                row=SafeComboBox()
                for text,data in CHOICES[name,key]:row.addItem(text,data)
                row.currentIndexChanged.connect(lambda index,k=key,r=row:self.inspector.edit_effect(k,r.currentData()))
            else:
                row=ValueRow(low,high,default,step)
                row.edited.connect(lambda value,delta,k=key:self.inspector.edit_effect(k,value))
            self.form.insertRow(self.form.rowCount()-1,label,row);self.rows[name,key]=row
        for key,label,default in COLORS.get(name,[]):
            button=QPushButton();button.clicked.connect(lambda _,k=key:self.pick(k))
            self.form.insertRow(self.form.rowCount()-1,label,button);self.rows[name,key]=button

    def refresh(self,effect):
        name=(effect or {}).get('name');self.setVisible(name in CONTROLS)
        if name not in CONTROLS:return
        self.setEnabled(effect.get('enabled',True));settings=values(effect)
        previous=self.inspector.updating;self.inspector.updating=True
        try:
            if self.current_name!=name:self.build(name)
            for (candidate,key),row in self.rows.items():
                self.form.setRowVisible(row,candidate==name)
                if candidate!=name:continue
                if isinstance(row,QPushButton):
                    color=settings[key];row.setText(color.upper());row.setStyleSheet(f'background:{color};color:{"#111" if QColor(color).lightnessF()>.5 else "#fff"}')
                elif isinstance(row,SafeComboBox):row.setCurrentIndex(row.findData(int(settings[key])))
                else:row.set_values([settings[key]])
        finally:self.inspector.updating=previous

    def pick(self,key):
        owner=self.inspector;effect=owner.effect()
        if not effect or effect.get('name') not in CONTROLS:return
        color=QColorDialog.getColor(QColor(values(effect)[key]),self,'Choose effect colour')
        if color.isValid():owner.edit_effect(key,color.name());owner.refresh_effect()

    def reset_effect(self):
        owner=self.inspector;effect=owner.effect()
        if getattr(owner.window,'current_page',0)!=0 or not effect or effect.get('name') not in CONTROLS:return
        targets=owner.effect_targets()
        if not targets:return
        owner.window.flush_text_edit()
        for item,entry in targets:
            defaults=default_effect(entry['name']);defaults.pop('clock_origin');entry.update(defaults)
        owner.window.model_changed();owner.refresh_effect()
