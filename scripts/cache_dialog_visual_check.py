"""Capture the cache dialog in each supported theme for visual QA."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.cache_manager import CacheManagerDialog


def main():
    output=Path(sys.argv[1]); output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    window=MainWindow(); window.autosave_timer.stop()
    for theme in ('default','obsidian','ableton_gray'):
        window.apply_theme(theme,save=False)
        dialog=CacheManagerDialog(window)
        dialog.show(); app.processEvents()
        if not dialog.grab().save(str(output/(theme+'.png'))):
            raise RuntimeError('Could not capture '+theme)
        dialog.close()
    window.close(); app.processEvents()


if __name__=='__main__':
    main()
