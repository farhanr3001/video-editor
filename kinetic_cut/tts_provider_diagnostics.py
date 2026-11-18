"""Isolated real free-service workflow and native on-open availability checks."""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch


def run(output_dir):
    output=Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home')
    from PySide6.QtCore import QEventLoop,QTimer,QCoreApplication,QEvent,QPoint,Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication,QWidget,QMessageBox
    from PySide6.QtMultimedia import QMediaPlayer
    from .theme_widgets import apply_application_theme
    from .tts_dialog import TTSDialog
    from .tts_dialogue_dialog import TTSDialogueDialog
    from .dialog_jobs import active_dialog_threads,cancel_dialog_threads,wait_dialog_threads
    from . import tts,tts_availability as health
    from .icons import resource_path
    from .process import run as process_run
    import edge_tts
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    owner=QWidget();owner.settings={'ffmpeg':str(resource_path('assets','tools','ffmpeg.exe'))}
    # Source checkout may keep the encoder only in the staged public assets.
    if not Path(owner.settings['ffmpeg']).is_file():
        owner.settings['ffmpeg']=str(Path.cwd()/'build/distribution-stage/KineticCut/_internal/assets/tools/ffmpeg.exe')
    ffmpeg=owner.settings['ffmpeg'];assert Path(ffmpeg).is_file()
    probe=str(Path(ffmpeg).with_name('ffprobe.exe'))
    report=dict(frozen=bool(getattr(sys,'frozen',False)),platform=app.platformName(),
        client=edge_tts.__version__,scope='Fixed test phrases, isolated home; no paid provider or owner data',cases=[])
    errors=[]
    warning=patch.object(QMessageBox,'warning',lambda *args:errors.append(str(args[-1])))
    critical=patch.object(QMessageBox,'critical',lambda *args:errors.append(str(args[-1])))
    warning.start();critical.start()

    def settle(condition,timeout=30):
        deadline=time.monotonic()+timeout;loop=QEventLoop();timer=QTimer();timer.setInterval(10)
        timer.timeout.connect(lambda:loop.quit() if condition() or time.monotonic()>deadline else None)
        timer.start();loop.exec();timer.stop()
        assert condition(),'Timed out waiting for speech workflow'

    def audio(path):
        response=process_run([probe,'-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,check=True)
        duration=float(json.loads(response.stdout)['format']['duration']);assert duration>0
        process_run([ffmpeg,'-v','error','-i',str(path),'-f','null','-'],capture_output=True,check=True)
        return dict(bytes=Path(path).stat().st_size,duration=duration)

    try:
        assert tuple(edge_tts.__version_info__[:3])>=(7,3,1)
        # Same source/stage/install suite: catalog + actual synthesis, all curated
        # voices, nondefault delivery and explicit multi-batch concatenation.
        availability=health.probe_service();assert availability.available,availability.message
        for i,(name,voice) in enumerate(tts.VOICES):
            if voice.startswith('offline:'):continue  # Separate optional-runtime diagnostic; no implicit model download.
            begin=time.monotonic()
            path=tts.synthesize_speech('Hello. This is a voice connection test.',voice=voice,
                rate_percent=15 if i==2 else 0,pitch_hz=-3 if i==2 else 0,
                output_path=output/f'voice-{i}.mp3',ffmpeg_bin=ffmpeg)
            report['cases'].append(dict(case='real voice',voice=voice,seconds=time.monotonic()-begin,**audio(path)))
        for i in range(8):
            path=tts.synthesize_speech('hello guys',voice=tts.DEFAULT_VOICE,
                output_path=output/f'short-adam-{i}.mp3',ffmpeg_bin=ffmpeg)
            report['cases'].append(dict(case='reported short Adam phrase',**audio(path)))
        script='This is a sentence for checking dialogue batches and audio assembly. '*6
        assert len(tts.split_script_into_batches(script,max_chars=350))>1
        path=tts.synthesize_dialogue_batches(script,
            voice='en-US-ChristopherNeural',output_path=output/'batch.mp3',ffmpeg_bin=ffmpeg)
        report['cases'].append(dict(case='real multi-batch',**audio(path)))
        for kind in (TTSDialogueDialog,TTSDialog):
            dialog=kind(owner,initial_text='Hello. This is a dialogue test.');dialog._audio_output.setVolume(0)
            generated=[];dialog.speechGenerated.connect(generated.append);dialog.show()
            settle(lambda:not dialog.voice_availability.checking)
            assert dialog.voice_availability.allowed(),dialog.voice_availability.label.text()
            dialog.preview_btn.click();settle(lambda:dialog._preview_worker is None)
            assert not errors,errors
            settle(lambda:dialog._preview_player.playbackState()==QMediaPlayer.PlayingState)
            dialog._cancel_preview();dialog.generate_btn.click();settle(lambda:bool(generated) or bool(errors))
            assert not errors,errors
            report['cases'].append(dict(case='real UI preview and generate',dialog=kind.__name__,**audio(generated[0]['audio_path'])))
            dialog.close();dialog.deleteLater();app.processEvents()
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            for kind in (TTSDialogueDialog,TTSDialog):
                for size in ((580,700),(470,520)):
                    with patch.object(health,'probe_service',return_value=health.Availability(False,
                            'The online voice service rejected the connection (HTTP 403). Try again later and check for a Kinetic Cut update if this continues.')) as fixture:
                        dialog=kind(owner,initial_text='Keep this script while checking voices.')
                        dialog.resize(*size);dialog.show();settle(lambda:not dialog.voice_availability.checking)
                        assert dialog.height()<=size[1],'Compact speech window grew beyond requested height'
                        assert not dialog.generate_btn.isEnabled() and dialog.cancel_btn.isEnabled()
                        assert dialog.voice_availability.retry.isVisible()
                        app.processEvents()
                        name=f'{theme}-{kind.__name__}-{size[0]}'
                        dialog.grab().save(str(output/(name+'.png')))
                        # Native list geometry, including when all rows are
                        # temporarily disabled. Keep Qt's screen-edge fallback.
                        for state in ('unavailable','ready'):
                            if state=='ready':
                                fixture.return_value=health.Availability(True)
                                dialog.voice_availability.retry.click();settle(lambda:not dialog.voice_availability.checking)
                            combo=dialog.voice_combo
                            QTest.mouseClick(combo,Qt.LeftButton,pos=combo.rect().center())
                            popup=combo.view().window();settle(popup.isVisible)
                            origin=combo.mapToGlobal(QPoint(0,combo.height()))
                            screen=combo.screen().availableGeometry()
                            if origin.y()+popup.height()<=screen.bottom()+1:
                                assert popup.geometry().top()>=origin.y()-1,'Voice popup covers the control instead of opening below'
                            popup.grab().save(str(output/(name+'-'+state+'-popup.png')))
                            report['cases'].append(dict(case='voice popup',name=name,state=state,
                                control_bottom=origin.y(),popup_top=popup.geometry().top(),height=popup.height()))
                            combo.hidePopup();app.processEvents()
                        # Footer stays reachable even in compact windows; editable
                        # dialogue content can scroll independently above it.
                        assert dialog.rect().contains(dialog.generate_btn.mapTo(dialog,dialog.generate_btn.rect().bottomRight()))
                        assert dialog.generate_btn.isEnabled()
                        assert dialog.voice_combo.currentData()==tts.DEFAULT_VOICE
                        report['cases'].append(dict(case='theme/compact failure and retry',name=name,
                            actual_size=[dialog.width(),dialog.height()]))
                        dialog.close();dialog.deleteLater();app.processEvents()
        settle(lambda:not active_dialog_threads())
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        report['passed']=True
    except Exception as error:
        import traceback
        report.update(passed=False,error=repr(error),traceback=traceback.format_exc())
    finally:
        warning.stop();critical.stop()
        for widget in app.topLevelWidgets():
            if isinstance(widget,(TTSDialog,TTSDialogueDialog)):widget.close()
        cancel_dialog_threads();report['threads_drained']=wait_dialog_threads()
        owner.close();app.processEvents()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report.get('passed') and report['threads_drained'] else 1
