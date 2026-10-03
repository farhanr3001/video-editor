"""Small caption-first font menu; saved legacy families remain selectable."""
from PySide6.QtCore import Qt,QPoint,Signal
from PySide6.QtGui import QFont,QFontDatabase
from .controls import SafeComboBox
from .icons import resource_path

CURATED=['Nirmala UI','Geometos','TikTok Sans','Montserrat','Poppins','Anton','Archivo Black','Bebas Neue','Bangers','Arial','Arial Black','Impact','Verdana','Trebuchet MS','Georgia']
_loaded=False

def load_fonts():
    global _loaded
    if _loaded:return
    for path in resource_path('assets','fonts').glob('*.ttf'):QFontDatabase.addApplicationFont(str(path))
    _loaded=True

def families():
    load_fonts(); installed=set(QFontDatabase.families())
    return CURATED+[name for name in sorted(installed) if name.startswith('Geometos Soft')]

class CaptionFontCombo(SafeComboBox):
    currentFontChanged=Signal(QFont)
    previewFontChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.addItems(families()); self.setEditable(False); self.setMaxVisibleItems(8)
        for i in range(self.count()):self.setItemData(i,QFont(self.itemText(i),11),Qt.FontRole)
        self.currentTextChanged.connect(lambda name:self.currentFontChanged.emit(QFont(name)))
        self.textHighlighted.connect(self.previewFontChanged)
    def setCurrentText(self,name):
        if self.findText(name)<0:self.addItem(name)
        super().setCurrentText(name)
    def currentFont(self):return QFont(self.currentText())
    def setCurrentFont(self,font):self.setCurrentText(font.family())
    def showPopup(self):
        super().showPopup()
        popup=self.view().window(); bottom=self.mapToGlobal(QPoint(0,self.height()))
        screen=self.screen().availableGeometry(); available=screen.bottom()-bottom.y()-4
        # Prefer a compact scrolling menu below, not an enormous menu with
        # the selected family centered over the entire Inspector.
        if available>=65:
            height=min(250,available); popup.resize(max(self.width(),230),height)
            popup.move(min(bottom.x(),screen.right()-popup.width()+1),bottom.y())
        self.view().scrollTo(self.model().index(self.currentIndex(),0))
    def hidePopup(self):
        super().hidePopup(); self.previewFontChanged.emit('')
