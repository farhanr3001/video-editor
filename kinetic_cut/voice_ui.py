"""Compact native controls for the currently inspected voice effect."""
from PySide6.QtWidgets import QWidget, QFormLayout, QPushButton
from .voice_effects import CONTROLS, values, default_effect


class VoiceControls(QWidget):
    def __init__(self, inspector):
        from .properties import ValueRow
        super().__init__(inspector)
        self.inspector=inspector; self.rows={}; self.labels={}
        self.form=QFormLayout(self); self.form.setContentsMargins(0,0,0,0)
        for name,controls in CONTROLS.items():
            for key,label,low,high,default,step in controls:
                row=ValueRow(low,high,default,step)
                row.edited.connect(lambda value,delta,k=key:inspector.edit_effect(k,value))
                self.form.addRow(label,row); self.rows[name,key]=row
                self.labels[name,key]=self.form.labelForField(row)
        self.reset=QPushButton('Reset voice effect'); self.reset.clicked.connect(self.reset_effect)
        self.form.addRow(self.reset); self.hide()

    def refresh(self,effect):
        controls=CONTROLS.get((effect or {}).get('name'))
        self.setVisible(bool(controls))
        if not controls:return
        self.setEnabled(effect.get('enabled',True))
        settings=values(effect); previous=self.inspector.updating; self.inspector.updating=True
        try:
            name=effect['name']
            for (candidate,key),row in self.rows.items():self.form.setRowVisible(row,candidate==name)
            for key,label,low,high,default,step in controls:
                self.rows[name,key].set_values([settings[key]])
        finally:self.inspector.updating=previous

    def reset_effect(self):
        owner=self.inspector; primary=owner.effect()
        if getattr(owner.window,'current_page',0)!=0:return
        if not primary or primary.get('name') not in CONTROLS:return
        targets=owner.effect_targets()
        if not targets:return
        owner.window.flush_text_edit()
        for item,effect in targets:
            defaults=default_effect(effect['name'])
            for key in ('amount',*(field[0] for field in CONTROLS[effect['name']])):effect[key]=defaults[key]
        owner.window.model_changed(); owner.refresh_effect()
