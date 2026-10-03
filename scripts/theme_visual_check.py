"""Native-window theme QA in an isolated profile; never opens user projects/devices."""
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('output')
args = parser.parse_args()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
os.environ['KINETIC_CUT_HOME'] = str(output / 'unit-test-home')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.theme_dialog import UIThemesDialog
from kinetic_cut.workspace import set_page

app = QApplication([])
app.setStyle('Fusion')
window = MainWindow()
window.autosave_timer.stop()
window.phone_connect.loaded = True  # No real device discovery, pairing or transfer.
window.resize(1500, 900)
window.show()
steps = []
dialogs = []
def setup(theme, page):
    window.apply_theme(theme, save=False)
    window.settings['ui_theme'] = theme
    set_page(window, page)
    window.effects_toggle.setChecked(True)
def capture(name):
    window.grab().save(str(output / (name + '.png')))
def dialog(theme):
    d = UIThemesDialog(window)
    dialogs.append(d)
    d.show()
    QTimer.singleShot(200, lambda: (d.grab().save(str(output / (theme + '-chooser.png'))), d.close()))
for theme in ('default', 'ableton_gray', 'final_cut_obsidian'):
    for page, label in ((0, 'edit'), (1, 'deliver'), (2, 'phone')):
        steps += [lambda t=theme, p=page: setup(t, p), lambda t=theme, l=label: capture(t + '-' + l)]
    steps.append(lambda t=theme: dialog(t))
def advance():
    if steps:
        steps.pop(0)()
        QTimer.singleShot(350, advance)
    else:
        window.close()
        app.quit()
QTimer.singleShot(500, advance)
sys.exit(app.exec())
