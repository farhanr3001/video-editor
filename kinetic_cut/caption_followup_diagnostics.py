"""Native caption word-count/hold/zoom/theme checks and decoded export evidence."""
def run(output,fixture):
    import os
    if os.environ.get('KINETIC_ZOOM_TEXT_SELFTEST')=='1':return run_zoom(output)
    if str(fixture).lower().endswith('.wav'):return run_templates(output,fixture)
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


def run_templates(output,fixture):
    """Private-desktop template, real generation and decoded output checks."""
    import os,sys,json,time,copy,hashlib,traceback,wave
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home');os.environ['QT_QPA_PLATFORM']='windows'
    from PySide6.QtCore import Qt,QRectF,QEventLoop,QTimer,QEvent
    from PySide6.QtGui import QImage,QPainter,QFont,QFontInfo,QColor
    from PySide6.QtWidgets import QApplication
    from .model import Project,ProjectSettings,Caption,CaptionStyle,MediaItem,TimelineItem,Transform
    from .ui import MainWindow
    from .caption_templates import CAPTION_TEMPLATES,get_template
    from .caption_style_dialog import CaptionStyleDialog,TemplateCardWidget
    from .caption_words import prepare_generated,timings
    from .caption_emojis import emojis_for_caption
    from .visuals import draw_caption,caption_geometry,caption_emoji_runs
    from .theme_widgets import apply_application_theme
    from .exporter import ExportPreset,export
    from .subtitle_render import write
    from .process import run as command
    from .icons import resource_path
    from .config import DATA_DIR
    from PIL import Image
    app=QApplication([]);app.setProperty('kineticTestDiscardUnsaved',True);app.setQuitOnLastWindowClosed(False)
    w=MainWindow();w.autosave_timer.stop();w.resize(1400,900);w.show()
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),checks=[])
    def check(name,ok):
        report['checks'].append(dict(name=name,passed=bool(ok)))
        assert ok,name
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def style(template):return CaptionStyle(**{k:v for k,v in template.items() if k in CaptionStyle.__dataclass_fields__})
    def render(p,c,at,target):
        p.playhead=at;image=QImage(p.settings.width,p.settings.height,QImage.Format_ARGB32);image.fill(Qt.black)
        painter=QPainter(image)
        try:draw_caption(painter,p,c,QRectF(image.rect()))
        finally:painter.end()
        image.save(str(target));return image
    path=Path(fixture).resolve();original=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        if os.environ.get('KINETIC_TEMPLATE_POLISH_ONLY')=='1':
            from PySide6.QtTest import QTest
            from PySide6.QtCore import QPoint
            from dataclasses import asdict
            from .caption_emojis import get_caption_emojis
            seed=Project(captions=[Caption('chosen',0,2,'THE MOST RANGE',customize=True),Caption('other',3,4,'Keep this',customize=True),Caption('track',4,5,'Track text')])
            w.set_project(seed);w.timeline.selected_caption_ids={'chosen'};w.inspector.select_caption('chosen');w.inspector.subtitle.setCurrentIndex(3)
            original_track=asdict(seed.subtitle_style);original_other=asdict(seed.captions[1].style)
            cards={card.template['id']:card for card in w.inspector.inspector_template_cards}
            QTest.mouseClick(cards['smart_highlight'],Qt.LeftButton);wait(30)
            check('custom caption receives bold Smart template',seed.captions[0].style.animation=='smart highlight' and seed.captions[0].style.font_face=='Bold')
            check('custom template preserves track and neighbours',asdict(seed.subtitle_style)==original_track and asdict(seed.captions[1].style)==original_other and not seed.captions[2].customize)
            check('custom template checkmark follows caption',cards['smart_highlight'].is_selected)
            check('custom Smart phrase marks',seed.captions[0].highlighted_words==[1,2])
            w.undo();check('custom template Undo',w.project.captions[0].style.animation==CaptionStyle().animation)
            w.redo();check('custom template Redo',w.project.captions[0].style.font_face=='Bold')
            w.timeline.selected_caption_ids={'chosen'};w.inspector.select_caption('chosen');w.inspector.subtitle.setCurrentIndex(3)
            QTest.mouseClick(cards['none'],Qt.LeftButton);wait(30)
            check('custom reset preserves customize and track',w.project.captions[0].customize and w.project.captions[0].style.animation==CaptionStyle().animation and asdict(w.project.subtitle_style)==original_track)
            w.timeline.selected_caption_ids={'chosen','other'};w.inspector.select_caption('chosen')
            w.inspector.apply_inspector_template(get_template('impact'))
            check('selected caption batch only',all(c.customize and c.style.font=='Impact' for c in w.project.captions[:2]) and asdict(w.project.subtitle_style)==original_track)
            for text,expected in [('THINK',[(0,'🤔')]),('video game',[(1,'🎮')]),('football game',[(1,'⚽')]),('game',[])]:
                check('semantic '+text,get_caption_emojis(text,1)==expected)
            for theme in ('default','final_cut_obsidian','ableton_gray'):
                apply_application_theme(theme)
                for size in ((150,110),(130,100)):
                    card=TemplateCardWidget(get_template('impact'));card.setFixedSize(*size);card.show();wait(30)
                    image=card.grab().toImage();x=card.width()-15;y=card.height()-15
                    check(theme+' empty circle '+str(size),all(image.pixelColor(x+dx,y+dy).name()=='#222734' for dx in range(-3,4) for dy in range(-3,4)))
                    image.save(str(out/(theme+'-empty-'+str(size[0])+'.png')))
                    card.set_selected(True);image=card.grab().toImage();check(theme+' checkmark '+str(size),image.pixelColor(x,y).name()!='#222734')
                    image.save(str(out/(theme+'-selected-'+str(size[0])+'.png')));card.close();card.deleteLater()
            # Actual image cards, no video/showcase export requested.
            for key,text in [('smart_highlight','THE MOST RANGE'),('capcut_emoji_pop','Let me think')]:
                c=Caption(key,0,2,text);sample=Project(captions=[c],subtitle_style=style(get_template(key)));prepare_generated([c],sample.subtitle_style)
                sample.settings.width=720;sample.settings.height=1280;sample.subtitle_style.size*=2/3
                render(sample,c,.5,out/(key+'-card.png'))
            check('fixture preserved',hashlib.sha256(path.read_bytes()).hexdigest()==original)
            report.update(passed=True,scope='Caption template polish: customized selection/history, bold preset, semantic emoji, three-theme normal/compact indicators')
            return 0
        from .assistant_api import edited
        seed=Project(captions=[Caption('chosen',0,2,'THE MOST RANGE',customize=True),Caption('other',3,4,'Keep this',style=CaptionStyle(font='Poppins'),customize=True)])
        original_seed=seed.to_dict();result,_=edited(seed,[dict(op='set_caption_style',template='smart_highlight',caption_ids=['chosen'])])
        check('atomic MCP template applies static phrase marks',result.captions[0].highlighted_words==[1,2] and result.captions[0].style.animation=='smart highlight')
        check('atomic template preserves original and custom neighbour',seed.to_dict()==original_seed and result.captions[1].style.font=='Poppins')
        for t in CAPTION_TEMPLATES:
            if t.get('is_none'):continue
            updated,_=edited(seed,[dict(op='set_caption_style',template=t['id'])])
            check('atomic template '+t['id'],updated.subtitle_style.font==t['font'] and updated.subtitle_style.size==t['size'])
        if os.environ.get('KINETIC_TEMPLATE_ATOMIC_ONLY')=='1':
            from .word_highlight import events
            from PySide6.QtCore import QRectF
            inline=Caption('inline',0,.4,'money ❤️')
            sample=Project(settings=ProjectSettings(width=360,height=640,fps=60),captions=[inline],subtitle_style=CaptionStyle(font='Poppins',size=24,animation='emoji pop'))
            for animation in ('emoji pop','smart highlight'):
                sample.subtitle_style.animation=animation;lines=events(sample,inline,'C0')
                embedded=[line for line in lines if line.startswith('Dialogue: 4,')]
                check(animation+' inline emoji motion matches text',bool(embedded) and (all('\\fscx100' in s and '\\fscx82' not in s for s in embedded) if animation=='emoji pop' else any('\\fscx86' in s for s in embedded)))
                ass=out/(animation.replace(' ','-')+'.ass');write(sample,ass);escaped=str(ass).replace('\\','/').replace(':','\\:');target=ass.with_suffix('.png')
                command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:s=360x640:r=60:d=0.4','-vf',"ass='"+escaped+"'",'-ss','0.04','-frames:v','1',str(target)],check=True,capture_output=True)
                check(animation+' inline emoji export decodes',target.is_file() and target.stat().st_size>1000)
            report.update(passed=True,scope='Bounded MCP template metadata and inline emoji animation parity corrections; prior full generation/preview/export gates retained')
            return 0
        with wave.open(str(path),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
        pattern=QImage(360,640,QImage.Format_RGB32);pattern.fill(QColor('#202A37'));pattern.save(str(out/'background.png'))
        p=Project(settings=ProjectSettings(width=1080,height=1920,fps=60),
            media=[MediaItem('bg',str(out/'background.png'),'image','Backdrop',duration,360,640),MediaItem('voice',str(path),'audio','Template voice',duration,has_audio=True)],
            timeline=[TimelineItem('background','bg','video_1',0,duration,transform=Transform(x=.5,y=.5)),TimelineItem('voice','voice','audio_1',0,duration,role='dialogue')],subtitle_style=style(get_template('smart_highlight')))
        w.request_waveform=lambda m:None;w.queue_proxy=lambda m:None;w.preview_quality.request=lambda:None
        w.set_project(p);w.timeline.select_ids(set(),'')
        model=resource_path('assets','caption-models','base.en')
        if not (model/'model.bin').is_file():model=Path.cwd()/'dist/KineticCut/_internal/assets/caption-models/base.en'
        check('existing speech model reused without download',(model/'model.bin').is_file())
        w.settings.update(whisper_model=str(model),caption_remove_periods=False,caption_censor=False,caption_device='cpu')
        worker=w.generate_captions(headless=True,words_per_card=3);check('real caption generation starts',worker is not None)
        errors=[];finished=[];worker.signals.error.connect(errors.append);worker.signals.finished.connect(lambda:finished.append(True))
        deadline=time.monotonic()+150
        while not finished and time.monotonic()<deadline:wait(50)
        check('real generated captions complete',finished and not errors and bool(p.captions))
        check('acoustic emphasis metadata reaches generated captions',any('emphasis_db' in word for c in p.captions for word in c.word_timings))
        check('smart highlights remain sparse',0<sum(len(c.highlighted_words) for c in p.captions)<sum(len(c.text.split()) for c in p.captions)*.5)
        check('word clocks and card tails remain valid',all(c.word_timings and max(b for a,b in timings(c))<=c.end+1e-6 for c in p.captions))
        generated=copy.deepcopy(p.captions);report['generated_words']=[dict(text=c.text,marks=c.highlighted_words,words=c.word_timings) for c in generated]
        w.undo();check('generation undo',not w.project.captions);w.redo();p=w.project;check('generation redo',len(p.captions)==len(generated))
        p.save(out/'smart-review.kcut')
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            d=CaptionStyleDialog(p.subtitle_style,{'caption_words_per_card':3},w);d.show();wait(80)
            for size in ((520,780),(480,600)):
                d.resize(*size);d.tabs.setCurrentIndex(1);wait(80);d.grab().save(str(out/(theme+'-templates-'+str(size[0])+'.png')))
                d.on_template_selected(get_template('impact'));d.tabs.setCurrentIndex(0);wait(80)
                check(theme+' impact defaults '+str(size[0]),d.selected_style().font=='Impact' and d.selected_style().glow_enabled and d.selected_style().color==CaptionStyle().color)
            d.close();d.deleteLater()
        check('requested first five templates',[t['id'] for t in CAPTION_TEMPLATES[1:6]]==['impact','hormozi_yellow','mrbeast_gold','smart_highlight','capcut_emoji_pop'])
        report['font_families']={t['id']:QFontInfo(QFont(t['font'])).family() for t in CAPTION_TEMPLATES if not t.get('is_none')}
        # Real template tiles, including static/default and hover/pop frames.
        for t in CAPTION_TEMPLATES:
            card=TemplateCardWidget(t);card.show();wait(10);card.grab().save(str(out/('tile-'+t['id']+'.png')));card.close();card.deleteLater()
        w.inspector.apply_inspector_template(get_template('smart_highlight'));p=w.project
        selected=next(c for c in p.captions if c.highlighted_words);old=list(selected.highlighted_words)
        w.inspector.toggle_word_highlight(selected.id,old[0]);check('manual marks keep smart animation',p.caption_style(selected).animation=='smart highlight' and old[0] not in selected.highlighted_words)
        w.undo();check('manual mark undo',next(c for c in w.project.captions if c.id==selected.id).highlighted_words==old)
        for key in ('cinematic_serif','basic'):
            p=w.project;p.captions=[];p.subtitle_style=style(get_template(key));w.model_changed();w.timeline.select_ids(set(),'')
            worker=w.generate_captions(headless=True,words_per_card=3);finished=[];errors=[]
            worker.signals.finished.connect(lambda:finished.append(True));worker.signals.error.connect(errors.append)
            deadline=time.monotonic()+120
            while not finished and time.monotonic()<deadline:wait(50)
            check(key+' actual generated captions complete',finished and not errors and bool(p.captions))
            c=p.captions[0];check(key+' generated style keeps requested font and size',c.style.font==get_template(key)['font'] and c.style.size==get_template(key)['size'])
            w.seek(min(c.end-.01,c.start+.3));deadline=time.monotonic()+5
            while ('caption',c.id) not in w.preview.text_rects and time.monotonic()<deadline:wait(50)
            check(key+' generated text reaches GPU preview',('caption',c.id) in w.preview.text_rects)
            w.preview.gpu.view.grabWindow().save(str(out/(key+'-generated-preview.png')))
            render(p,c,c.start+.3,out/(key+'-generated-text.png'));p.save(out/(key+'-review.kcut'))
            if key=='cinematic_serif':
                height=caption_geometry(p,c,QRectF(0,0,1080,1920))[0].boundingRect().height()
                check('cinematic generated letter height is readable',height>=55)
        # Explicit old-word gaps prove the emoji no longer follows the keyword.
        c=Caption('emoji',0,1.4,'have money',word_timings=[dict(text='have',start=.1,end=.3),dict(text='money',start=.7,end=1.1)])
        ep=Project(settings=ProjectSettings(width=360,height=640,fps=60),captions=[c],subtitle_style=style(get_template('capcut_emoji_pop')))
        ep.subtitle_style.size/=3
        geo=caption_geometry(ep,c,QRectF(0,0,360,640));runs=caption_emoji_runs(geo[2],geo[3],emojis_for_caption(ep,c,2),1.)
        check('money emoji selected',len(runs)==1)
        top=int(geo[2].top()-6);count=lambda file:sum(max(pixel)>90 for pixel in Image.open(file).convert('RGB').crop((0,0,360,max(1,top))).getdata())
        ass=out/'emoji.ass';write(ep,ass);escaped=str(ass).replace('\\','/').replace(':','\\:')
        video=out/'emoji-export.mp4';command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=black:s=360x640:r=60:d=1.4','-vf',"ass='"+escaped+"'",'-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
        for at in (.02,.4,.6,.9,1.3):
            preview=out/(f'emoji-{at}-preview.png');decoded=out/(f'emoji-{at}-export.png');render(ep,c,at,preview)
            command(['ffmpeg','-v','error','-y','-ss',str(at),'-i',str(video),'-frames:v','1',str(decoded)],check=True,capture_output=True)
            check('emoji visible across caption '+str(at),count(preview)>20 and count(decoded)>20)
        # Export both reference-style mixed colours and full-card emoji through
        # the actual application export entry point, with recorded backend.
        for key in ('smart_highlight','capcut_emoji_pop'):
            demo=copy.deepcopy(ep);demo.subtitle_style=style(get_template(key));demo.subtitle_style.size/=3
            demo.media=[MediaItem('bg',str(out/'background.png'),'image','Backdrop',1.4,360,640)];demo.timeline=[TimelineItem('bg','bg','video_1',0,1.4,transform=Transform(x=.5,y=.5))]
            if key=='smart_highlight':demo.captions=[Caption('mixed',0,1.4,'THE MOST RANGE',highlighted_words=[1,2])]
            messages=[];export(demo,str(out/(key+'-native-export.mp4')),ExportPreset('Test','h264',6,128,''),hardware='Auto',export_audio=False,progress=lambda v,s:messages.append(s))
            report[key+'_export_messages']=list(dict.fromkeys(messages))
            import av
            with av.open(str(out/(key+'-native-export.mp4'))) as movie:frames=list(movie.decode(video=0))
            check(key+' native exported moving clock',len(frames)>=80)
        check('input audio preserved',hashlib.sha256(path.read_bytes()).hexdigest()==original)
        report['templates']=len(CAPTION_TEMPLATES)-1;report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        w.close();deadline=time.monotonic()+15
        while (w.isVisible() or w._workers) and time.monotonic()<deadline:wait(50)
        app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
        (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return 0 if report['passed'] else 1


def run_zoom(output):
    """Private desktop: inspect actual GPU text pixels while preparation lags."""
    import os,json,time,traceback,copy
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['QT_QPA_PLATFORM']='windows'
    import numpy as np
    from PySide6.QtCore import Qt,QPointF,QEventLoop,QTimer
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project,Caption,CaptionStyle,TimelineItem
    from .caption_style_dialog import CaptionStyleDialog
    from .caption_templates import get_template
    from .theme_widgets import apply_application_theme
    app=QApplication([]);app.setProperty('kineticTestDiscardUnsaved',True);app.setQuitOnLastWindowClosed(False)
    w=MainWindow();w.autosave_timer.stop();w.resize(1400,900);w.show()
    report=dict(passed=False,checks=[],remote=os.environ.get('KINETIC_GPU_PREVIEW_PROCESS','1')!='0')
    def check(name,ok):
        report['checks'].append(dict(name=name,passed=bool(ok)));assert ok,name
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def yellow(image):
        image=image.convertToFormat(QImage.Format_RGBA8888)
        data=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
        ys,xs=np.where((data[:,:,0]>180)&(data[:,:,1]>180)&(data[:,:,2]<90))
        return (float(xs.min()),float(ys.min()),float(xs.max()),float(ys.max())) if len(xs) else None
    try:
        for kind in ('caption','title','headline'):
            style=CaptionStyle(size=100,color='#ffff00',animation='none',outline_width=0,shadow_enabled=False,box_style='headline' if kind=='headline' else '')
            p=Project(subtitle_style=style);p.playhead=.5
            if kind=='caption':p.captions=[Caption('text',0,2,'ELLIE IS')]
            else:p.timeline=[TimelineItem('text','','video_1',0,2,role='title',title_text='ELLIE IS',title_style=style)]
            w.set_project(p);w.preview.view_zoom=1.;w.preview.view_pan=QPointF();w.timeline.select_ids(set(),'');w.seek(.5);wait(800)
            gpu=w.preview.gpu;deadline=time.monotonic()+12
            while not gpu.bounds and time.monotonic()<deadline:wait(50)
            wait(150);initial=w.preview.composition_rect();base=yellow(gpu.view.grabWindow())
            check(kind+' actual initial text pixels',base is not None)
            # Freeze only preparation after a valid raster: deterministic slow
            # compositor, so geometry must remain correct before any new pixels.
            start=getattr(gpu,'_start',None)
            if start:gpu._start=lambda:None
            for index,zoom in enumerate((.65,.45,.8,1.2,1.,.55)):
                w.preview.view_zoom=zoom;w.preview.update()
                if hasattr(gpu,'sync'):gpu.sync()
                else:gpu.schedule()
                wait(25);image=gpu.view.grabWindow();found=yellow(image);frame=w.preview.composition_rect()
                expected=tuple((v-(initial.x() if i%2==0 else initial.y()))*zoom+(frame.x() if i%2==0 else frame.y()) for i,v in enumerate(base))
                check(kind+' continuous zoom pixels '+str(index),found is not None and max(abs(a-b) for a,b in zip(found,expected))<6)
                if index in (1,3):image.save(str(out/(kind+'-zoom-'+str(index)+'.png')))
            if start:gpu._start=start;gpu.schedule()
            wait(150)
        check('Titles category is second',w.effects_panel.categories.item(1).text()=='Titles')
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            d=CaptionStyleDialog(CaptionStyle(size=150),{'caption_words_per_card':12,'caption_censor':True,'caption_remove_periods':True},w);d.show()
            for width,height in ((520,780),(480,600)):
                d.resize(width,height);d.on_template_selected(get_template('smart_highlight'));d.restore_defaults.click();wait(30)
                check(theme+' restore '+str(width),d.words.value()==3 and d.size.value()==72 and not d.censor.isChecked() and not d.remove_periods.isChecked() and d.selected_template_id=='none')
                d.grab().save(str(out/(theme+'-defaults-'+str(width)+'.png')))
            d.close();d.deleteLater()
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        w.close();deadline=time.monotonic()+12
        while w.isVisible() and time.monotonic()<deadline:wait(50)
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
