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
    os.environ['KINETIC_CUT_HOME'] = str(output / 'home')
    os.environ['QT_QPA_PLATFORM'] = 'windows' if os.name == 'nt' else 'offscreen'
    from PySide6.QtCore import Qt, QRectF, QEventLoop, QTimer, QThreadPool, QEvent
    from PySide6.QtGui import QImage, QColor, QPainter, QPainterPath
    from PySide6.QtWidgets import QApplication, QMessageBox
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
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            window.apply_theme(theme, save=False)
            dialog = TrackingDialog(window, project.media[0], item, item.effects[0])
            dialog.show()
            for _ in range(30):
                settle(100)
                if not dialog.raw.isNull() and dialog.settled_frame(): break
            assert not dialog.raw.isNull() and dialog.settled_frame(), dialog.info.text()
            assert dialog.apply_button.isEnabled()
            dialog.before.setChecked(False)
            for size in ((980, 750), (760, 640)):
                dialog.resize(*size); settle()
                image_path = output / f'dialog-{theme}-{size[0]}.png'
                assert dialog.grab().save(str(image_path)); report['themes'].append(image_path.name)
            original = copy.deepcopy(item.effects[0])
            dialog.item.crop = Crop(.2, .1, .45, .65)
            dialog.mode.setCurrentText('Follow Crop'); dialog.refresh_preview(); settle()
            assert dialog.view.crop != dialog.item.crop
            image_path = output / f'follow-guide-{theme}.png'
            assert dialog.grab().save(str(image_path)); report['themes'].append(image_path.name)
            dialog.add_anchor()
            assert dialog.anchors and dialog.dirty_track and not dialog.apply_button.isEnabled()
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
        report['native_controls'] = True

        # Exercise the actual authenticated loopback MCP transport, not a
        # direct EditorAPI call. The network client never touches Qt objects;
        # queued server requests and worker completion settle on the GUI thread.
        from .assistant_client import Client
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
                assert not state['project']['timeline'][0]['effects']
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
                assert not client.value('get_state')['project']['timeline'][0]['effects']
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
        report['passed'] = True
    except Exception:
        report['passed'] = False
        report['error'] = traceback.format_exc()
    finally:
        if window is not None:
            window.close()
            QThreadPool.globalInstance().waitForDone(10000)
            window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
