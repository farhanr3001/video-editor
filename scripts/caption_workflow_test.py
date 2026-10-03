"""End-to-end caption setup, progress, Inspector and visible preview acceptance."""
import os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"caption-workflow-home")); os.environ["QT_QPA_PLATFORM"]="windows"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog,QProgressDialog,QSpinBox,QCheckBox,QColorDialog
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.media import probe
from kinetic_cut.model import Project,Caption,uid
import kinetic_cut.ui as ui_module
from kinetic_cut.theme import STYLESHEET

def main():
    app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET); w=MainWindow(); w.resize(1400,900); w.show()
    media=probe(ROOT/"xqc_royalty.mp4"); w.set_project(Project(media=[media])); w.add_media_to_track(media.id,"video_1",0); w.settings["whisper_model"]="tiny.en"
    def controlled_transcribe(path,settings,offset,progress):
        progress((65,"Transcribing… 1.0s / 2.0s")); time.sleep(.2); progress((90,"Transcribing… 2.0s / 2.0s")); return [Caption(uid(),offset,offset+2,"Visible styled caption")],"test backend"
    ui_module.transcribe=controlled_transcribe
    def accept_setup():
        dialog=app.activeModalWidget()
        assert isinstance(dialog,QDialog) and dialog.windowTitle()=="Auto Caption Style",dialog
        size=next(box for box in dialog.findChildren(QSpinBox) if box.maximum()==200); size.setValue(46)
        checks=dialog.findChildren(QCheckBox); next(c for c in checks if c.text()=="Background card").setChecked(True); dialog.accept()
    QTimer.singleShot(150,accept_setup); w.generate_captions()
    progress=next((d for d in w.findChildren(QProgressDialog) if d.isVisible()),None); assert progress and progress.maximum()==100 and progress.value()>=5
    deadline=time.monotonic()+15
    while not w.project.captions and time.monotonic()<deadline:QTest.qWait(100)
    assert w.project.captions,"Caption worker did not complete"; assert not progress.isVisible()
    first=w.project.captions[0]; assert w.project.subtitle_style.size==46 and w.project.subtitle_style.background_enabled
    assert w.timeline.selected_caption==first.id and w.inspector.current_caption()==first and w.inspector.video_stack.currentIndex()==1
    original_picker=QColorDialog.getColor; QColorDialog.getColor=staticmethod(lambda *args,**kwargs:QColor("#ff315c"))
    try:
        attr,color_button=w.inspector.style_colors[0]; assert attr=="color" and color_button.isEnabled(); w.inspector.pick_color(attr)
    finally:QColorDialog.getColor=original_picker
    assert w.project.subtitle_style.color=="#ff315c"
    w.inspector.edit_style("alignment","Right"); w.inspector.edit_style("position_x",.75); w.inspector.edit_style("shadow_blur",8); w.inspector.edit_style("background_radius",.04)
    assert (w.project.subtitle_style.alignment,w.project.subtitle_style.position_x,w.project.subtitle_style.shadow_blur,w.project.subtitle_style.background_radius)==("Right",.75,8,.04)
    assert "subtitle_1" in w.timeline.tracks(); w.seek(first.start+.03); QTest.qWait(200); with_caption=w.preview.grab().toImage()
    saved=w.project.captions; w.project.captions=[]; w.preview.update(); without_caption=w.preview.grab().toImage(); w.project.captions=saved
    assert with_caption!=without_caption,"Caption must paint in the viewer"
    w.grab().save(str(ROOT/"build"/"caption-workflow.png")); w.close(); w.thread_pool.waitForDone(10000)
    print(f"PASS caption setup/progress/selection/Inspector/subtitle track/visible preview: {len(saved)} captions",flush=True)
if __name__=="__main__":main()
