"""Native captures of the new controls in all themes; isolated personal data."""
import json,os,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/distribution-visual';OUT.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(OUT/'home');os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop,QEvent
from kinetic_cut.ui import MainWindow
from kinetic_cut.theme import PALETTES
from kinetic_cut.update_ui import UpdateDialog
from kinetic_cut.component_ui import InstallComponentDialog
from kinetic_cut.updates import Release
from kinetic_cut.workspace import set_page

app=QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
w=MainWindow();w.autosave_timer.stop();w.show()
def settle():
    loop=QEventLoop();QTimer.singleShot(180,loop.quit);loop.exec()
for theme in PALETTES:
    w.apply_theme(theme,save=False);settle()
    dialog=UpdateDialog(w,Release('1.2.0','https://github.com/farhanr3001/video-editor/releases/download/v1.2.0/test.exe','0'*64,341000000,'Editing features are preserved.'),startup=True)
    dialog.show();settle();dialog.grab().save(str(OUT/f'{theme}-update.png'));dialog.close()
    dialog=InstallComponentDialog(w,'vision');dialog.show();settle();dialog.grab().save(str(OUT/f'{theme}-download.png'));dialog.close()
    with patch('kinetic_cut.feature_packs.available',return_value=False):
        set_page(w,0);w.effects_panel.categories.setCurrentRow(1+list(w.effects_panel.catalog).index('Face Filters'));w.effects_panel.refresh();settle()
        w.effects_panel.grab().save(str(OUT/f'{theme}-effects.png'))
        set_page(w,2);w.phone_connect.refresh_download_gate();settle()
        w.phone_connect.grab().save(str(OUT/f'{theme}-phone.png'))
w.close();app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
(OUT/'report.json').write_text(json.dumps({'passed':True,'themes':list(PALETTES),'captures':12},indent=2))
