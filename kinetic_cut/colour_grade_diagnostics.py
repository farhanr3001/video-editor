"""Private desktop check for grading, graphic transforms and export parity."""
import json
import os
import sys
import time
from pathlib import Path


def run(output):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ.update(KINETIC_CUT_HOME=str(out/"home"), QT_QPA_PLATFORM="windows",
                      QSG_RHI_BACKEND="d3d11")
    mode = os.environ.get("KINETIC_GRADE_CHECK_MODE", "ui")
    source = Path(os.environ["KINETIC_GRADE_TEST_SOURCE"])
    report = {"mode": mode, "frozen": bool(getattr(sys, "frozen", False)), "checks": []}

    def save():
        (out/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        save()
        assert condition, name

    from PySide6.QtWidgets import QApplication
    from .model import MediaItem, Project, ProjectSettings, TimelineItem, Transform
    from .colour_grade import PRESETS, clean
    from .graphics import GRAPHICS_CATALOG, default_graphic_data
    from .motion_presets import is_motion

    app = QApplication([])
    app.setProperty("kineticTestDiscardUnsaved", True)
    app.setQuitOnLastWindowClosed(False)
    media = MediaItem("webcam", str(source), "video", source.name, 244., 1920, 1080, 60, True)

    def webcam(duration):
        return Project(settings=ProjectSettings(width=1920, height=1080, fps=60), media=[media],
                       timeline=[TimelineItem("video", media.id, "video_1", 0., duration, in_point=12.,
                                              transform=Transform(x=.5, y=.5))])

    def graphics():
        items = []
        for variant in range(2):
            for name in GRAPHICS_CATALOG:
                n = len(items)
                data = default_graphic_data(name)
                if name == "Pointing Arrow":
                    data.update(direction="Up" if variant else "Right", style="Double-Headed" if variant else "Straight")
                items.append(TimelineItem(f"g{n}", "", "video_1", n*.5, .5, role="graphic", graphic_type=name,
                                         in_point=1.4 if is_motion(name) else 0,
                                         graphic_data=data, transform=Transform(x=.39 if variant else .56,
                                         y=.44 if variant else .57, scale=.68 if variant else .91,
                                         scale_y=.9 if variant else .75, rotation=-27 if variant else 12,
                                         anchor_x=17 if variant else 0, anchor_y=-12 if variant else 0)))
        return Project(settings=ProjectSettings(width=960, height=540, fps=30), timeline=items)

    if mode in ("export", "speed"):
        export_checks(out, report, check, webcam, graphics, mode)
    else:
        ui_checks(app, out, report, check, webcam, graphics)
    report["passed"] = True
    save()
    return 0


def ui_checks(app, out, report, check, webcam, graphics):
    import numpy as np
    from PySide6.QtCore import Qt, QEvent, QEventLoop, QPointF, QTimer
    from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .colour_grade import PRESETS, clean, saved_presets
    from .colour_grade_dialog import GradeDialog
    from .model import MediaItem, Project, TimelineItem
    from .theme_widgets import apply_application_theme
    from .ui import MainWindow
    from .video_presets import PresetNameDialog

    def wait(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def until(condition, timeout=8):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            if condition():
                return True
            wait(40)
        return False

    def pixels(image):
        image = image.convertToFormat(QImage.Format_RGBA8888)
        return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.width(), 4).copy()

    def screenshot(dialog, name):
        shot = dialog.grab()
        preview = dialog.monitor.surface.view.grabWindow()
        painter = QPainter(shot)
        painter.drawImage(dialog.monitor.mapTo(dialog, dialog.monitor.rect().topLeft()), preview)
        painter.end()
        shot.save(str(out/(name+".png")))

    w = MainWindow()
    w.autosave_timer.stop()
    w.preview_quality.request = lambda: None
    w.resize(1420, 900)
    w.show()
    p = webcam(5)
    p.timeline[0].brightness = -.19
    p.timeline[0].sharpen = .2
    p.playhead = .4
    w.set_project(p)
    w.select_item("video")
    w.inspector.tabs.setCurrentIndex(3)
    w.flush_text_edit()
    grade = clean(PRESETS[2][1])
    main_position = p.playhead

    def workflow(dialog):
        received = until(lambda: not dialog.monitor.message)
        report["monitor_status"] = [dialog.player.mediaStatus().name, dialog.player.position(), dialog.monitor.message]
        check("private clip monitor receives frames", received)
        check("monitor uses D3D11", dialog.monitor.surface.diagnostics()["graphics_backend"] == "Direct3D11")
        frame = dialog.monitor.sink.videoFrame()
        report["decoder_handle"] = frame.handleType().name
        first_frame = frame.startTime()
        report["initial_frame_us"] = first_frame
        check("trimmed initial frame", abs(first_frame-12_400_000) < 100_000)
        QTest.keyClick(dialog, Qt.Key_Space)
        check("Space starts independent playback", until(lambda: dialog.player.playbackState() == QMediaPlayer.PlayingState
              and dialog.monitor.sink.videoFrame().startTime() > first_frame+120_000))
        QTest.keyClick(dialog, Qt.Key_Space)
        check("Space pauses", dialog.player.playbackState() == QMediaPlayer.PausedState)
        dialog.scrubber.setValue(120)
        check("scrub seeks to trimmed source frame", until(lambda: abs(dialog.monitor.sink.videoFrame().startTime()-14000000) < 50000))
        check("main playhead is unchanged", p.playhead == main_position)
        dialog.presets.setCurrentIndex(3)
        dialog.presets.activated.emit(3)
        check("preset changes draft only", dialog.current == grade and p.timeline[0].colour_grade == {})
        dialog.tabs.setCurrentIndex(1)
        tone = dialog.tone["exposure"][1]
        tone.setValue(.22)
        tone.lineEdit().setFocus()
        QTest.keyClick(tone.lineEdit(), Qt.Key_Z, Qt.ControlModifier)
        check("Ctrl+Z in number field undoes grade only", dialog.current == grade and p.timeline[0].colour_grade == {})
        QTest.keyClick(tone.lineEdit(), Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
        check("Ctrl+Shift+Z restores individual change", dialog.current.get("exposure") == .22)
        dialog.undo()
        dialog.tabs.setCurrentIndex(0)
        wheel = dialog.wheels["gamma"][0]
        QTest.mousePress(wheel, Qt.LeftButton, pos=wheel.rect().center())
        QTest.mouseMove(wheel, wheel.rect().center()+QPointF(17, -13).toPoint())
        QTest.mouseRelease(wheel, Qt.LeftButton, pos=wheel.rect().center()+QPointF(17, -13).toPoint())
        check("wheel drag changes tint", dialog.current["gamma"] != grade["gamma"])
        dialog.undo()
        check("wheel drag is one undo step", dialog.current == grade)
        wait(150)
        graded = pixels(dialog.monitor.surface.view.grabWindow())
        position = dialog.player.position()
        history = dialog.history_index
        QTest.mousePress(dialog.before_button, Qt.LeftButton)
        wait(100)
        before = pixels(dialog.monitor.surface.view.grabWindow())
        check("holding Original bypasses basic colour, sharpen and advanced grade on GPU",
              np.abs(before.astype(float)-graded).mean() > 1
              and dialog.monitor.layer.property("grade").x() == 0
              and dialog.monitor.layer.property("sharpen") == 0
              and not dialog.monitor.layer.property("gradeSlope").w())
        QTest.mouseRelease(dialog.before_button, Qt.LeftButton)
        wait(100)
        restored = pixels(dialog.monitor.surface.view.grabWindow())
        check("release restores the grade on the same frame without history",
              np.array_equal(graded, restored) and dialog.player.position() == position
              and dialog.history_index == history and dialog.current == grade)
        QTest.keyPress(dialog.monitor, Qt.Key_Backslash)
        check("backslash holds original", dialog.original_key and not dialog.monitor.layer.property("gradeSlope").w())
        QTest.keyRelease(dialog.monitor, Qt.Key_Backslash)
        check("backslash release restores grade", not dialog.original_key and dialog.monitor.layer.property("gradeSlope").w())
        screenshot(dialog, "default-normal")
        check("built-in presets cannot be deleted", not dialog.delete_preset_button.isEnabled())
        def enter_name():
            prompt = dialog.findChild(PresetNameDialog)
            if prompt is None:
                return
            prompt.name.setText("teal & amber")
            if prompt.save.isEnabled():
                prompt.reject()
                return
            prompt.name.setText("Webcam Look")
            prompt.save.click()
        QTimer.singleShot(60, enter_name)
        dialog.save_preset_button.click()
        check("named preset saves the current draft without adding history",
              dialog.presets.currentText() == "Webcam Look" and dialog.history_index == history
              and saved_presets(w.settings)[0]["values"] == grade and p.timeline[0].colour_grade == {})
        dialog.accept()

    def open_dialog(action):
        failures = []

        def inspect():
            dialog = w.findChild(GradeDialog)
            if dialog is None:
                failures.append(RuntimeError("Inspector did not open Advanced Colours"))
                return
            try:
                action(dialog)
            except BaseException as error:
                failures.append(error)
                dialog.reject()

        QTimer.singleShot(250, inspect)
        w.inspector.advanced_colours.click()
        if failures:
            raise failures[0]

    check("Advanced Colours is available from the selected clip", w.inspector.advanced_colours.isEnabled())
    open_dialog(workflow)
    check("Apply commits entire grade", p.timeline[0].colour_grade == grade)
    w.undo()
    check("editor undo reverts entire session", w.project.timeline[0].colour_grade == {})
    w.redo()
    check("editor redo reapplies entire session", w.project.timeline[0].colour_grade == grade)
    history = w._history_index
    open_dialog(lambda dialog: (dialog.replace({}), dialog.reject()))
    check("Cancel adds no editor history", w._history_index == history and w.project.timeline[0].colour_grade == grade)

    def edit_saved_preset(dialog):
        check("saved preset is in the list after reopening", dialog.presets.currentText() == "Webcam Look")
        dialog.edit("exposure", .37)
        check("editing a draft leaves the saved preset intact", dialog.presets.currentText() == "Webcam Look (edited)"
              and saved_presets(w.settings)[0]["values"] == grade)
        def answer(label):
            prompt = next((m for m in dialog.findChildren(QMessageBox) if m.isVisible()), None)
            if prompt:
                button = next(b for b in prompt.buttons() if b.text().replace("&", "") == label)
                button.click()
        QTimer.singleShot(60, lambda: answer("Overwrite"))
        dialog.save_preset_button.click()
        check("overwrite keeps the same preset with the new grade",
              len(dialog.custom_presets) == 1 and dialog.custom_presets[0]["values"].get("exposure") == .37)
        dialog.reset_grade_button.click()
        check("grade reset icon resets the draft", dialog.current == {})
        dialog.apply_preset(dialog.presets.findText("Webcam Look"))
        check("reapplying the saved look is a local undo step", dialog.current.get("exposure") == .37)
        dialog.undo()
        check("local undo reverts applying the saved look", dialog.current == {})
        dialog.redo()
        dialog.reject()

    open_dialog(edit_saved_preset)
    from .config import SETTINGS_PATH
    def disk_presets():
        try:
            return saved_presets(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
    check("overwritten preset persists even when the clip edit is cancelled",
          until(lambda: any(r["values"].get("exposure") == .37 for r in (disk_presets() or [])))
          and w.project.timeline[0].colour_grade == grade)

    def compact(dialog, theme):
        dialog.resize(620, 550)
        wait(160)
        check(theme+" compact wheels and level fields fit", all(wheel.isVisible() and wheel.width() >= 100
              and wheel.geometry().bottom() < spin.geometry().top() for wheel, spin, _ in dialog.wheels.values()))
        check(theme+" compact preset buttons fit", dialog.rect().contains(dialog.save_preset_button.geometry())
              and dialog.rect().contains(dialog.delete_preset_button.geometry()))
        resets = [dialog.reset_grade_button, *(reset for _, _, reset in dialog.wheels.values())]
        check(theme+" resets use accessible refresh icons", all(
            not b.text() and not b.icon().isNull() and b.toolTip() == b.accessibleName() for b in resets))
        screenshot(dialog, theme+"-compact")
        dialog.tabs.setCurrentIndex(1)
        wait(90)
        check(theme+" compact Tone is visible", all(spin.isVisible() for _, spin, _, _ in dialog.tone.values()))
        screenshot(dialog, theme+"-tone")
        dialog.reject()

    for theme in ("default", "final_cut_obsidian", "ableton_gray"):
        apply_application_theme(theme)
        open_dialog(lambda dialog, t=theme: compact(dialog, t))

    def remove_saved_preset(dialog):
        dialog.apply_preset(dialog.presets.findText("Webcam Look"))
        def confirm():
            prompt = next((m for m in dialog.findChildren(QMessageBox) if m.isVisible()), None)
            if prompt:
                prompt.button(QMessageBox.Yes).click()
        QTimer.singleShot(60, confirm)
        dialog.delete_preset_button.click()
        check("deleting a preset leaves the current draft and built-ins",
              not dialog.custom_presets and dialog.current.get("exposure") == .37
              and dialog.presets.count() == 1+len(PRESETS))
        dialog.reject()
    open_dialog(remove_saved_preset)
    check("deleted preset is removed from disk", until(lambda: disk_presets() == []))

    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(QColor("#6589ac"))
    still = out/"still.png"
    image.save(str(still))
    w.set_project(Project(media=[MediaItem("still", str(still), "image", "Still image", 0, 320, 180)],
                          timeline=[TimelineItem("still-clip", "still", "video_1", 0, 1)]))
    w.select_item("still-clip")

    def check_still(dialog):
        check("still image loads as a GPU texture", until(lambda: dialog.monitor.surface.root.property("imageReady")))
        check("still image disables playback controls", not dialog.play_button.isEnabled() and not dialog.scrubber.isEnabled())
        dialog.replace(grade)
        wait(100)
        shot = pixels(dialog.monitor.surface.view.grabWindow())
        check("graded still image is visible", np.count_nonzero(shot[..., 2] > 70) > 1000)
        dialog.accept()

    open_dialog(check_still)
    check("still image grade commits", w.project.timeline[0].colour_grade == grade)

    p = graphics()
    w.set_project(p)
    w.preview.set_transform_controls_visible(True)
    for item in p.timeline[:len(p.timeline)//2]:
        w.seek(item.start+.25)
        w.select_item(item.id)
        wait(100)
        preview = w.preview
        rect = preview._graphic_rect(item, preview.composition_rect())
        anchor, corners, _, rotation, _ = preview._transform_geometry(item, rect)
        check(item.graphic_type+" has resize and rotation grips", not rect.isEmpty() and (rotation-anchor).manhattanLength() > 25)

        def drag(start, end, kind):
            host=preview.gpu.view
            QTest.mousePress(host, Qt.LeftButton, pos=start.toPoint())
            assert preview.drag_mode == kind, (item.graphic_type, preview.drag_mode, kind)
            QApplication.sendEvent(host, QMouseEvent(QEvent.MouseMove, end, QPointF(preview.mapToGlobal(end.toPoint())),
                                                        Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
            QTest.mouseRelease(host, Qt.LeftButton, pos=end.toPoint())

        old = item.transform.scale
        drag(corners[1], anchor+(corners[1]-anchor)*1.18, "scale")
        check(item.graphic_type+" corner updates inspector scale",
              item.transform.scale > old and abs(w.inspector.gtr_scale.spin.value()-item.transform.scale) < .002)
        rect = preview._graphic_rect(item, preview.composition_rect())
        anchor, _, _, rotation, _ = preview._transform_geometry(item, rect)
        drag(rotation, anchor+QPointF(62, 0), "rotate")
        check(item.graphic_type+" grip updates inspector rotation",
              abs(item.transform.rotation-90) < 2 and abs(w.inspector.gtr_rot.spin.value()-item.transform.rotation) < 1)
    w.set_project(Project())
    w.close()
    check("private editor closes normally", until(lambda: not w.isVisible(), 25))


def export_checks(out, report, check, webcam, graphics, mode):
    import statistics
    import av
    import numpy as np
    from PySide6.QtGui import QImage
    from .colour_grade import PRESETS, apply_rgb, clean
    from .export_process import render
    from .exporter import ExportPreset, export
    from .gpu_export import mux_command, prepare_recipe, render_native
    from .native_animation import frame
    from .motion_gpu import is_motion

    preset = ExportPreset("Grade check", "h264", 25, 192, "Grade check", "auto")
    grade = clean(PRESETS[2][1])

    def native(project, name):
        target = out/name
        target.mkdir(exist_ok=True)
        start = time.perf_counter()
        recipe = prepare_recipe(project, preset, target, False, {}, "ffmpeg", None, None)
        status = render_native(recipe, target)
        path = target/"result.mp4"
        code, log = render(mux_command(project, recipe, str(path), preset, "ffmpeg", False), project.duration)
        duration = time.perf_counter()-start
        check(name+" native D3D11 and NVENC export", code == 0 and status["composition"] == "Direct3D11 GPU"
              and status["encoder"] == "NVENC D3D11 texture")
        return path, duration, recipe, status

    def frames(path, wanted):
        with av.open(str(path)) as movie:
            return {i:f.to_ndarray(format="rgb24") for i, f in enumerate(movie.decode(video=0)) if i in wanted}

    if mode == "speed":
        project = webcam(20)
        seconds = {"baseline": [], "graded": []}
        for i, kind in enumerate(("baseline", "graded", "graded", "baseline", "baseline", "graded")):
            project.timeline[0].colour_grade = grade if kind == "graded" else {}
            _, elapsed, recipe, status = native(project, f"{i}-{kind}")
            check("native hardware frames and no preparation", status["decoded_gpu"] > 0 and status["decoded_cpu"] == 0 and not recipe["cpu_islands"])
            seconds[kind].append(elapsed)
        report["seconds"] = seconds
        report["median"] = {kind: statistics.median(values) for kind, values in seconds.items()}
        return

    p = webcam(.6)
    baseline, _, _, _ = native(p, "baseline")
    p.timeline[0].colour_grade = grade
    graded, _, job, status = native(p, "graded")
    check("grading is GPU-only on the webcam clip", not job["cpu_islands"] and status["decoded_gpu"] > 0 and status["decoded_cpu"] == 0)
    with av.open(str(graded)) as movie:
        stream = movie.streams.video[0]
        check("native graded output retains 1920x1080 at 60 fps", stream.width == 1920 and stream.height == 1080 and stream.average_rate == 60)
    wanted = (2, 17, 30)
    after = frames(graded, wanted)
    before = frames(baseline, wanted)
    error = np.mean([np.abs(apply_rgb(before[i]/255., grade)*255-after[i]).mean() for i in wanted])
    report["webcam_grade_reference_mean_error"] = float(error)
    check("native webcam grade matches reference colour math", error < 5)
    compatibility = out/"compatibility.mp4"
    export(p, str(compatibility), preset, False, "CPU", export_audio=False)
    compatible = frames(compatibility, wanted)
    check("compatibility export keeps the grade", np.mean([np.abs(compatible[i].astype(float)-after[i]).mean() for i in wanted]) < 6)
    item = p.timeline[0]
    item.effects = [{"name": "Gaussian Blur", "horizontal": 3, "vertical": 3, "blend": 100}]
    item.colour_grade = {}
    smooth, _, _, _ = native(p, "blur")
    item.colour_grade = grade
    smooth_grade, _, job, _ = native(p, "graded-blur")
    a, b = frames(smooth, wanted), frames(smooth_grade, wanted)
    error = np.mean([np.abs(apply_rgb(a[i]/255., grade)*255-b[i]).mean() for i in wanted])
    check("grade and blur remain on GPU with expected pixel colours", not job["cpu_islands"] and error < 5)

    p = graphics()
    rendered, _, recipe, _ = native(p, "graphics")
    times = [round((i.start+.4)*30) for i in p.timeline]
    actual = frames(rendered, times)
    from .motion_gpu_render import MotionStage
    stage = MotionStage(960, 540)
    try:
        for index, (item, t) in enumerate(zip(p.timeline, times)):
            elapsed = t/30-item.start
            image = stage.render([item], p, lambda _: elapsed) if is_motion(item) else frame(p, item, elapsed)
            image = image.convertToFormat(QImage.Format_RGBA8888)
            rgba = np.frombuffer(image.constBits(), np.uint8).reshape(540, 960, 4).astype(float)
            reference = rgba[..., :3]*rgba[..., 3:4]/255
            strong = reference.max(axis=-1) > 72
            result = actual[t].max(axis=-1) > 72
            union = np.count_nonzero(strong | result)
            overlap = np.count_nonzero(strong & result)/max(1, union)
            check(f"{item.graphic_type} transform {index} matches drawn geometry (IoU {overlap:.3f})", overlap > .80)
    finally:
        stage.close()
