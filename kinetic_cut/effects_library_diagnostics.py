"""Opt-in native/package acceptance for the effects library; disposable profile."""


def run(output):
    import os
    if os.environ.get("KINETIC_FIXED_INSPECTOR_DIAGNOSTIC"):return _fixed_inspector(output)
    if os.environ.get("KINETIC_FREEZE_PHASE1_DIAGNOSTIC"):
        from .freeze_interaction_diagnostics import run as freeze_run
        return freeze_run(output)
    if os.environ.get("KINETIC_EFFECTS_DRAG_DIAGNOSTIC"):
        from .effects_interaction_diagnostics import run as interaction_run
        return interaction_run(output)
    import json, os, sys, traceback
    from pathlib import Path
    out = Path(output).resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(out/'home')
    os.environ['QT_QPA_PLATFORM'] = 'windows' if os.name == 'nt' else 'offscreen'
    from PySide6.QtCore import Qt, QTimer, QEventLoop, QThreadPool, QEvent, QPoint, QRect, QObject
    from PySide6.QtGui import QPixmap, QPainter
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
    from .ui import MainWindow
    from . import effects_library as L
    from .theme import get_active_theme_palette
    from .config import load_settings
    app = QApplication([]); app.setStyle('Fusion'); app.setProperty('kineticTestDiscardUnsaved', True)
    app.setQuitOnLastWindowClosed(False)
    report = dict(passed=False, frozen=bool(getattr(sys, 'frozen', False)), themes=[], checks=[])
    window = host = None
    def wait(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()
    def check(name, condition):
        report['checks'].append(dict(name=name, passed=bool(condition)))
        assert condition, name
    def capture(name):
        # QWidget.grab omits native GPU children. Capture those real surfaces
        # independently and place them at their actual widget coordinates.
        picture=window.grab().toImage(); painter=QPainter(picture)
        try:
            for label, surface in (('timeline',window.timeline.gpu),('preview',window.preview.gpu)):
                if surface is None or surface.closed: continue
                pixels=surface.view.grabWindow()
                if pixels.isNull(): continue
                painter.drawImage(QRect(surface.container.mapTo(window,QPoint()),surface.container.size()),pixels)
                pixels.save(str(out/f'{name}-{label}-surface.png'))
        finally: painter.end()
        picture.save(str(out/f'{name}.png'))
    try:
        window = MainWindow(); window.show(); window.autosave_timer.stop()
        from dataclasses import asdict
        from .model import Project, ProjectSettings, MediaItem, TimelineItem, Caption
        import wave, math, struct
        sound=out/'soft-cue.wav'
        with wave.open(str(sound),'wb') as stream:
            stream.setparams((1,2,16000,0,'NONE','not compressed'))
            stream.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(i*2*math.pi*220/16000)*(.5+.5*math.sin(i*2*math.pi/16000)))) for i in range(48000)))
        samples=[MediaItem('lake',str(L.asset_directory()/'samples/lake.jpg'),'image','Lake.jpg',6,960,540),
                 MediaItem('camera',str(L.asset_directory()/'samples/camera.jpg'),'image','Camera.jpg',6,960,540),
                 MediaItem('sound',str(sound),'audio','Soft cue.wav',3,has_audio=True)]
        fixture=Project(name='Library layout check',settings=ProjectSettings(width=1920,height=1080),media=samples,
                        timeline=[TimelineItem('sample-clip','lake','video_1',0,6)],
                        captions=[Caption('sample-caption',1,3,'A clear view')])
        window.set_project(fixture); window.timeline.set_zoom(70); window.seek(2); wait(600)
        import copy
        video_path=L.asset_directory()/'samples/moving-object.kcpreview'
        video_project=copy.deepcopy(fixture)
        video_project.media.append(MediaItem('video',str(video_path),'video','Moving sample',14,960,540,30))
        video_project.timeline=[TimelineItem('sample-video','video','video_1',0,6),TimelineItem('sample-audio','sound','audio_1',0,3)]
        window.monitor_control.set_level(0); window.set_project(video_project); window.seek(1.2)
        window.toggle_play(); wait(850); window.toggle_play(); wait(200)
        video_diag=window.preview.gpu.diagnostics(); report['video_playback']=video_diag
        check('Normal video and caption playback advances',video_project.playhead>1.2)
        check('Video decoder produces preview frames',video_diag.get('gpu_source_frames',0)+video_diag.get('cpu_source_frames',0)>0)
        check('Audio decoder remains active',any(sink is None for _,_,sink in window.transport.decoders.values()))
        window.preview.select_caption('sample-caption'); wait(100)
        check('Caption selection keeps video visible',window.preview.gpu.container.isVisible())
        window.set_project(fixture); window.monitor_control.set_level(100); window.seek(2); wait(300)
        browser = window.effects_panel
        check('Only Media and Effects primary tabs', list(window.left_panels.buttons) == ['Media','Effects'])
        check('Commands share library header', all(b.parentWidget() is window.left_panels.header for b in window.edit_actions))
        check('Inspector follows assistant in menu header', window.header_actions_layout.itemAt(0).widget() is window.assistant_button and window.header_actions_layout.itemAt(1).widget() is window.inspector_toggle)
        check('No separate top toolbar', window.center_split.mapTo(window.centralWidget(),QPoint()).y()==0)
        check('Native light tab bases disabled', not window.media_panel.source_tabs.drawBase() and not window.inspector.tabs.tabBar().drawBase())
        class ResizeEvents(QObject):
            count=0
            def eventFilter(self,obj,event):
                if event.type()==QEvent.Resize:self.count+=1
                return False
        resize_events=ResizeEvents(); browser.list.viewport().installEventFilter(resize_events)
        report['resize_settling']=[]
        report['workspace'] = []
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            window.apply_theme(theme,save=False)
            check(theme+' timeline uses the selected palette',window.timeline._palette()['timeline_track_bg']==get_active_theme_palette(theme)['timeline_track_bg'])
            for width, height in ((1480, 900), (1100, 700)):
                window.resize(width, height); window.left_panels.select('Effects')
                wait(120)
                timeline = window.timeline.parentWidget()
                check(f'{theme} {width} full-width timeline', timeline.width() == window.center_split.width())
                def bottom(widget): return widget.mapToGlobal(QPoint(0, widget.height())).y()
                check(f'{theme} {width} aligned tab edges',
                      all(bottom(button) == bottom(window.viewer_header) == bottom(window.inspector.tabs.tabBar())
                          for button in window.left_panels.buttons.values()))
                monitor=window.monitor_control
                if width==1100:
                    monitor.set_level(63); was_muted=monitor.muted; monitor.button.click(); wait(60)
                    check(theme+' compact volume opens without muting',monitor._menu.isVisible() and monitor.muted==was_muted and monitor.popup_slider.orientation()==Qt.Vertical)
                    monitor._menu.grab().save(str(out/f'monitor-popup-{theme}.png'))
                    monitor.mute_button.click(); check(theme+' compact mute is separate',monitor.muted!=was_muted)
                    monitor.mute_button.click(); monitor.popup_slider.setValue(43)
                    check(theme+' popup adjusts monitor volume',monitor.level==43 and window.transport.monitor_gain==.43)
                    monitor._menu.close(); monitor.set_level(100)
                else:
                    right=monitor.slider.mapTo(window,QPoint(monitor.slider.width(),0)).x()
                    check(theme+' volume has edge clearance',not monitor.slider.isHidden() and window.width()-right>=14)
                capture(f'workspace-{theme}-{width}x{height}')
                report['workspace'].append(dict(theme=theme, size=[width,height], library_width=window.left_stack.width(), timeline_width=timeline.width()))
            window.resize(1480,900)
            for category_name in ('Texture & Retro','Time & Speed'):
                browser.categories.setCurrentItem(browser.categories.findItems(category_name,Qt.MatchExactly)[0])
                for upper_height in (350,450):
                    window.center_split.setSizes([upper_height,800-upper_height])
                    for library_width in (610,560,520,480,440,400,380):
                        window.workspace_split.setSizes([library_width,1480-library_width]); wait(25)
                    wait(170); resize_events.count=0; wait(250)
                    report['resize_settling'].append(dict(theme=theme,category=category_name,upper_height=upper_height,idle_resizes=resize_events.count))
                    check(f'{theme} {category_name} {upper_height} resize settles',resize_events.count==0 and not browser.layout_timer.isActive())
            window.workspace_split.setSizes([520,960]); window.center_split.setSizes([530,300])
        browser.list.viewport().removeEventFilter(resize_events)
        report['timeline_native']=window.timeline.gpu.diagnostics()
        check('Timeline native renderer contains the sample media and caption',report['timeline_native']['visible_nodes']>=2 and report['timeline_native']['scene_graph_frames']>0)
        window.resize(1480,900); window.left_panels.select('Media')
        window.workspace_split.setSizes([465,1015])
        panel=window.media_panel
        panel.navigation_split.parentWidget().setSizes([135,326])
        # Enough disposable items to prove wrapping, including folder cards.
        gallery_samples=[copy.deepcopy(samples[n%len(samples)]) for n in range(9)]
        for n,media in enumerate(gallery_samples):media.id='gallery'+str(n)
        fixture.media=gallery_samples; panel.refresh()
        panel.power.data={'folders':['Master','Master/References','Master/Sounds'],
                          'media':[{'folder':'Master','media':asdict(media)} for media in gallery_samples]}
        panel.rebuild_tree(); report['gallery_density']=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            window.apply_theme(theme,save=False)
            for source in (0,1):
                panel.source_tabs.setCurrentIndex(source); panel.refresh(); wait(350)
                rects=[panel.grid.visualItemRect(panel.grid.item(n)) for n in range(4)]
                columns=sum(r.top()==rects[0].top() for r in rects)
                source_name='media-pool' if source==0 else 'power-bins'
                report['gallery_density'].append(dict(theme=theme,source=source_name,viewport=panel.grid.viewport().width(),columns=columns,cell=[panel.grid.gridSize().width(),panel.grid.gridSize().height()]))
                check(theme+' '+source_name+' fits three fixed columns',columns==3 and rects[3].top()>rects[0].top() and panel.grid.gridSize().width()==98)
                panel.grab().save(str(out/f'gallery-{source_name}-{theme}.png'))
                if theme=='default':capture('workspace-'+source_name)
        check('Power Bins is a Media subtab', window.media_panel.folder == 'Master' and window.media_panel.tree.isVisible())
        window.media_panel.source_tabs.setCurrentIndex(0)
        window.left_panels.select('Effects')
        host = QWidget(); layout = QVBoxLayout(host); browser.setParent(host); layout.addWidget(browser)
        host.show(); window.hide()
        def category(name):
            browser.categories.setCurrentItem(browser.categories.findItems(name, Qt.MatchExactly)[0]); wait(60)
        category('All Effects')
        identities = [browser.list.item(i).data(Qt.UserRole) for i in range(browser.list.count())]
        check('Complete catalogue and identities', identities == list(L.ALL_NAMES))
        check('Every bundled thumbnail decodes', all(not QPixmap(str(L.asset_path(entry, 'thumbnail'))).isNull() for entry in browser.assets.values()))
        report['preview_policy_mismatches'] = [name for name, entry in browser.assets.items()
                                               if bool(entry.get('preview')) != (name in L.ANIMATED_NAMES)]
        check('Preview policy matches all entries', not report['preview_policy_mismatches'])
        category('Visual FX'); check('First subsection is All', browser.subsections.currentData() == '')
        browser.subsections.setCurrentText('Zooms'); category('Video Transitions'); browser.subsections.setCurrentText('Dissolve')
        category('Visual FX'); check('Per-category subsection memory', browser.subsections.currentText() == 'Zooms')
        browser.search.setText('Wave Distortion'); check('Global search', browser.list.count() == 1 and browser.list.item(0).text() == 'Wave Distortion')
        browser.search.clear()
        for name in L.ALL_NAMES[:15]: browser.remember_used(name)
        browser.remember_used(L.ALL_NAMES[9]); check('Ten unique recent effects', len(browser.recent) == 10 and len(set(browser.recent)) == 10 and browser.recent[0] == L.ALL_NAMES[9])
        browser.toggle_favourite('Punch Zoom'); category(L.FAVOURITES)
        check('Favourite navigation', any(browser.list.item(i).text() == 'Punch Zoom' for i in range(browser.list.count())))
        category('Titles')
        for name in ('Text', 'Headline'):
            browser.list.setCurrentItem(browser.list.findItems(name, Qt.MatchExactly)[0])
            check(name+' is static', browser.preview_button.isHidden())
        category('Colour'); check('Static colour has no Play', browser.preview_button.isHidden())
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            window.apply_theme(theme,save=False)
            for width, height in ((520, 660), (430, 340), (345, 300)):
                host.resize(width, height); category('Visual FX'); browser.subsections.setCurrentIndex(0)
                browser.details_collapsed = height < 400; browser._apply_details_state()
                wait(100); browser.layout_items(); wait(80)
                browser.grab().save(str(out/f'{theme}-{width}x{height}.png'))
                report['themes'].append(dict(theme=theme, size=[width,height], gallery=[browser.list.viewport().width(),browser.list.viewport().height()]))
        window.apply_theme('default',save=False); host.resize(520,660); category('Visual FX'); browser.subsections.setCurrentText('Zooms'); wait(120)
        frames = []
        browser.preview()
        check('On-demand player created', browser.player is not None)
        browser.video.videoSink().videoFrameChanged.connect(lambda frame: frames.append(dict(valid=frame.isValid(), handle=str(frame.handleType()))))
        wait(1500)
        report['video_frames'] = len(frames)
        report['video_handles'] = sorted({f['handle'] for f in frames})
        report['video_error'] = browser.player.errorString()
        report['video_state'] = str(browser.player.playbackState())
        report['hardware_decoded_preview'] = any(f['valid'] and 'RhiTextureHandle' in f['handle'] for f in frames)
        # Qt may choose software decoding for these tiny H.264 samples. A CPU
        # frame is still presented by QVideoWidget's native RHI output. Record
        # the real decoder evidence rather than requiring a hardware decoder.
        check('Native preview delivers video frames', any(f['valid'] for f in frames) and not browser.player.errorString())
        browser.stop_preview(); wait(100)
        check('Preview stops and releases source', browser.player.source().isEmpty() and not browser.video.isVisible())
        browser.details_collapsed = False; browser.toggle_details(); category('Titles')
        check('Details remain compact after selection', browser.details_collapsed and browser.description.isHidden())
        window.apply_effect('Text'); check('Applied effect enters recent history', browser.recent[0] == 'Text' and len(browser.recent) <= 10)
        saved = load_settings()
        check('Preferences persisted', saved['effects_details_collapsed'] is True and saved['effects_category'] == 'Titles' and saved['effects_subsections']['Visual FX'] == 'Zooms')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if host is not None: host.close()
        if window is not None: window.close()
        report['workers_finished'] = QThreadPool.globalInstance().waitForDone(10000)
        wait(250)
        report['passed'] = report['passed'] and report['workers_finished']
        (out/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('themes','checks')}), flush=True)
    return 0 if report['passed'] else 1


