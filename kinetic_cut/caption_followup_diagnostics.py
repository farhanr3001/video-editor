"""Native caption word-count/hold/zoom/theme checks and decoded export evidence."""
def run(output,fixture):
    import os,sys,json,copy,hashlib,traceback
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QRectF,QEventLoop,QTimer
    from PySide6.QtGui import QImage,QPainter,QFont,QFontInfo
    from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSpinBox
    from PySide6.QtTest import QTest
    from .model import Project,Caption
    from .visuals import draw_caption,caption_geometry
    from .caption_emojis import emojis_for_caption
    from .caption_style_dialog import CaptionStyleDialog
    from .caption_templates import CAPTION_TEMPLATES
    from .theme_widgets import apply_application_theme
    from .subtitle_render import write
    from .process import run as process
    from PIL import Image
    app=QApplication([]); app.setStyle('Fusion'); path=Path(fixture).resolve()
    before=hashlib.sha256(path.read_bytes()).hexdigest(); report={'frozen':bool(getattr(sys,'frozen',False))}
    windows=[]
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def render(p,c,t,width=360):
        p.playhead=t; image=QImage(width,round(width*1920/1080),QImage.Format_ARGB32); image.fill(Qt.black)
        painter=QPainter(image)
        try:draw_caption(painter,p,c,QRectF(image.rect()))
        finally:painter.end()
        return image
    def ink(file,box):
        im=Image.open(file).convert('RGB').crop(tuple(round(v) for v in (box.left(),box.top(),box.right(),box.bottom())))
        pixels=list(im.getdata()); return dict(white=sum(min(rgb)>150 for rgb in pixels),yellow=sum(r>120 and g>100 and b<min(r,g)*.5 for r,g,b in pixels))
    try:
        p=Project.load(path); original_style=copy.deepcopy(p.subtitle_style.__dict__)
        happened=next(c for c in p.captions if c.text.casefold()=='happened')
        headphones=next(c for c in p.captions if c.text.casefold()=='headphones')
        assert emojis_for_caption(p,headphones)==[(0,'🎧')]
        images=[render(p,happened,t) for t in (happened.start+.02,happened.start+.4,happened.end-.02)]
        assert all(bytes(im.constBits())==bytes(images[0].constBits()) for im in images)
        images[0].save(str(out/'happened-static.png'))
        report['happened_static_through_hold']=True; report['headphones_selected']=True
        report['komika_family']=QFontInfo(QFont(p.subtitle_style.font)).family()
        assert report['komika_family']==p.subtitle_style.font,report['komika_family']
        report['word_counts']=[]; report['themes']=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            d=CaptionStyleDialog(p.subtitle_style,{'caption_words_per_card':2}); windows.append(d)
            d.show(); wait(100)
            for size in ((500,780),(480,600)):
                d.resize(*size); wait(100); d.grab().save(str(out/(theme+'-setup-'+str(size[0])+'.png')))
            d.words.setValue(2); option=QStyleOptionSpinBox(); d.words.initStyleOption(option)
            for sub,expected in ((QStyle.SC_SpinBoxUp,3),(QStyle.SC_SpinBoxDown,2)):
                rect=d.words.style().subControlRect(QStyle.CC_SpinBox,option,sub,d.words)
                QTest.mouseClick(d.words,Qt.LeftButton,pos=rect.center()); assert d.words.value()==expected
            d.close(); report['themes'].append(theme)
        for count in range(1,13):
            text=' '.join(['word']*(count//2)+['headphones']+['word']*(count-count//2-1))
            c=Caption('sample',0,3,text,word_timings=[dict(text=w,start=i*.18,end=i*.18+.15) for i,w in enumerate(text.split())])
            sample=Project(subtitle_style=copy.deepcopy(p.subtitle_style),captions=[c])
            frame=QRectF(0,0,1080,1920); geometry=caption_geometry(sample,c,frame)
            index=emojis_for_caption(sample,c)[0][0]; time=index*.18+.1
            for width in (180,360,1080):
                image=render(sample,c,time,width)
                if count in (1,2,3,6,12):image.save(str(out/(f'words-{count}-width-{width}.png')))
                scaled=caption_geometry(sample,c,QRectF(image.rect()))
                for (a,_),(b,_) in zip(geometry[4],scaled[4]):
                    assert a.elementCount()==b.elementCount()
                    for n in range(a.elementCount()):
                        assert abs(a.elementAt(n).x-b.elementAt(n).x*1080/width)<1e-5
                        assert abs(a.elementAt(n).y-b.elementAt(n).y*1080/width)<1e-5
            report['word_counts'].append(count)
        assert p.subtitle_style.__dict__==original_style
        # Full transcript retains the real semantic plan; no mutation of fixture.
        ass=out/'fixture.ass'; write(p,ass); escaped=str(ass).replace('\\','/').replace(':','\\:')
        video=out/'fixture-export.mp4'
        process(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:s=360x640:r=60:d=7','-vf',"ass='"+escaped+"'",'-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
        checks=[]
        for c,time,label in ((happened,happened.start+.02,'happened-start'),(happened,happened.start+.4,'happened-hold'),(headphones,headphones.start+.15,'headphones')):
            preview=out/(label+'-preview.png'); decoded=out/(label+'-export.png'); render(p,c,time).save(str(preview))
            process(['ffmpeg','-v','error','-y','-ss',str(time),'-i',str(video),'-frames:v','1',str(decoded)],capture_output=True,check=True)
            box=caption_geometry(p,c,QRectF(0,0,360,640))[2]
            a,b=ink(preview,box),ink(decoded,box)
            if c==happened:assert a['white']>100 and b['white']>100 and a['yellow']==b['yellow']==0,(a,b)
            else:assert a['yellow']>100 and b['yellow']>100,(a,b)
            checks.append(dict(label=label,preview=a,export=b))
        report['decoded_color_checks']=checks
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
        report.update(style_unchanged=True,original_project_unchanged=True,passed=True)
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        for window in windows:window.close()
        app.processEvents(); (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report.get('passed') else 1
