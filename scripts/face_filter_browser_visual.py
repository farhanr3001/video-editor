"""Capture the grouped Face Filters browser under every supported theme."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from PySide6.QtWidgets import QApplication
from kinetic_cut.theme_widgets import apply_application_theme
from kinetic_cut.ui import MainWindow


def main():
    app=QApplication([])
    window=MainWindow()
    window.autosave_timer.stop()
    browser=window.effects_panel
    choices=[browser.categories.item(i).text() for i in range(browser.categories.count())]
    browser.categories.setCurrentRow(choices.index('Face Filters'))
    browser.setParent(None)
    browser.resize(430,620)
    browser.show()
    destination=ROOT/'build/face-filter-browser-visual'
    destination.mkdir(parents=True,exist_ok=True)
    for theme in ('default','obsidian','ableton_gray'):
        apply_application_theme(theme)
        app.processEvents()
        if not browser.grab().save(str(destination/(theme+'.png'))):
            raise RuntimeError('Could not capture '+theme)
    window.close()


if __name__=='__main__':
    main()
