"""Capture the Custom Face editor against a short local sample for UI QA."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from kinetic_cut.custom_face_dialog import CustomFaceDialog
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.media import probe
from kinetic_cut.ui import MainWindow
from kinetic_cut.vision_effects import fingerprint
from kinetic_cut.theme_widgets import apply_application_theme


def main():
    source=Path(os.environ.get('KINETIC_FACE_SOURCE',ROOT/'build/face-filter-check/input.mp4'))
    analysis_root=Path(os.environ.get('KINETIC_FACE_ANALYSIS',ROOT/'build/custom-face-check/analysis'))
    output=Path(os.environ.get('KINETIC_FACE_VISUAL_OUTPUT',ROOT/'build/custom-face-check/dialog.png'))
    info=json.loads((analysis_root/'info.json').read_text())
    app=QApplication([])
    window=MainWindow()
    window.autosave_timer.stop()
    media=probe(source) if os.environ.get('KINETIC_FACE_SOURCE') else MediaItem('sample',str(source),'video',source.name,2,640,360)
    duration=info['source_end']-info['source_start']
    item=TimelineItem('selected',media.id,'video_1',0,duration,in_point=info['source_start'])
    item.transform.x=float(os.environ.get('KINETIC_FACE_X',item.transform.x))
    item.transform.y=float(os.environ.get('KINETIC_FACE_Y',item.transform.y))
    window.set_project(Project(media=[media],timeline=[item]))
    window.project.settings.fps=round(info['fps'])
    info.update(root=str(analysis_root),source=fingerprint(media),crop=vars(item.crop.clamped()))
    dialog=CustomFaceDialog(window,media,item,info)
    dialog.rows['nose_size'][0].setValue(65)
    dialog.rows['left_eye'][0].setValue(55)
    dialog.rows['right_eye'][0].setValue(55)
    dialog.show()
    def capture():
        output.parent.mkdir(parents=True,exist_ok=True)
        for theme in ('default','obsidian','ableton_gray'):
            apply_application_theme(theme)
            app.processEvents()
            dialog.grab().save(str(output.with_name('dialog-'+theme+'.png')))
        dialog.reject()
        window.close()
        app.quit()
    QTimer.singleShot(2500,capture)
    app.exec()


if __name__=='__main__':
    main()
