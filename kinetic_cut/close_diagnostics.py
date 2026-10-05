"""Actual themed close prompts and cancellation in an isolated native fixture."""
def run(output):
    import json,os,sys,traceback
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QTimer,QThreadPool,QEvent
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem
    from .close_guard import mark_saved
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion')
    w=None; report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),themes=[])
    try:
        w=MainWindow(); w.autosave_timer.stop(); w.resize(1200,800); w.show()
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False)
            w.set_project(Project(media=[MediaItem('m','missing.png','image','Close fixture',10,1920,1080)],timeline=[TimelineItem('v','m','video_1',0,2)]))
            w.project.path=str(out/'fixture.kcut'); mark_saved(w)
            w.project.timeline[0].transform.scale=2
            observed=[]
            def click():
                box=app.activeModalWidget()
                observed.append(isinstance(box,QMessageBox))
                box.grab().save(str(out/(theme+'-close.png')))
                QTest.mouseClick(box.button(QMessageBox.Cancel),Qt.LeftButton)
            QTimer.singleShot(30,click); assert not w.close()
            assert observed==[True] and w.isVisible()
            report['themes'].append(theme)
        w.project.timeline[0].transform.scale=1.0
        unexpected=[]
        def dismiss_unexpected():
            box=app.activeModalWidget()
            if isinstance(box,QMessageBox):
                unexpected.append(box.text()); box.reject()
        QTimer.singleShot(500,dismiss_unexpected)
        assert w.close() and not unexpected  # Unchanged saved project needs no prompt.
        report.update(passed=True,cancel_preserved_window=True,unchanged_saved_closed=True)
    except Exception:report['error']=traceback.format_exc()
    finally:
        app.setProperty('kineticTestDiscardUnsaved',True)
        if w:w.close(); w.deleteLater()
        QThreadPool.globalInstance().waitForDone(10000)
        QApplication.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
        (out/'report.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1
