"""Disposable native acceptance for Help, recovery and optional offline narration."""
import json,os,shutil,sys,time
from pathlib import Path

def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home')
    if os.environ.get('KINETIC_DROPDOWN_SELFTEST')=='1':return dropdowns(output)
    from unittest.mock import patch
    from PySide6.QtCore import QEventLoop,QTimer,QEvent
    from PySide6.QtWidgets import QApplication,QPushButton
    from .theme_widgets import apply_application_theme
    from .help_ui import AboutDialog,RepairDialog
    from .recovery_ui import RecoveryDialog
    from . import recovery_store as store,offline_speech
    from .ui import MainWindow
    from .model import Project,TimelineItem
    from .dialog_jobs import active_dialog_threads
    app=QApplication.instance() or QApplication([]);app.setProperty('kineticTestDiscardUnsaved',True)
    def settle(predicate,timeout=15):
        end=time.monotonic()+timeout;loop=QEventLoop();timer=QTimer();timer.setInterval(5)
        timer.timeout.connect(lambda:loop.quit() if predicate() or time.monotonic()>end else None);timer.start();loop.exec();timer.stop()
        assert predicate(),'Native diagnostic operation did not settle'
    token=store.session();project=Project(name='Recovery example',timeline=[TimelineItem('title','','video_1',0,3,role='title',title_text='Example')])
    store.save(project,token);project.timeline[0].title_text='Later edit';store.save(project,token);store.finish(token)
    window=MainWindow();window.autosave_timer.stop();window.show();checks=[]
    fixture=os.environ.get('KINETIC_OFFLINE_VOICE_FIXTURE')
    if fixture:
        fixture=Path(fixture).resolve();target=offline_speech.component_root();target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(fixture,target,dirs_exist_ok=True);assert offline_speech.ready()
    crashed=store.session();store.save(project,crashed)
    store.atomic(store.root()/'sessions'/(crashed+'.json'),dict(pid=2_000_000_000,created=0))
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        apply_application_theme(theme)
        for width in (510,780):
            with patch('kinetic_cut.updates.check',return_value=None):
                from .cache_manager import CacheManagerDialog
                from .component_ui import InstallComponentDialog
                from .tts_dialogue_dialog import TTSDialogueDialog
                from .tts_availability import Availability
                with patch('kinetic_cut.tts_availability.probe_service',return_value=Availability(False,'The online voice service is temporarily unavailable.')):
                    speech=TTSDialogueDialog(window,initial_text='Offline narration example.');speech.voice_combo.setCurrentIndex(speech.voice_combo.findData(offline_speech.VOICE))
                    speech.voice_availability.started=True;speech.voice_availability.result=Availability(False,'The online voice service is temporarily unavailable.');speech.voice_availability.refresh()
                    speech._audio_output.setVolume(0)
                    dialogs=[AboutDialog(window),RepairDialog(window),RecoveryDialog(window),RecoveryDialog(window,crash_only=True),CacheManagerDialog(window),InstallComponentDialog(window,'offline-speech'),speech]
                for dialog in dialogs:
                    actual_width=max(width,dialog.minimumWidth());dialog.resize(actual_width,max(340,dialog.height()));dialog.show();settle(lambda:not window._workers)
                    if isinstance(dialog,CacheManagerDialog):assert dialog.wait_for_scan()
                    assert dialog.width()<=actual_width+1
                    assert dialog.height()<=window.screen().availableGeometry().height()
                    for button in dialog.findChildren(QPushButton):
                        if not button.isVisible():continue
                        if isinstance(dialog,CacheManagerDialog) and dialog.scroll_area.widget().isAncestorOf(button):dialog.scroll_area.ensureWidgetVisible(button);app.processEvents()
                        rect=button.rect();top=button.mapTo(dialog,rect.topLeft());bottom=button.mapTo(dialog,rect.bottomRight())
                        assert dialog.rect().contains(top) and dialog.rect().contains(bottom),(type(dialog).__name__,button.text(),top,bottom)
                    if isinstance(dialog,RecoveryDialog):
                        assert dialog.table.rowCount()>=(1 if dialog.crash_only else 2)
                        dialog.table.selectRow(0 if dialog.crash_only else 1);assert dialog.restore_button.isEnabled()
                        app.processEvents()
                        from .theme_widgets import ui_color
                        pixels=dialog.table.viewport().grab().toImage();expected=ui_color('bg_selected')
                        selected=dialog.table.currentRow()
                        for column in range(4):
                            cell=dialog.table.visualRect(dialog.table.model().index(selected,column))
                            sample=pixels.pixelColor(cell.left()+3,cell.center().y())
                            assert max(abs(a-b) for a,b in zip(sample.getRgb()[:3],expected.getRgb()[:3]))<=3,('Selection gutter obscures text',column,sample.name(),expected.name())
                    if isinstance(dialog,CacheManagerDialog):dialog.scroll_area.verticalScrollBar().setValue(0)
                    suffix='-crash' if getattr(dialog,'crash_only',False) else ''
                    dialog.grab().save(str(output/f'{theme}-{type(dialog).__name__}{suffix}-{width}.png'))
                    checks.append(dict(theme=theme,dialog=type(dialog).__name__,width=dialog.width(),height=dialog.height()));dialog.close();dialog.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
    # Actual restore through the control preserves the original saved project.
    original=output/'original.kcut';project.save(original);original_bytes=original.read_bytes()
    recovery=RecoveryDialog(window);recovery.show();settle(lambda:not window._workers);recovery.table.selectRow(0);recovery.restore_button.click()
    assert window.project.path=='' and original.read_bytes()==original_bytes
    assert window.project.timeline[0].title_text=='Later edit';recovery.deleteLater()
    offline=[]
    if fixture:
        from .tts import synthesize_speech
        from .icons import resource_path
        ffmpeg=resource_path('assets','tools','ffmpeg.exe')
        if not ffmpeg.is_file():ffmpeg=Path.cwd()/'build/distribution-stage/KineticCut/_internal/assets/tools/ffmpeg.exe'
        assert ffmpeg.is_file()
        for rate,pitch in ((0,0),(20,-4)):
            target_audio=output/f'offline-{rate}-{pitch}.mp3'
            with patch('urllib.request.urlopen',side_effect=AssertionError('Offline synthesis attempted a network connection')):
                synthesize_speech('This narration works without an internet connection.',offline_speech.VOICE,rate,pitch,output_path=target_audio,ffmpeg_bin=str(ffmpeg))
            assert target_audio.stat().st_size>1000;offline.append(dict(rate=rate,pitch=pitch,bytes=target_audio.stat().st_size))
    window.close();settle(lambda:not window._workers and not active_dialog_threads());app.sendPostedEvents(None,QEvent.DeferredDelete)
    report=dict(passed=True,private_desktop=os.environ.get('KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP')=='1',owner_data_used=False,dialogs=checks,restore_preserved_original=True,offline=offline)
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return 0


