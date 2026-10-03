"""Small, non-modal conveniences with no project/history side effects."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLineEdit, QLabel, QMenu


class PanelSearch(QLineEdit):
    dismissed = Signal()

    def __init__(self, *args):
        super().__init__(*args)
        self.setClearButtonEnabled(True)
        self.setToolTip("Search · Escape clears and closes")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear()
            self.hide()
            self.dismissed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def toggle(self):
        if self.isHidden():
            self.show()
            self.setFocus()
        else:
            self.clear()
            self.hide()
            self.dismissed.emit()


class CopyTimecodeLabel(QLabel):
    def __init__(self, text, seconds, parent=None):
        super().__init__(text, parent)
        self.seconds = seconds
        self.setToolTip("Right-click to copy timecode or seconds")

    def copy_menu(self):
        # Freeze both representations at menu-open, even during playback.
        menu = QMenu(self)
        for title, value in (("Copy timecode", self.text()),
                             ("Copy seconds", f"{self.seconds():.3f}")):
            menu.addAction(title, lambda value=value: QGuiApplication.clipboard().setText(value))
        return menu

    def contextMenuEvent(self, event):
        menu = self.copy_menu()
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(event.globalPos())