def _fixed_inspector(output):
    """Bounded native geometry check; never loads an owner profile/project."""
    import json,os,sys,traceback
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QPoint,QTimer,QEventLoop,QThreadPool
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .ui import MainWindow
    from .workspace import set_page
    app=QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False)
    app.setProperty('kineticTestDiscardUnsaved',True)
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),checks=[],sizes=[]);window=None
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def check(name,value):
        report['checks'].append(dict(name=name,passed=bool(value)));assert value,name
    try:
        window=MainWindow();window.show();window.autosave_timer.stop();wait(150)
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            window.apply_theme(theme,save=False)
            for width,height in ((1100,700),(1480,900),(1920,1080)):
                window.resize(width,height);wait(70)
                for left in (360,520):
                    window.workspace_split.setSizes([left,width-left]);wait(35)
                    handle=window.viewer_split.handle(1)
                    check(f'{theme} {width} divider disabled',not handle.isEnabled())
                    check(f'{theme} {width} original inspector width',window.right_stack.width()==350)
                    check(f'{theme} {width} left divider adjustable',window.workspace_split.handle(1).isEnabled())
                    before=window.viewer_split.sizes()
                    QTest.mousePress(handle,Qt.LeftButton,pos=QPoint(0,50))
                    QTest.mouseMove(handle,QPoint(-120,50));QTest.mouseRelease(handle,Qt.LeftButton,pos=QPoint(-120,50));wait(35)
                    check(f'{theme} {width} drag leaves divider fixed',window.viewer_split.sizes()==before)
                window.inspector_toggle.setChecked(False);wait(25)
                check(f'{theme} {width} inspector hides',not window.right_stack.isVisible())
                window.inspector_toggle.setChecked(True);wait(25)
                check(f'{theme} {width} inspector restores width',window.right_stack.isVisible() and window.right_stack.width()==350)
                for page in (1,0):
                    set_page(window,page);wait(25)
                    check(f'{theme} {width} page {page} fixed sidebar',window.right_stack.width()==350 and not handle.isEnabled())
                report['sizes'].append(dict(theme=theme,window=[width,height],inspector=window.right_stack.width(),preview=window.preview.parentWidget().width()))
                window.grab().save(str(out/f'inspector-{theme}-{width}.png'))
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if window is not None:window.close()
        report['workers_finished']=QThreadPool.globalInstance().waitForDone(10000);wait(100)
        report['passed']=report['passed'] and report['workers_finished']
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(passed=report['passed'],error=report.get('error'),checks=len(report['checks']))),flush=True)
    return 0 if report['passed'] else 1
