"""Native package check for intentional Phone feature removal."""
def run(folder):
 import os,json,sys
 from pathlib import Path
 out=Path(folder).resolve();out.mkdir(parents=True,exist_ok=True)
 os.environ['KINETIC_CUT_HOME']=str(out/'home')
 from PySide6.QtWidgets import QApplication
 from .ui import MainWindow
 from .workspace import set_page
 from .feature_packs import ROOTS
 app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
 w=MainWindow();w.resize(1250,800);w.show();app.processEvents()
 assert [b.text() for b in w.page_group.buttons()]==['Edit','Deliver']
 assert not hasattr(w,'phone_connect') and set(ROOTS)=={'vision','vocals'}
 set_page(w,2);assert w.current_page==0
 set_page(w,1);assert w.current_page==1
 set_page(w,0);assert w.current_page==0
 assert w.grab().save(str(out/'editor.png'))
 w.close();app.processEvents()
 (out/'report.json').write_text(json.dumps(dict(passed=True,frozen=bool(getattr(sys,'frozen',False)),pages=['Edit','Deliver'],phone_runtime_absent=True)),encoding='utf-8')
 return 0
