"""Isolated packaged subtitle layout, batch editing and typing checks."""
def run(output):
    import os,json,sys,time,traceback
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(output/'home')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtCore import QThreadPool
    from .ui import MainWindow
    from .theme import STYLESHEET
    from .model import Project,Caption
    from .captions import split_caption
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
    for font in ('arial.ttf','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
    w=MainWindow(); w.resize(1400,850); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False))}
    try:
        p=Project(captions=[Caption(str(i),i*.5,i*.5+.4,'Subtitle '+str(i)) for i in range(1000)])
        w.set_project(p); w.timeline.select_captions({'0','1'},'0'); panel=w.inspector
        app.processEvents(); panel.grab().save(str(output/'caption-custom-off.png'))
        before_header=(panel.caption_text.y(),panel.customize.y())
        panel.customize.setChecked(True); panel.edit_style('position_y',.4)
        assert all(c.customize and c.style.position_y==.4 for c in p.captions[:2]); assert not p.captions[2].customize
        app.processEvents(); panel.grab().save(str(output/'custom-caption.png'))
        assert before_header==(panel.caption_text.y(),panel.customize.y()); report['stable_caption_header']=True
        panel.subtitle.setCurrentIndex(2); app.processEvents(); panel.grab().save(str(output/'timings.png'))
        assert panel.caption_table.rowCount()==1000; assert not panel.subtitle.widget(0).isAncestorOf(panel.caption_table)
        report['timings_and_batch_style']=True
        panel.subtitle.setCurrentIndex(0); w.timeline.select_captions({'0'},'0'); app.processEvents()
        before=p.captions[0].text; times=[]
        for character in ' quick typing':
            start=time.perf_counter(); panel.caption_text.insertPlainText(character); app.processEvents(); times.append((time.perf_counter()-start)*1000)
        assert p.captions[0].text==before+' quick typing'; w.flush_text_edit(); w.undo(); assert w.project.captions[0].text==before
        report['typing_mean_ms']=sum(times)/len(times); report['typing_max_ms']=max(times); report['typing_undo']=True
        assert split_caption(Caption('word',0,1,'Word'),.5) is not None
        p=Project(captions=[Caption('a',0,4,'One'),Caption('b',2,3,'Two')]); p.overwrite_captions({'b'})
        assert sorted((c.start,c.end) for c in p.captions)==[(0,2),(2,3),(3,4)]
        report['single_word_cut_and_overwrite']=True
        from .caption_style_diagnostics import run as check_styles
        report['caption_styles']=check_styles(output,app,panel); report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); (output/'report.json').write_text(json.dumps(report,indent=2)); app.processEvents()
    return 0 if report.get('passed') else 1