def dropdowns(output):
    """Real popup input and indicator pixels, without opening owner projects."""
    from unittest.mock import patch
    from PySide6.QtCore import Qt,QPoint,QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QWidget,QFormLayout,QComboBox,QFontComboBox,QStyle,QStyleOptionComboBox
    from .controls import SafeComboBox
    from .render_queue import RecentLocations
    from .tracking_design import TrackingComboBox
    from .theme_widgets import apply_application_theme,set_ui_style
    from .help_ui import AboutDialog
    from .tts_dialogue_dialog import TTSDialogueDialog
    from .tts_availability import Availability
    from .ui import MainWindow
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setProperty('kineticTestDiscardUnsaved',True)
    window=MainWindow();window.autosave_timer.stop();window.show();QTest.qWait(800);checks=[]
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        apply_application_theme(theme)
        for width in (360,620):
            form=QWidget();layout=QFormLayout(form)
            plain=QComboBox();safe=SafeComboBox();tracking=TrackingComboBox()
            editable=RecentLocations({});font=QFontComboBox()
            for name,combo in [('Standard',plain),('Safe',safe),('Tracking',tracking),('Editable location',editable),('Font',font)]:
                if combo in (plain,safe,tracking):combo.addItems(['First choice','Second choice','Third choice'])
                layout.addRow(name,combo)
            form.resize(width,260);form.show();form.raise_();form.activateWindow();QTest.qWait(80)
            for name,combo in [('Standard',plain),('Safe',safe),('Tracking',tracking),('Editable location',editable),('Font',font)]:
                option=QStyleOptionComboBox();combo.initStyleOption(option)
                rect=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxArrow,combo)
                image=combo.grab().toImage();background=image.pixelColor(rect.left()+2,5)
                ink=[(x,y) for x in range(rect.left()+2,rect.right()-2) for y in range(4,combo.height()-4)
                     if max(abs(a-b) for a,b in zip(image.pixelColor(x,y).getRgb()[:3],background.getRgb()[:3]))>40]
                assert 8<=len(ink)<=55,(theme,name,'indicator ink',len(ink))
                assert max(x for x,y in ink)-min(x for x,y in ink)<=9,(theme,name,'bar or square')
                assert max(y for x,y in ink)-min(y for x,y in ink)<=6,(theme,name,'bar or square')
                checks.append(dict(theme=theme,width=width,control=name,indicator_pixels=len(ink)))
            form.grab().save(str(output/f'{theme}-controls-{width}.png'))
            # Use actual arrow clicks and keyboard navigation through the popup.
            for name,combo in [('Standard',plain),('Safe',safe),('Tracking',tracking)]:
                option=QStyleOptionComboBox();combo.initStyleOption(option)
                rect=combo.style().subControlRect(QStyle.CC_ComboBox,option,QStyle.SC_ComboBoxArrow,combo)
                QTest.mouseClick(combo,Qt.LeftButton,pos=rect.center());QTest.qWait(25)
                assert combo.view().isVisible(),name
                form.grab().save(str(output/f'{theme}-{name}-open-{width}.png'))
                QTest.keyClick(combo.view(),Qt.Key_Down);QTest.keyClick(combo.view(),Qt.Key_Return)
                assert combo.currentIndex()==1 and not combo.view().isVisible(),name
                combo.setEnabled(False);assert not combo.isEnabled();combo.setEnabled(True)
            editable.setEditText('A local destination');assert editable.currentText()=='A local destination'
            with patch('kinetic_cut.updates.check',return_value=None),patch('kinetic_cut.tts_availability.probe_service',return_value=Availability(False,'Diagnostic offline mode')):
                about=AboutDialog(window);voice=TTSDialogueDialog(window,initial_text='Dropdown appearance test.')
                voice._audio_output.setVolume(0)
                for name,dialog in [('about',about),('voice',voice)]:
                    dialog.resize(max(width,dialog.minimumWidth()),dialog.height());dialog.show();QTest.qWait(60)
                    dialog.grab().save(str(output/f'{theme}-{name}-{width}.png'));dialog.close();dialog.deleteLater()
            form.close();form.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
    window.close()
    for _ in range(100):
        app.processEvents()
        if not window._workers:break
        QTest.qWait(20)
    assert not window._workers
    report=dict(passed=True,private_desktop=os.environ.get('KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP')=='1',owner_data_used=False,checks=checks,popup_input=True,editable_input=True)
    (output/'report.json').write_text(json.dumps(report,indent=2));return 0
