"""Disposable native object-tracking fixtures, controls and decoded output checks."""
from pathlib import Path


def make_fixture(directory, *, fps=30, duration=2.8, width=320, height=180, occlusion=True):
    """Author a small original textured target; never read or mutate owner media."""
    import math
    import av
    import numpy as np
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'moving-target.mp4'
    boxes = []
    with av.open(str(target), 'w') as movie:
        stream = movie.add_stream('libx264', rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
        stream.options = {'crf': '12', 'preset': 'veryfast'}
        for n in range(round(duration * fps)):
            t = n / fps
            image = np.zeros((height, width, 3), dtype=np.uint8)
            image[:] = (30, 37, 43)
            # A distinct stationary distractor makes the test more than motion
            # against a uniform background.
            yy, xx = np.mgrid[:height, :width]
            image[:, :, 0] += ((xx // 23 + yy // 17) % 2).astype(np.uint8) * 5
            image[14:40, width-54:width-12] = (40, 112, 210)
            image[19:35:5, width-50:width-16] = (100, 183, 241)
            size = round(36 + 7 * math.sin(t * 1.25))
            x = round(28 + (width - 105) * t / duration)
            y = round(height * .45 + 11 * math.sin(t * 1.7))
            boxes.append([round(x / width, 6), round(y / height, 6),
                          round(size / width, 6), round(size / height, 6)])
            py, px = np.mgrid[:size, :size]
            # Scale the texture with the target. Identity survives size changes.
            check = ((px * 6 // size + py * 6 // size) % 2).astype(bool)
            patch = np.zeros((size, size, 3), np.uint8)
            patch[check] = (250, 197, 55)
            patch[~check] = (138, 45, 71)
            patch[size//3:size//3+3, 4:-4] = (242, 241, 222)
            patch[4:-4, size//2:size//2+3] = (20, 28, 33)
            image[y:y+size, x:x+size] = patch
            if occlusion and 1.1 <= t < 1.4:
                image[y-4:y+size+4, x-4:x+size+4] = (30, 37, 43)
            frame = av.VideoFrame.from_ndarray(image, format='rgb24')
            for packet in stream.encode(frame):
                movie.mux(packet)
        for packet in stream.encode():
            movie.mux(packet)
    return target, boxes


def image_array(image):
    import numpy as np
    from PySide6.QtGui import QImage
    image = image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.constBits(), np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)[:, :image.width()].copy()


def verify_tracking_first_open(window,app,output,source):
    """Actual editor Add Effect/exec/reopen, including a delayed GUI and real60fps source."""
    import copy,time,os
    from PySide6.QtCore import QTimer,QPoint,QEventLoop,Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPainter
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem
    from .media import probe
    from .tracking_dialog import TrackingDialog
    records=[]
    media=probe(source,window.settings.get('ffprobe','ffprobe'))
    duration=min(6.5055555555555555,media.duration)
    proxy=os.environ.get('KINETIC_TRACKING_TEST_PROXY','')
    vfr=os.environ.get('KINETIC_TRACKING_TEST_VFR','')
    variants=[('original60-first',media,None,0.),('original60-reopen',media,None,2.15)]
    if proxy:variants.append(('proxy60',media,proxy,0.))
    if vfr:variants.append(('variable-rate',probe(vfr,window.settings.get('ffprobe','ffprobe')),None,0.))
    original_poll=TrackingDialog.poll
    def delayed_poll(dialog):
        if dialog.player and not dialog.playing and dialog.player.playbackState().name=='PlayingState':time.sleep(.09)
        original_poll(dialog)
    TrackingDialog.poll=delayed_poll
    try:
        for name,source_media,preview_path,opening in variants:
            current=copy.deepcopy(source_media)
            item=TimelineItem('first-open-'+name,current.id,'video_1',0,min(duration,current.duration))
            project=Project(name='Disposable tracking first open '+name,media=[current],timeline=[item],playhead=opening)
            project.settings.fps=60
            window.set_project(project);window.select_item(item.id)
            if preview_path:window.proxies[current.id]=preview_path
            before=copy.deepcopy(item.effects);errors=[];phase=0;started=time.monotonic();record=dict(name=name,frames=[],fresh_effect=True,actual_add_effect=True)
            def drive():
                nonlocal phase
                dialog=app.activeModalWidget()
                if not isinstance(dialog,TrackingDialog):return
                try:
                    assert dialog.surface.container.geometry()==dialog.view.rect(),('geometry',dialog.surface.container.geometry(),dialog.view.rect())
                    if time.monotonic()-started>8:raise AssertionError((name,'frame timeout',dialog.source_time(),dialog.sink.videoFrame().startTime(),dialog._seek_attempts))
                    if phase==5:
                        assert dialog.playing
                        dialog.pause_for_edit();record.update(passed=True,native_geometry=True,source_visible=True,box_preview=True,stepping=True,instant_play=True)
                        dialog.reject();return
                    if not dialog.settled_frame():return
                    frame=dialog.sink.videoFrame();target=round(dialog.frame_target()*1000000)
                    assert frame.isValid() and frame.startTime()<=target+1000 and frame.endTime()>target
                    record['frames'].append(dict(target=target,start=frame.startTime(),end=frame.endTime()))
                    if phase==0:
                        dialog.timeline.setValue(min(dialog.timeline.maximum(),129));phase=1;return
                    if phase==1:
                        rect=dialog.view.image_rect();a=QPoint(round(rect.x()+rect.width()*.2),round(rect.y()+rect.height()*.2));b=QPoint(round(rect.x()+rect.width()*.42),round(rect.y()+rect.height()*.65))
                        QTest.mousePress(dialog.surface.view,Qt.LeftButton,pos=a);QTest.mouseMove(dialog.surface.view,b);QTest.mouseRelease(dialog.surface.view,Qt.LeftButton,pos=b)
                        assert dialog.view.region and dialog.track_button.isEnabled()
                        dialog.mode.setCurrentText('Circle');phase=2;return
                    if phase==2:
                        gpu=dialog.surface.view.grabWindow()
                        assert image_array(gpu)[:,:,:3].std()>15,(name,'black/flat GPU pixels')
                        shot=dialog.grab();painter=QPainter(shot);painter.drawImage(dialog.view.mapTo(dialog,QPoint(0,0)),gpu);painter.end()
                        assert shot.save(str(output/('first-open-'+name+'.png')))
                        if preview_path:assert dialog._playback_source==preview_path
                        dialog.step(-1);phase=3;return
                    if phase==3:
                        dialog.step(1);phase=4;return
                    if phase==4:
                        dialog.timeline.setValue(min(dialog.timeline.maximum(),90));dialog.toggle_play();assert dialog.playing
                        phase=5;return
                    if phase==5:
                        dialog.pause_for_edit();record.update(passed=True,native_geometry=True,source_visible=True,box_preview=True,stepping=True,instant_play=True)
                        dialog.reject()
                except Exception as error:
                    errors.append(error);dialog.reject()
            driver=QTimer();driver.setInterval(60);driver.timeout.connect(drive);driver.start()
            try:window.apply_effect('Object Tracking')
            finally:driver.stop()
            if errors:raise errors[0]
            assert record.get('passed') and item.effects==before,(name,'Cancel changed clip or modal did not open')
            records.append(record)
            QApplication.processEvents()
    finally:TrackingDialog.poll=original_poll
    return records


def run(output):
    """Verify real source tracking, native three-theme UI and encoded pixels."""
    import copy
    import json
    import os
    import shutil
    import sys
    import threading
    import time
    import traceback
    import av
    import numpy as np
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    import faulthandler
    trace=(output/'stacks.log').open('w',encoding='utf-8')
    faulthandler.enable(trace)
    faulthandler.dump_traceback_later(20,repeat=True,file=trace)
    os.environ['KINETIC_GPU_PROCESS_TRACE']=str(output/'gpu-stacks.log')
    def phase(name):
        (output/'phase.txt').write_text(name,encoding='utf-8')
    phase('Starting')
    import tempfile
    os.environ['KINETIC_CUT_HOME'] = tempfile.mkdtemp(prefix='home-',dir=output)
    os.environ['QT_QPA_PLATFORM'] = 'windows' if os.name == 'nt' else 'offscreen'
    from PySide6.QtCore import Qt, QRectF, QPoint, QPointF, QEventLoop, QTimer, QThreadPool, QEvent
    from PySide6.QtGui import QImage, QColor, QPainter, QPainterPath
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtTest import QTest
    from .model import Project, TimelineItem, MediaItem, Crop, Transform
    from .object_tracking import analyze, sample, valid as analysis_valid
    from .tracking_effect import (MODES, default_effect, apply, export_error,
                                  valid as effect_valid, effective_crop)
    from .tracking_dialog import TrackingDialog
    from .tracking_ui import TrackingPanel
    from .exporter import export, PRESETS
    from .vocal_component import Cancelled
    from .ui import MainWindow
    from .caption_fonts import load_fonts
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    app.setQuitOnLastWindowClosed(False)
    load_fonts()
    report = dict(frozen=bool(getattr(sys, 'frozen', False)), themes=[], modes=[], parity=[])
    window = None

    def settle(milliseconds=80):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    try:
        source, boxes = make_fixture(output / 'fixture')
        media = MediaItem('tracking-source', str(source), 'video', 'Tracking test',
                          2.8, 320, 180, 30)
        clip = TimelineItem('tracking-item', media.id, 'video_1', 0, 2.8,
                            transform=Transform(.5, .5))
        analysis = analyze(media, clip, .7, boxes[21],
                           anchors=[dict(time=1.7, box=boxes[51])],
                           sample_fps=15, search_radius=.16, confidence_threshold=.62)
        losses = sum(point['status'] == 'lost' for point in analysis['frames'])
        assert losses > 0, 'The occluded object must not be reported as tracked.'
        assert sample(analysis, 1.2)['status'] == 'lost'
        errors = []
        for at in (.2, .7, 1.7, 2.5):
            point = sample(analysis, at)
            assert point['status'] != 'lost', (at, point)
            expected = boxes[round(at * 30)]
            error = max(abs(a-b) for a, b in zip(expected, point['box']))
            assert error < .04, (at, error, point)
            errors.append(error)
        report['tracking'] = dict(samples=len(analysis['frames']), lost_samples=losses,
                                  normalized_box_errors=errors,
                                  anchors=[.7, 1.7], source_seconds=2.8)
        with av.open(str(source)) as movie:
            source_rgb = [frame.to_ndarray(format='rgb24') for frame in movie.decode(video=0)]
        assert len(source_rgb) == 84

        stamp = QImage(64, 64, QImage.Format_RGBA8888)
        stamp.fill(Qt.transparent)
        painter = QPainter(stamp)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.moveTo(32, 2); path.lineTo(60, 56); path.lineTo(4, 56); path.closeSubpath()
        painter.fillPath(path, QColor('#ed47c4')); painter.end()
        stamp_path = output / 'marker.png'
        assert stamp.save(str(stamp_path))
        window = MainWindow()
        window.resize(1480, 920)
        window.show()
        window.autosave_timer.stop()

        def project_with(mode):
            item = copy.deepcopy(clip)
            if mode == 'Follow Crop':
                # A full-source viewport has no room to follow. Keep a visibly
                # tighter static viewport and let tracking move its source origin.
                item.crop = Crop(.2, .1, .45, .65)
            effect = default_effect(mode)
            effect.update(analysis=copy.deepcopy(analysis), color='#46e0ad',
                          padding=5., arrow_length=70., arrow_head=20.,
                          label='TRACKED', font_size=22., image=str(stamp_path))
            if mode == 'Censor Bar': effect['color'] = '#000000'
            item.effects = [effect]
            project = Project(name='Disposable object tracking check',
                              media=[copy.deepcopy(media)], timeline=[item])
            project.settings.width = 320
            project.settings.height = 180
            project.settings.fps = 30
            return project, item

        # Render through the exact viewer painter at output resolution using
        # actual decoded source images. This isolates effect parity from decoder
        # seek latency and display scaling; native dialogs are inspected below.
        def viewer_frame(project, item, at):
            from .keyframes import evaluated
            project.playhead = at
            view = window.preview
            view.project = project
            source_at = item.source_time(at)
            rgb = source_rgb[min(len(source_rgb)-1, max(0, round(source_at * 30)))]
            image = QImage(rgb.data, 320, 180, rgb.strides[0], QImage.Format_RGB888).copy()
            result = QImage(project.settings.width, project.settings.height, QImage.Format_RGBA8888)
            result.fill(QColor('black'))
            frame_rect = QRectF(0, 0, result.width(), result.height())
            current = evaluated(item, at-item.start)
            target = (frame_rect if current.role == 'background' else
                      view._layer_rect(current, image, frame_rect, current.role == 'facecam'))
            painter = QPainter(result)
            view._draw_layer_item(painter, current, image, target, frame_rect)
            painter.end()
            return result

        for mode in MODES:
            phase('Export '+mode)
            project, item = project_with(mode)
            window.preview.set_project(project)
            output_path = output / ('marker-' + mode.lower().replace(' ', '-') + '.mp4')
            export(project, str(output_path), PRESETS['TikTok · Fast'], False,
                   'CPU', export_audio=False)
            with av.open(str(output_path)) as movie:
                frames = list(movie.decode(video=0))
                assert str(movie.streams.video[0].average_rate) == '30'
            assert len(frames) == 84 and frames[0].width == 320 and frames[0].height == 180
            errors = []
            for number in (6, 21, 36, 51, 75):
                expected = viewer_frame(project, item, number / 30)
                decoded = frames[number].to_ndarray(format='rgb24')
                error = float(np.abs(image_array(expected)[:, :, :3].astype(float)-decoded).mean())
                assert error < 4., (mode, number, error)
                errors.append(error)
                if number == 51:
                    assert expected.save(str(output / ('viewer-' + mode.lower().replace(' ', '-') + '.png')))
                    exported = QImage(decoded.data, 320, 180, decoded.strides[0], QImage.Format_RGB888).copy()
                    assert exported.save(str(output / ('decoded-' + mode.lower().replace(' ', '-') + '.png')))
            if mode in ('Blur', 'Pixelate', 'Censor Bar'):
                assert int(frames[36].to_ndarray(format='rgb24').max()) < 8
            if mode == 'Follow Crop':
                first_crop = effective_crop(item, project.media[0], 0)
                last_crop = effective_crop(item, project.media[0], 2.7)
                assert abs(first_crop.x) < 1e-7
                assert abs(last_crop.x-(1-last_crop.width)) < 1e-7
                observed = [point for point in analysis['frames']
                            if point['time'] <= 1.2 and point['status'] != 'lost'][-1]
                held_crop = effective_crop(item, project.media[0], 1.2)
                assert held_crop == effective_crop(item, project.media[0], observed['time'])
                report['follow_crop_edges_and_hold'] = dict(
                    left=first_crop.x, right=last_crop.x,
                    held_source_time=observed['time'], viewport_size=[held_crop.width, held_crop.height])
                rgb = frames[51].to_ndarray(format='rgb24')
                target_mask = ((rgb[:, :, 0] > 95)
                               & ((rgb[:, :, 0].astype(int)-rgb[:, :, 1] > 30)
                                  | ((rgb[:, :, 1] > 100) & (rgb[:, :, 2] < 95))))
                y, x = np.where(target_mask)
                assert len(x) > 100
                assert abs((x.min()+x.max())/2-160) < 4
                assert abs((y.min()+y.max())/2-90) < 4
                report['follow_crop_center'] = [float((x.min()+x.max())/2), float((y.min()+y.max())/2)]
            report['modes'].append(dict(mode=mode, decoded_frames=len(frames), rgb_errors=errors))

        # A speed change, trim, crop and clip transform all sample source time.
        project, item = project_with('Circle')
        item.in_point = .2; item.speed = 2.; item.duration = 1.2
        item.crop = Crop(.15, .2, .75, .75)
        item.transform = Transform(.5, .5, .72, scale_y=.8, scale_linked=False,
                                   rotation=15., flip_horizontal=True)
        window.preview.set_project(project)
        target = output / 'trim-speed-crop-transform.mp4'
        export(project, str(target), PRESETS['TikTok · Fast'], False, 'CPU', export_audio=False)
        with av.open(str(target)) as movie: transformed = list(movie.decode(video=0))
        assert len(transformed) == 36
        for number in (0, 9, 21, 33):
            expected = viewer_frame(project, item, number/30)
            decoded = transformed[number].to_ndarray(format='rgb24')
            error = float(np.abs(image_array(expected)[:, :, :3].astype(float)-decoded).mean())
            assert error < 7., (number, error)
            report['parity'].append(dict(frame=number, source_time=item.source_time(number/30), rgb_error=error))
        report['trim_speed_crop_transform'] = True

        # The common short-form case: a cropped webcam-style lane in a portrait
        # project. The viewport holds through occlusion, corrects at the manual
        # anchor and reaches a source edge without sampling outside the video.
        project, item = project_with('Follow Crop')
        project.settings.width = 180; project.settings.height = 320
        item.role = 'facecam'
        item.transform = Transform(.5, .27, .8)
        window.preview.set_project(project)
        target = output / 'follow-crop-facecam.mp4'
        export(project, str(target), PRESETS['TikTok · Fast'], False, 'CPU', export_audio=False)
        with av.open(str(target)) as movie: following = list(movie.decode(video=0))
        assert len(following) == 84 and following[0].width == 180 and following[0].height == 320
        report['follow_crop_facecam'] = []
        for number in (0, 21, 36, 51, 81):
            expected = viewer_frame(project, item, number/30)
            decoded = following[number].to_ndarray(format='rgb24')
            error = float(np.abs(image_array(expected)[:, :, :3].astype(float)-decoded).mean())
            assert error < 5., (number, error)
            report['follow_crop_facecam'].append(dict(frame=number, source_time=item.source_time(number/30), rgb_error=error))
            if number == 51:
                target_mask = ((decoded[:, :, 0] > 95)
                               & ((decoded[:, :, 0].astype(int)-decoded[:, :, 1] > 30)
                                  | ((decoded[:, :, 1] > 100) & (decoded[:, :, 2] < 95))))
                y, x = np.where(target_mask)
                assert len(x) > 100
                assert abs((x.min()+x.max())/2-90) < 5
                assert abs((y.min()+y.max())/2-project.settings.height*.27) < 5
                assert expected.save(str(output/'viewer-follow-crop-facecam.png'))

        project, item = project_with('Follow Crop')
        item.in_point = .2; item.speed = 2.; item.duration = 1.2
        window.preview.set_project(project)
        target = output / 'follow-crop-trim-speed.mp4'
        export(project, str(target), PRESETS['TikTok · Fast'], False, 'CPU', export_audio=False)
        with av.open(str(target)) as movie: following = list(movie.decode(video=0))
        assert len(following) == 36
        report['follow_crop_trim_speed'] = []
        for number in (0, 9, 21, 33):
            expected = viewer_frame(project, item, number/30)
            decoded = following[number].to_ndarray(format='rgb24')
            error = float(np.abs(image_array(expected)[:, :, :3].astype(float)-decoded).mean())
            assert error < 5., (number, error)
            report['follow_crop_trim_speed'].append(dict(frame=number, source_time=item.source_time(number/30), rgb_error=error))

        # Loss policies remain explicit; an invalid or unreviewed censor must
        # never quietly export uncensored source pixels.
        project, item = project_with('Censor Bar')
        effect = item.effects[0]
        effect['loss_policy'] = 'Hide'
        assert export_error(effect, project.media[0], item)
        image = QImage(source_rgb[36].data, 320, 180, source_rgb[36].strides[0], QImage.Format_RGB888).copy()
        assert image_array(apply(image, item, project.media[0], 1.2))[:, :, :3].max() == 0
        effect['loss_reviewed'] = True
        assert not export_error(effect, project.media[0], item)
        report['censor_review_guard'] = True
        effect['loss_policy'] = 'Full frame'
        sentinel = output / 'cancel-preserves.mp4'
        sentinel.write_bytes(b'previous completed destination')
        cancel = threading.Event(); cancel.set()
        try:
            export(project, str(sentinel), PRESETS['TikTok · Fast'], False, 'CPU',
                   cancel=cancel, export_audio=False)
            raise AssertionError('Cancelled export unexpectedly completed.')
        except (Cancelled, RuntimeError, ValueError):
            pass
        assert sentinel.read_bytes() == b'previous completed destination'
        report['cancel_preserves_destination'] = True

        # Preserve trajectory and custom marker paths in an ordinary copied
        # portable project. This uses copy2, matching normal timestamp-preserving
        # Explorer transfer; a modified source remains a deliberate invalidation.
        portable = output / 'portable'
        portable.mkdir(exist_ok=True)
        copied_source = portable / 'source.mp4'
        copied_stamp = portable / 'marker.png'
        shutil.copy2(source, copied_source); shutil.copy2(stamp_path, copied_stamp)
        project, item = project_with('Image')
        project.media[0].path = str(copied_source)
        item.effects[0]['image'] = str(copied_stamp)
        project.portable_media = True
        project.save(portable / 'project.kcut')
        moved = output / 'transferred'
        if moved.exists():
            # Only our diagnostic copy is removed; never a computed owner path.
            assert moved.parent == output and moved.name == 'transferred' and not moved.is_symlink()
            shutil.rmtree(moved)
        shutil.copytree(portable, moved)
        loaded = Project.load(moved / 'project.kcut')
        loaded_effect = loaded.timeline[0].effects[0]
        assert effect_valid(loaded_effect, loaded.media[0], loaded.timeline[0])
        assert Path(loaded_effect['image']).parent == moved
        assert analysis_valid(loaded_effect['analysis'], loaded.media[0], loaded.timeline[0])
        report['portable_source_and_marker'] = True

        # Native, themed workflow: existing analysis, original/effect toggle,
        # source crop guides, correction controls and actual inspector settings.
        project, item = project_with('Circle')
        project.playhead = .7
        window.set_project(project)
        window.select_item(item.id)
        window.inspector.tabs.setCurrentIndex(2)
        window.inspector.effect_picker.setCurrentIndex(0)
        window.preview.set_transform_controls_visible(False)
        phase('Unanalysed marker source visibility and stable decoder')
        fresh=TrackingDialog(window,project.media[0],item)
        fresh.show()
        for _ in range(40):
            settle(100)
            if fresh.settled_frame():break
        assert fresh.settled_frame(),fresh.info.text()
        for mode in MODES:
            fresh.mode.setCurrentText(mode);fresh.refresh_preview();settle(60)
            assert not fresh.surface.root.property('showMarkers'),mode
            pixels=image_array(fresh.surface.view.grabWindow())
            assert pixels[:,:,:3].mean()>8,(mode,'unexpected black source')
        fresh.mode.setCurrentText('Circle')
        original_pixels=image_array(fresh.surface.view.grabWindow())
        rectangle=fresh.view.image_rect()
        x,y,w,h=boxes[21]
        start=QPoint(round(rectangle.x()+x*rectangle.width()),round(rectangle.y()+y*rectangle.height()))
        end=QPoint(round(rectangle.x()+(x+w)*rectangle.width()),round(rectangle.y()+(y+h)*rectangle.height()))
        workers_before=len(window._workers)
        QTest.mousePress(fresh.view,Qt.LeftButton,pos=start)
        QTest.mouseMove(fresh.view,end)
        QTest.mouseRelease(fresh.view,Qt.LeftButton,pos=end)
        settle(100)
        assert fresh.surface.root.property('showMarkers')
        assert fresh._published_markers and fresh._published_markers[0]['w']<.9
        marked_pixels=image_array(fresh.surface.view.grabWindow())
        assert np.count_nonzero(np.max(np.abs(marked_pixels.astype(int)-original_pixels.astype(int)),axis=2)>15)>100
        assert not fresh.effect.get('analysis') and len(window._workers)==workers_before
        fresh.add_anchor()
        assert len(fresh.timeline.keyframes)==1
        key=fresh.timeline.keyframe_position(fresh.timeline.keyframes[0]).toPoint()
        QTest.mouseClick(fresh.timeline,Qt.LeftButton,pos=key)
        assert fresh.anchor_list.selectionModel().selectedRows()
        menu=fresh.analysis_menu()
        next(action for action in menu.actions() if action.text()=='Remove selected frames').trigger()
        assert not fresh.anchors and not fresh.timeline.keyframes and fresh.view.region is None
        assert not fresh.effect.get('analysis')
        original_source=fresh._playback_source
        window.proxies[project.media[0].id]=str(output/'late-proxy-must-not-be-opened.mp4')
        fresh._busy=True
        fresh.poll()
        assert fresh._playback_source==original_source
        fresh.set_busy(False)
        window.proxies.pop(project.media[0].id,None)
        settle(150)
        gpu_shot=fresh.surface.view.grabWindow()
        shot=fresh.grab()
        painter=QPainter(shot)
        painter.drawImage(fresh.view.mapTo(fresh,QPoint(0,0)),gpu_shot)
        painter.end()
        assert shot.save(str(output/'guided-first-use.png'))
        fresh.reject();fresh.deleteLater();settle()
        report['unanalysed_all_modes_visible_and_decoder_stable']=True
        report['drawn_marker_preview_diamond_and_context_removal']=True
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            window.apply_theme(theme, save=False)
            dialog = TrackingDialog(window, project.media[0], item, item.effects[0])
            dialog.show()
            for _ in range(30):
                settle(100)
                if not dialog.raw.isNull() and dialog.settled_frame(): break
            if dialog.raw.isNull() or not dialog.settled_frame():
                frame=dialog.sink.videoFrame() if dialog.player else None
                report['monitor_failure']=dict(theme=theme,target=dialog.source_time(),
                    position=dialog.player.position() if dialog.player else None,
                    status=dialog.player.mediaStatus().name if dialog.player else None,
                    frame=(frame.startTime(),frame.endTime()) if frame and frame.isValid() else None)
            assert not dialog.raw.isNull() and dialog.settled_frame(), dialog.info.text()
            assert dialog.apply_button.isEnabled()
            width=dialog.view.width()
            draft_before=dialog.result_effect()
            dialog.marker_toggle.click();settle(100)
            assert dialog.marker_panel.isHidden() and dialog.view.width()>width
            assert image_array(dialog.surface.view.grabWindow())[:,:,:3].mean()>8
            dialog.marker_toggle.click();settle(100)
            assert not dialog.marker_panel.isHidden() and dialog.result_effect()==draft_before
            dialog.preview_expand.click();settle(100)
            assert not dialog.analysis_panel.isVisible() and dialog.view.width()>width
            assert image_array(dialog.surface.view.grabWindow())[:,:,:3].mean()>8
            QTest.keyClick(dialog,Qt.Key_Escape);settle(100)
            assert dialog.analysis_panel.isVisible() and not dialog.preview_expand.isChecked()
            assert dialog.result_effect()==draft_before and dialog.isVisible()
            dialog.marker_settings_card.toggle.click()
            assert dialog.marker_settings_card.body.isHidden()
            dialog.marker_settings_card.toggle.click()
            dialog.before.setChecked(False)
            for size in ((980,700),(1100,760),(1280,850),(1440,1000)):
                dialog.resize(*size); settle()
                for control in (dialog.track_button,dialog.anchor_list,dialog.anchor_button,dialog.remove_frame_button,dialog.clear_target_button,dialog.clear_button):
                    position=control.mapTo(dialog.analysis_panel,QPoint(0,0))
                    assert position.y()>=0 and position.y()+control.height()<=dialog.analysis_panel.height(),(theme,size,control.objectName(),'clipped analysis action')
                assert dialog.mode.count()==len(MODES)
                assert dialog.marker_toggle.parentWidget() is dialog.source_label.parentWidget()
                image_path = output / f'dialog-{theme}-{size[0]}.png'
                gpu_shot=dialog.surface.view.grabWindow() if dialog.surface else None
                shot=dialog.grab()
                if dialog.surface:
                    painter=QPainter(shot)
                    painter.drawImage(dialog.view.mapTo(dialog,QPoint(0,0)),gpu_shot)
                    painter.end()
                assert shot.save(str(image_path)); report['themes'].append(image_path.name)
            original = copy.deepcopy(item.effects[0])
            dialog.item.crop = Crop(.2, .1, .45, .65)
            dialog.mode.setCurrentText('Follow Crop'); dialog.refresh_preview(); settle()
            assert dialog.view.crop != dialog.item.crop
            image_path = output / f'follow-guide-{theme}.png'
            assert dialog.grab().save(str(image_path)); report['themes'].append(image_path.name)
            dialog.add_anchor()
            assert dialog.anchors and not dialog.dirty_track and dialog.apply_button.isEnabled()
            dialog.reject(); dialog.deleteLater(); settle()
            assert item.effects[0] == original, 'Cancelling corrections changed the timeline.'
            panels = window.inspector.findChildren(TrackingPanel)
            assert panels and panels[0].isVisible(), 'Object tracking inspector was not shown.'
            panel = panels[0]
            assert panel.mode.currentText() == 'Circle'
            for size in ((1480, 920), (1040, 760)):
                window.resize(*size); settle()
                image_path = output / f'inspector-{theme}-{size[0]}.png'
                assert window.grab().save(str(image_path)); report['themes'].append(image_path.name)
            previous_crop = copy.deepcopy(item.crop)
            item.crop = Crop(.2, .1, .45, .65)
            panel.mode.setCurrentText('Follow Crop'); settle()
            assert panel.mode.currentText() == 'Follow Crop'
            image_path = output / f'follow-inspector-{theme}.png'
            assert window.grab().save(str(image_path)); report['themes'].append(image_path.name)
            item.crop = previous_crop
            panel.mode.setCurrentText('Circle'); settle()

        phase('Real nested-modal reopen and popup ownership')
        import gc
        from .tracking_design import TrackingCard
        from PySide6.QtWidgets import QWidget,QDialog
        modal_checks=[]
        for reopen in range(3):
            modal=TrackingDialog(window,project.media[0],item,item.effects[0] if reopen else None)
            failures=[]
            def drive_modal():
                try:
                    deadline=time.monotonic()+5
                    while not modal.settled_frame() and time.monotonic()<deadline:settle(50)
                    assert modal.settled_frame()
                    captions={card:card.title_label.text() for card in modal.findChildren(TrackingCard)}
                    for size in ((980,700),(1280,850),(1440,1000)):
                        modal.resize(*size);settle(50)
                        for mode in MODES:
                            modal.mode.setCurrentText(mode)
                            gc.collect();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);settle(15)
                            assert all(card.title_label.text()==title for card,title in captions.items())
                            assert modal.mode.count()==len(MODES)
                        managed={modal.layout().itemAt(i).widget() for i in range(modal.layout().count())}
                        assert all(w in managed for w in modal.findChildren(QWidget,options=Qt.FindDirectChildrenOnly) if w.isVisible() and not w.isWindow())
                    modal.mode.setCurrentText('Censor Bar')
                    modal.mode.showPopup();settle(60)
                    popup=modal.mode.view().window()
                    bottom=modal.mode.mapToGlobal(QPoint(0,modal.mode.height())).y()
                    report['popup_probe']=dict(visible=popup.isVisible(),popup=(popup.x(),popup.y(),popup.width(),popup.height()),below=bottom,dialog_visible=modal.isVisible(),reopen=reopen)
                    # Windows closes ordinary Qt popups immediately on a
                    # non-input desktop too (plain-combo.log reproduces it).
                    # Check native geometry here; visible item selection is
                    # covered through the offscreen Qt popup/input test.
                    assert popup.y()>=bottom
                    modal.mode.hidePopup()
                    modal.marker_editor.add_kind('Arrow')
                    assert modal.marker_editor.picker.count()==2 and modal.mode.count()==len(MODES)
                    modal.marker_editor.picker.setCurrentIndex(0)
                    assert modal.mode.currentText()=='Censor Bar'
                    modal.marker_toggle.click();assert modal.marker_toggle.arrowType()==Qt.UpArrow
                    modal.marker_toggle.click();assert modal.marker_toggle.arrowType()==Qt.DownArrow
                    modal_checks.append(dict(reopen=reopen,real_exec=True,all_types=True,popup_below_geometry=True,native_popup_visible=popup.isVisible(),no_orphans=True))
                except Exception as error:failures.append(error)
                finally:modal.reject()
            QTimer.singleShot(0,drive_modal)
            assert modal.exec()==QDialog.Rejected
            if failures:raise failures[0]
            modal.deleteLater();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);settle(50)
        report['nested_modal_ownership']=modal_checks
        report['native_controls'] = True
        phase('Playback and multiple markers')

        # The new workflow keeps corrections editable and renders a shared
        # trajectory with independent markers through the normal GPU exporter.
        project,item=project_with('Circle')
        window.set_project(project)
        dialog=TrackingDialog(window,project.media[0],item,item.effects[0])
        dialog.show()
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not dialog.settled_frame():settle(40)
        assert dialog.player is not None and dialog.surface is not None
        assert dialog.anchor_list.rowCount()==len(analysis['frames'])
        assert len(dialog.timeline.keyframes)==len(analysis['frames'])
        # Real native held-pointer scrubs in both directions. Geometry must not
        # change when seek status and decoded-frame notifications alternate.
        timeline_width=dialog.timeline.width();positions=[]
        QTest.mousePress(dialog.timeline,Qt.LeftButton,pos=QPoint(30,41))
        for xs in (list(range(40,timeline_width-15,25)),list(range(timeline_width-20,30,-25))):
            values=[]
            for x in xs:
                QTest.mouseMove(dialog.timeline,QPoint(x,41));settle(20)
                assert dialog.timeline.width()==timeline_width
                assert dialog.timeline.value()==dialog.timeline.at(x)
                values.append(dialog.timeline.value())
            assert values==sorted(values,reverse=xs[0]>xs[-1]),values
            positions.append(values)
        QTest.mouseRelease(dialog.timeline,Qt.LeftButton,pos=QPoint(30,41))
        seek_results=[]
        for index in (10,35,65,40,20,61):
            dialog.timeline.setValue(index)
            deadline=time.monotonic()+3
            while not dialog.settled_frame() and time.monotonic()<deadline:settle(20)
            assert dialog.settled_frame(),('seek',index,dialog.sink.videoFrame().startTime())
            frame=dialog.sink.videoFrame();target=round(dialog.source_time()*1000000)
            assert frame.startTime()<=target+1000 and frame.endTime()>target,(index,frame.startTime(),frame.endTime(),target)
            seek_results.append(dict(index=index,start=frame.startTime(),end=frame.endTime()))
        for direction in (-1,1,-1,1):
            previous=dialog.timeline.value();dialog.step(direction)
            deadline=time.monotonic()+3
            while not dialog.settled_frame() and time.monotonic()<deadline:settle(20)
            assert dialog.settled_frame() and dialog.timeline.value()==previous+direction
        dialog.timeline.setValue(20)
        dialog.toggle_play()
        assert dialog.playing and not dialog._decode_timer.isActive()
        settle(180)
        assert dialog.timeline.value()>=20
        assert dialog.sink.videoFrame().endTime()>round(20/30*1000000)
        dialog.pause_for_edit()
        report['stable_scrubbing']=dict(pointer_positions=positions,seeks=seek_results,previous_next=True,label_stable=True)
        # The exact same source-time keys drive native GPU overlays and export.
        dialog.select_frame_rows([10,20]);dialog.seek_anchor(10)
        deadline=time.monotonic()+3
        while not dialog.settled_frame() and time.monotonic()<deadline:settle(20)
        dialog.mode.setCurrentText('Arrow');dialog.marker_editor.change('color','#ed47c4')
        dialog.refresh_preview();settle(80)
        assert dialog._published_markers[0]['mode']=='Arrow'
        temporal=dialog.result_effect()
        assert len(temporal['markers'][0]['appearance_keys'])==2
        temporal_project,temporal_item=project_with('Circle');temporal_item.effects=[temporal]
        temporal_target=output/'temporal-markers-gpu.mp4'
        export(temporal_project,str(temporal_target),PRESETS['TikTok · Fast'],False,'Auto',export_audio=False)
        with av.open(str(temporal_target)) as movie:temporal_frames=list(movie.decode(video=0))
        temporal_errors=[]
        for number in (6,21,51,75):
            expected=viewer_frame(temporal_project,temporal_item,number/30)
            difference=float(np.abs(image_array(expected)[:,:,:3].astype(float)-temporal_frames[number].to_ndarray(format='rgb24')).mean())
            assert difference<6,(number,difference)
            temporal_errors.append(difference)
        report['temporal_marker_gpu_export']=dict(frames=len(temporal_frames),keys=2,errors=temporal_errors)
        dialog.clear_frame_selection();dialog.marker_editor.current().pop('appearance_keys',None)
        dialog.mode.setCurrentText('Circle');dialog.timeline.setValue(0);settle(150)
        QTest.keyClick(dialog,Qt.Key_Space)
        assert dialog.playing
        first=dialog.player.position()
        first_frame=dialog.sink.videoFrame().startTime()
        first_paint=dialog.surface.frames
        settle(350)
        assert dialog.player.position()>first+100
        assert dialog.sink.videoFrame().startTime()>first_frame+100000
        assert dialog.surface.frames>first_paint
        dialog.timeline.setValue(30)
        settle(150)
        assert not dialog.playing
        assert abs(dialog.player.position()-1001)<70
        dialog.step(1)
        settle(150)
        assert not dialog.playing
        dialog.view.region=[.25,.25,.2,.2]
        dialog._shown_time=dialog.source_time()
        worker_count=len(window._workers)
        dialog.region_changed(dialog.view.region)
        assert not dialog.dirty_track and dialog.apply_button.isEnabled()
        assert len(window._workers)==worker_count
        dialog.marker_editor.kind.setCurrentText('Label')
        dialog.marker_editor.add()
        dialog.marker_editor.change('label','Tracked')
        dialog.marker_editor.change('font_size',22)
        dialog.marker_editor.change('offset_y',-45)
        dialog.marker_editor.kind.setCurrentText('Arrow')
        dialog.marker_editor.add()
        dialog.marker_editor.change('offset_x',65)
        dialog.marker_editor.change('rotation',25)
        dialog.marker_editor.picker.setCurrentIndex(0)
        dialog.transform_tool.setChecked(True);dialog.refresh_preview();settle(50)
        before_track=copy.deepcopy(dialog.effect['analysis'])
        original_offset=dialog.marker_editor.current().get('offset_x',0)
        geometry=dialog.view.selected();transform,rect=dialog.view.shape(geometry)
        point=transform.map(rect.center()).toPoint()
        # Route through the actual native QQuick window's production forwarding.
        QTest.mousePress(dialog.surface.view,Qt.LeftButton,pos=point)
        QTest.mouseMove(dialog.surface.view,point+QPoint(18,9))
        QTest.mouseRelease(dialog.surface.view,Qt.LeftButton,pos=point+QPoint(18,9))
        assert dialog.marker_editor.current()['offset_x']>original_offset
        point=dialog.view.handles(dialog.view.selected())['se'].toPoint()
        QTest.mousePress(dialog.surface.view,Qt.LeftButton,pos=point)
        QTest.mouseMove(dialog.surface.view,point+QPoint(15,12))
        QTest.mouseRelease(dialog.surface.view,Qt.LeftButton,pos=point+QPoint(15,12))
        assert dialog.marker_editor.current()['width']>100
        geometry=dialog.view.selected();transform,rect=dialog.view.shape(geometry)
        origin=transform.map(QPointF(0,0));knob=dialog.view.handles(geometry)['rotate']
        relative=knob-origin;target=origin+QPointF(-relative.y(),relative.x())
        QTest.mousePress(dialog.surface.view,Qt.LeftButton,pos=knob.toPoint())
        QTest.mouseMove(dialog.surface.view,target.toPoint())
        QTest.mouseRelease(dialog.surface.view,Qt.LeftButton,pos=target.toPoint())
        assert abs(dialog.marker_editor.current()['rotation']-90)<3
        assert dialog.effect['analysis']==before_track
        report['native_marker_gizmo']=dict(move=True,resize=True,rotate=True,trajectory_unchanged=True)
        dialog.before.setChecked(False)
        settle(120)
        assert dialog.surface.view.grabWindow().save(str(output/'multiple-marker-preview.png'))
        effect=dialog.result_effect()
        assert len(effect['markers'])==3
        dialog.reject();dialog.deleteLater();settle(80)
        item.effects=[effect]
        target=output/'multiple-markers-gpu.mp4'
        messages=[]
        export(project,str(target),PRESETS['TikTok · Fast'],False,'Auto',export_audio=False,
               progress=lambda _,message:messages.append(message))
        with av.open(str(target)) as movie:
            decoded=list(movie.decode(video=0))
        assert len(decoded)==84
        for number in (6,21,51,75):
            expected=viewer_frame(project,item,number/30)
            difference=float(np.abs(image_array(expected)[:,:,:3].astype(float)-decoded[number].to_ndarray(format='rgb24')).mean())
            assert difference<6,(number,difference)
        report['playback_correction_multiple_markers']=dict(passed=True,decoded_frames=len(decoded),markers=3,
            export_messages=messages[-3:])

        partial_project,partial_item=project_with('Censor Bar')
        phase('Partial range export')
        partial=partial_item.effects[0]['analysis']
        partial['frames']=[point for point in partial['frames'] if point['time']<=2.0]
        partial['source_end']=partial['frames'][-1]['time']
        target=output/'partial-tracking-protected.mp4'
        export(partial_project,str(target),PRESETS['TikTok · Fast'],False,'Auto',export_audio=False)
        with av.open(str(target)) as movie:protected=list(movie.decode(video=0))
        assert len(protected)==84
        assert protected[75].to_ndarray(format='rgb24').max()<8
        report['extended_range_export_protected']=True

        # Exercise the actual authenticated loopback MCP transport, not a
        # direct EditorAPI call. The network client never touches Qt objects;
        # queued server requests and worker completion settle on the GUI thread.
        from .assistant_client import Client
        phase('MCP tracking')
        from .media import make_thumbnail
        network_project, network_item = project_with('Circle')
        network_item.effects = []
        network_project.name = 'Disposable MCP object tracking check'
        # A normal import supplies a thumbnail. This hand-authored fixture
        # previously allowed MediaPanel's asynchronous discovery to add cache
        # metadata after the history baseline, obscuring the tracking edit.
        network_project.media[0].thumbnail = make_thumbnail(
            source, 'video', window.settings.get('ffmpeg', 'ffmpeg'), timeout=15)
        assert network_project.media[0].thumbnail
        window.apply_theme('default', save=False)
        window.set_project(network_project)
        window.select_item(network_item.id)
        settle()
        window.commit_history()
        history_length = len(window._history)
        history_index = window._history_index
        connection = window.assistant_connection
        if connection.server is not None: connection.stop()
        connection.config['port'] = 0
        connection.start()
        assert connection.server is not None, connection.error
        endpoint = connection.server.url
        token = connection.config['token']
        finished = threading.Event()
        network = {}

        def network_work():
            try:
                client = Client(endpoint, token)
                handshake = client.initialize('Object Tracking native verification')
                tools = client.request('tools/list')['tools']
                names = [tool['name'] for tool in tools]
                assert {'track_object', 'tracking_job_control'} <= set(names)
                schema = next(tool['inputSchema'] for tool in tools if tool['name'] == 'track_object')
                assert schema['required'] == ['revision', 'item_id', 'reference_source_time', 'region']
                assert schema['properties']['mode']['enum'] == list(MODES)
                capabilities = client.value('get_capabilities')['object_tracking']
                assert capabilities['modes'] == list(MODES)
                state = client.value('get_state')
                assert not state['project']['timeline'][0].get('effects',[])
                job = client.value('track_object', revision=state['revision'],
                    item_id=network_item.id, reference_source_time=.7, region=boxes[21],
                    anchors=[dict(time=1.7, box=boxes[51])], mode='Circle',
                    properties=dict(color='#46e0ad', stroke_width=6.),
                    sample_fps=15, search_radius=.16, confidence_threshold=.62)
                deadline = time.monotonic()+30
                while time.monotonic() < deadline:
                    tasks = client.value('get_jobs')['tasks']
                    complete = next(task for task in tasks if task['id'] == job['id'])
                    if complete['state'] not in ('Running', 'Cancelling'): break
                    time.sleep(.05)
                assert complete['state'] == 'Complete', complete
                assert complete['progress'] == 100. and complete['undoable'], complete
                changed = client.value('get_state')['project']
                effects = changed['timeline'][0]['effects']
                assert len(effects) == 1 and effects[0]['name'] == 'Object Tracking'
                assert effects[0]['analysis']['anchors'] == [dict(time=.7, box=boxes[21]),
                                                            dict(time=1.7, box=boxes[51])]
                client.value('history', direction='undo')
                assert not client.value('get_state')['project']['timeline'][0].get('effects',[])
                client.value('history', direction='redo')
                restored = client.value('get_state')['project']['timeline'][0]['effects']
                assert restored == effects
                network.update(passed=True, server=handshake['serverInfo'],
                    tools=['track_object', 'tracking_job_control'], state=complete['state'],
                    progress=complete['progress'], sample_count=complete['sample_count'],
                    lost_samples=complete['lost_samples'], undo_redo=True)
            except Exception:
                network.update(passed=False, error=traceback.format_exc())
            finally:
                finished.set()

        client_thread = threading.Thread(target=network_work, daemon=True,
                                         name='TrackingNativeMCP')
        client_thread.start()
        deadline = time.monotonic()+45
        try:
            while not finished.is_set() and time.monotonic() < deadline:
                settle(40)
            assert finished.is_set(), 'The isolated MCP tracking check did not complete.'
            client_thread.join(timeout=1)
            assert network.get('passed'), network
            network['history_before'] = dict(length=history_length, index=history_index)
            network['history_after'] = dict(length=len(window._history), index=window._history_index)
            network['history_change_keys'] = []
            for previous, following in zip(window._history, window._history[1:]):
                a, b = previous.to_dict(), following.to_dict()
                changes = [key for key in a
                           if key not in ('playhead', 'modified_at') and a.get(key) != b.get(key)]
                network['history_change_keys'].append(changes)
            report['mcp_network'] = network
            assert len(window._history) == history_length+1, network['history_after']
            assert window._history_index == history_index+1, network['history_after']
            current = window.project.timeline[0]
            assert effect_valid(current.effects[0], window.project.media_by_id(current.media_id), current)
            network['exactly_one_history_step'] = True
            network['effect_valid'] = True
            report['mcp_network'] = network
        finally:
            connection.stop()
        if os.environ.get('KINETIC_TRACKING_REAL_SOURCE'):
            phase('Real media Add Effect first-open/reopen')
            report['real_first_open']=verify_tracking_first_open(window,app,output,os.environ['KINETIC_TRACKING_REAL_SOURCE'])
        report['passed'] = True
    except Exception:
        report['passed'] = False
        report['error'] = traceback.format_exc()
    finally:
        phase('Cleanup')
        if window is not None:
            window.close()
            QThreadPool.globalInstance().waitForDone(10000)
            window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        trace.close()
        phase('Complete')
    return 0 if report['passed'] else 1
