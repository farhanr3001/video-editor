"""Project canvas/timebase settings, distinct from application preferences."""
import copy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QWidget,
    QHBoxLayout,QDialogButtonBox,QCheckBox,QMessageBox)
from .controls import SafeComboBox,SafeSpinBox,SafeDoubleSpinBox


class ProjectSettingsDialog(QDialog):
    FORMATS=[("Vertical · 9:16 · 1080 × 1920",(1080,1920)),
             ("Landscape · 16:9 · 1920 × 1080",(1920,1080)),
             ("Square · 1:1 · 1080 × 1080",(1080,1080)),
             ("Portrait · 4:5 · 1080 × 1350",(1080,1350)),
             ("Vertical HD · 9:16 · 720 × 1280",(720,1280)),
             ("Custom",None)]

    def __init__(self,project,parent=None,*,new_project=False):
        super().__init__(parent); self.original=copy.deepcopy(project.settings); self.new_project=new_project
        self.setWindowTitle("Project Settings"); self.setMinimumWidth(490)
        root=QVBoxLayout(self); form=QFormLayout(); root.addLayout(form)
        self.name=QLineEdit(project.name); form.addRow("Project name",self.name)
        self.format=SafeComboBox()
        for label,size in self.FORMATS:self.format.addItem(label,size)
        form.addRow("Canvas format",self.format)
        self.width=SafeSpinBox(); self.height=SafeSpinBox()
        for spin in [self.width,self.height]:spin.setRange(64,8192); spin.setSingleStep(2); spin.setSuffix(" px")
        self.width.setValue(project.settings.width); self.height.setValue(project.settings.height)
        host=QWidget(); dimensions=QHBoxLayout(host); dimensions.setContentsMargins(0,0,0,0)
        dimensions.addWidget(self.width); dimensions.addWidget(QLabel("×")); dimensions.addWidget(self.height); form.addRow("Width × height",host)
        selected=next((i for i,(_,size) in enumerate(self.FORMATS) if size==(project.settings.width,project.settings.height)),len(self.FORMATS)-1)
        self.format.setCurrentIndex(selected); self.format.currentIndexChanged.connect(self.format_changed)
        self.width.valueChanged.connect(self.custom_dimensions); self.height.valueChanged.connect(self.custom_dimensions)
        self.fps=SafeComboBox(); self.fps.addItems([str(v) for v in sorted({24,25,30,50,60,120,project.settings.fps})]); self.fps.setCurrentText(str(project.settings.fps)); form.addRow("Timeline frame rate",self.fps)
        if not new_project:
            self.normalize=QCheckBox("Normalize export audio to −14 LUFS"); self.normalize.setChecked(project.settings.normalize_audio); form.addRow("Audio",self.normalize)
            self.noise=QCheckBox("Global noise reduction on export"); self.noise.setChecked(project.settings.noise_reduction); form.addRow("",self.noise)
            self.duck=QCheckBox("Duck music-role tracks during source speech"); self.duck.setChecked(project.settings.auto_duck); form.addRow("",self.duck)
            self.duck_amount=SafeDoubleSpinBox(); self.duck_amount.setRange(-36,0); self.duck_amount.setDecimals(1); self.duck_amount.setSuffix(" dB"); self.duck_amount.setValue(project.settings.duck_amount_db); form.addRow("Preview duck level",self.duck_amount)
        note=QLabel("Defaults: 1080 × 1920, 60 fps." if new_project else "Defaults: 1080 × 1920, 60 fps. Changing the canvas keeps clip timing and Transform values; review framing and caption placement afterwards. Queued exports keep their original settings.")
        note.setWordWrap(True); note.setObjectName("emptyState"); root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def format_changed(self):
        size=self.format.currentData()
        if size:
            for spin,value in zip((self.width,self.height),size):spin.blockSignals(True); spin.setValue(value); spin.blockSignals(False)

    def custom_dimensions(self):
        size=(self.width.value(),self.height.value())
        index=next((i for i,(_,candidate) in enumerate(self.FORMATS) if candidate==size),len(self.FORMATS)-1)
        self.format.blockSignals(True); self.format.setCurrentIndex(index); self.format.blockSignals(False)

    def values(self):
        settings=copy.deepcopy(self.original); settings.width=self.width.value(); settings.height=self.height.value(); settings.fps=int(self.fps.currentText())
        if self.new_project:
            settings.normalize_audio=False; settings.noise_reduction=False; settings.auto_duck=False
        else:
            settings.normalize_audio=self.normalize.isChecked(); settings.noise_reduction=self.noise.isChecked(); settings.auto_duck=self.duck.isChecked(); settings.duck_amount_db=self.duck_amount.value()
        return self.name.text().strip() or "Untitled Short",settings

    def accept(self):
        if self.width.value()%2 or self.height.value()%2:
            QMessageBox.warning(self,"Canvas dimensions","Use even pixel dimensions for H.264/H.265 export."); return
        super().accept()
