"""Offscreen UI and real FFmpeg checks for caption styles, in source or EXE."""
def run(output,app,panel):
    from pathlib import Path
    from PySide6.QtCore import QRectF,Qt
    from PySide6.QtGui import QImage,QPainter,QFontDatabase
    from .model import Project,Caption,CaptionStyle
    from .caption_style_dialog import CaptionStyleDialog
    from .caption_fonts import load_fonts
    from .caption_words import prepare_generated
    from .visuals import draw_caption
    from .subtitle_render import write
    from .exporter import _escape_ass_path
    from .icons import resource_path
    from .process import run as run_process
    load_fonts(); assert all(font in QFontDatabase.families() for font in ('Geometos','Anton','Poppins','Montserrat','TikTok Sans'))
    dialog=CaptionStyleDialog(CaptionStyle(),{}); dialog.animation.setCurrentText('word highlight 2'); dialog.glow.setChecked(True); dialog.show(); app.processEvents()
    dialog.grab().save(str(output/'caption-style-dialog.png')); dialog.font.showPopup(); app.processEvents()
    dialog.font.view().window().grab().save(str(output/'caption-font-menu.png')); dialog.font.hidePopup(); dialog.close()
    panel.toggle_word_highlight('0',1); panel.subtitle.setCurrentIndex(2); app.processEvents(); panel.grab().save(str(output/'timings-highlighted.png'))
    caption=Caption('style',0,3,'This looks incredible',word_timings=[dict(text='This',start=0,end=.3),dict(text='looks',start=.8,end=1.1),dict(text='incredible',start=2,end=2.7)])
    project=Project(captions=[caption]); project.settings.width=640; project.settings.height=360
    style=project.subtitle_style; style.font='Poppins'; style.size=44; style.position_y=.5; style.outline_width=1; style.shadow_enabled=False; style.glow_enabled=True
    report={}
    for font,animation in [('Poppins',animation) for animation in ('word highlight 2','fade every word','punch','none')]+[('Geometos','none')]:
        style.font=font; style.glow_enabled=font!='Geometos'
        style.animation=animation; prepare_generated([caption],style); name=('geometos-' if font=='Geometos' else '')+animation.replace(' ','-')
        for at in (.4,1.,2.3):
            project.playhead=at; image=QImage(640,360,QImage.Format_ARGB32); image.fill(Qt.black); painter=QPainter(image); painter.setRenderHint(QPainter.Antialiasing)
            try:draw_caption(painter,project,caption,QRectF(0,0,640,360))
            finally:painter.end()
            image.save(str(output/(name+'-'+str(at)+'-preview.png')))
        ass=output/(name+'.ass'); write(project,ass)
        fontdir=_escape_ass_path(str(resource_path('assets','fonts')))
        target=output/(name+'-export.png')
        command=['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=640x360:r=30:d=3','-vf',"ass='"+_escape_ass_path(str(ass))+"':fontsdir='"+fontdir+"',select='gte(t,2.3)'",'-frames:v','1',str(target)]
        run_process(command,check=True,capture_output=True,timeout=40); assert target.stat().st_size>1500
        # Regression: text font metrics must not change size in export.
        from PIL import Image,ImageChops
        preview=Image.open(output/(name+'-2.3-preview.png')).convert('RGB'); exported=Image.open(target).convert('RGB')
        preview_box=preview.point(lambda x:255 if x>150 else 0).getbbox(); export_box=exported.point(lambda x:255 if x>150 else 0).getbbox()
        assert all(abs(a-b)<=5 for a,b in zip(preview_box,export_box)),(name,preview_box,export_box)
        report[name]=True
    return report
