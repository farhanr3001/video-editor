"""Native Qt visual matrix, with synthetic local media and no device/network I/O."""
def run(folder):
    import os, sys, json, traceback, hashlib, copy
    from pathlib import Path
    out = Path(folder).resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(out / 'unit-test-home')
    from PySide6.QtCore import Qt, QEventLoop, QTimer, QEvent
    from PySide6.QtGui import QImage, QPainter, QColor, QFontDatabase
    from PySide6.QtWidgets import QApplication, QTreeWidgetItem, QDialog
    from .ui import MainWindow
    from .model import Project, MediaItem, TimelineItem, Caption
    from .workspace import set_page
    from .theme import PALETTES
    from .theme_dialog import UIThemesDialog
    from .caption_style_dialog import CaptionStyleDialog
    from .keyframe_editor import KeyframeEditor
    from .vfx_timing_dialog import VFXTimingDialog
    from .tts_dialog import TTSDialog
    from .tts_dialogue_dialog import TTSDialogueDialog
    from .downloader_dialog import MediaDownloaderDialog

    app = QApplication([]); app.setStyle('Fusion'); app.setQuitOnLastWindowClosed(False)
    for font in ('arial.ttf', 'arialbd.ttf', 'segoeui.ttf', 'segoeuib.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    image = QImage(640, 360, QImage.Format_RGB32); image.fill(QColor('#335477'))
    painter = QPainter(image)
    painter.fillRect(30, 45, 180, 220, QColor('#cf7d41'))
    painter.fillRect(230, 95, 280, 170, QColor('#448868')); painter.end()
    source = out/'fixture.png'; image.save(str(source))
    w = MainWindow(); w.resize(1500, 900); w.show(); w.autosave_timer.stop()
    page = w.phone_connect; page.loaded = True
    # UI fixtures only: even selecting a simulated phone cannot launch a worker.
    page.connect_device = lambda: None
    page.request = lambda *a, **k: None
    p = Project(media=[MediaItem('fixture', str(source), 'image', 'Theme QA image', 8, 640, 360)],
                timeline=[TimelineItem('clip', 'fixture', 'video_1', 0, 8)],
                captions=[Caption('caption', 0, 6, 'Caption colours stay unchanged')])
    p.settings.width=1080; p.settings.height=1920
    p.timeline[0].effects=[{'name':'Punch Zoom','enabled':True,'start_time':1.,'duration':1.}]
    w.set_project(p); w.seek(2); w.transform_box_tool.setChecked(False)
    from .widgets import PreviewCanvas
    program_preview=PreviewCanvas(); program_preview.set_project(p)
    program_preview.setFixedSize(320, 500); program_preview.set_transform_controls_visible(False)
    report={'frozen':bool(getattr(sys,'frozen',False)), 'screenshots':[], 'hardware_tested':False}
    def wait(ms=110):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def shot(widget,name):
        wait(); assert widget.grab().save(str(out/(name+'.png')))
        report['screenshots'].append(name)
    def close_dialog(d):
        d.reject() if isinstance(d,QDialog) else d.close()
        d.deleteLater(); app.sendPostedEvents(None,QEvent.DeferredDelete); wait(30)
    def dialog(d,name):
        d.show(); shot(d,name); close_dialog(d)
    try:
        reference=None
        original_transform=copy.deepcopy(p.timeline[0].transform)
        original_style=copy.deepcopy(p.subtitle_style)
        for theme in PALETTES:
            w.apply_theme(theme,save=False); set_page(w,0)
            w.effects_toggle.setChecked(True); w.select_item('clip')
            for tab,label in enumerate(('transform','audio','effects','colours')):
                w.inspector.tabs.setCurrentIndex(tab); shot(w,theme+'-'+label)
            w.select_caption('caption'); shot(w,theme+'-captions')
            w.inspector.subtitle.setCurrentIndex(1); shot(w,theme+'-caption-track-style')
            w.inspector.subtitle.setCurrentIndex(2); shot(w,theme+'-caption-timings')
            w.inspector.subtitle.setCurrentIndex(0)
            w.preview.select_caption(''); w.preview.select_item(''); wait()
            # Fixed viewport excludes theme chrome/borders and splitter rounding.
            rect=program_preview.composition_rect().toRect().adjusted(2,2,-2,-2)
            content=program_preview.grab().toImage().copy(rect)
            digest=hashlib.sha256(bytes(content.bits())).hexdigest()
            if reference is None: reference=digest
            assert digest==reference, 'Theme changed the program image'
            dialog(CaptionStyleDialog(p.subtitle_style,w.settings,w),theme+'-caption-style')
            dialog(KeyframeEditor(w,p.timeline[0]),theme+'-keyframes')
            dialog(VFXTimingDialog(w,p.timeline[0],p.timeline[0].effects[0]),theme+'-vfx-timing')
            dialog(TTSDialog(w,'A clear voice for your next edit.'),theme+'-voiceover')
            dialog(TTSDialogueDialog(w,'A caption and dialogue preview.'),theme+'-dialogue')
            dialog(MediaDownloaderDialog(w),theme+'-downloader')
            set_page(w,1); shot(w,theme+'-deliver')
            set_page(w,2)
            page.platform='iphone'; page.platform_buttons['iphone'].setChecked(True); page.apply_platform_text()
            page.devices.clear(); page.device_changed()
            shot(w,theme+'-iphone-disconnected')
            page.platform='android'; page.platform_buttons['android'].setChecked(True); page.apply_platform_text()
            page.devices.addItem('QA phone (simulated)',dict(name='QA phone (simulated)',model='UI fixture',state='unauthorized'))
            page.device_changed(); shot(w,theme+'-android-authorize')
            page.devices.setItemData(0,dict(name='QA phone (simulated)',model='UI fixture',state='ready'))
            page.device_changed()
            QTreeWidgetItem(page.files,['Videos','Folder',''])
            QTreeWidgetItem(page.files,['Finished edit.mp4','26.4 MB','Today'])
            shot(w,theme+'-android-files')
            page.tabs.setCurrentIndex(1); shot(w,theme+'-phone-queue'); page.tabs.setCurrentIndex(0)
            page.mirror.pop_out(); wait()
            shot(page.mirror.popout_window,theme+'-mirror-popout')
            page.mirror.dock_back()
            dialog(UIThemesDialog(w),theme+'-chooser')
        w.apply_theme('default',save=False); set_page(w,0); w.select_item('clip')
        shot(w,'default-roundtrip')
        assert p.timeline[0].transform==original_transform
        assert p.subtitle_style==original_style
        report['program_image_unchanged']=True
        report['passed']=True
    except Exception:
        report['passed']=False; report['error']=traceback.format_exc()
    finally:
        for d in list(app.topLevelWidgets()):
            if d is not w:
                d.reject() if isinstance(d,QDialog) else d.close()
        w._saved_project_key=w._history_key(w.project)
        w.close(); app.processEvents()
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
