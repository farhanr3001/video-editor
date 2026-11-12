"""Optional drop layout: blurred background, fitted content and a webcam layer.

The layout is deterministic. The webcam comes from a saved Video preset or a
crop the user draws in the same dialog; the content layer is never cropped and is zoomed so its
height exactly fills the output space below the webcam.
"""
import copy

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from .controls import SafeComboBox
from .model import Crop, TimelineItem, Transform, uid

MIN_CONTENT = .1  # the content layer always keeps at least this share of the frame height


def _base(project, media):
    """Zoom 1.0 fills the output frame; crop and scale operate on top of it."""
    width, height = max(1, media.width), max(1, media.height)
    return max(project.settings.width / width, project.settings.height / height)


def layer_height(project, media, item):
    from .exporter import _target_size
    return _target_size(item, media, project.settings.width, 1., project.settings.height)[1]


def fit_webcam_crop(project, media, item, crop):
    """Scale a drawn webcam crop to the output width and park it at the top."""
    item.crop = copy.deepcopy(crop).clamped()
    item.transform = Transform(.5, .5, 1.)
    scale = project.settings.width / max(1e-6, max(1, media.width) * item.crop.width * _base(project, media))
    item.transform.scale = scale
    item.transform.y = layer_height(project, media, item) / 2 / project.settings.height


def webcam_bottom(project, media, item):
    """Output-pixel position of the webcam layer's lower edge."""
    height = project.settings.height
    bottom = item.transform.y * height + layer_height(project, media, item) / 2
    return max(0., min(bottom, height * (1 - MIN_CONTENT)))


def fit_content(project, media, item, top):
    """Uncropped content: the full source height fills the space below `top`."""
    height = project.settings.height
    remaining = max(height * MIN_CONTENT, height - top)
    item.crop = Crop()
    scale = remaining / (max(1, media.height) * _base(project, media))
    item.transform = Transform(.5, (height - remaining / 2) / height, scale)


def place(stage, media, track, start, in_point, duration, group, layout):
    """Append background, content and webcam layers to `stage` for one media item.

    The webcam stays on the requested lane (never below layer 3); the content goes
    to layer 2 and the blurred background to layer 1.
    """
    while len(stage.video_tracks) < 3:
        stage.add_track('video')
    lanes = stage.video_tracks
    index = max(2, lanes.index(track)) if track in lanes else 2
    background_lane, content_lane, webcam_lane = lanes[0], lanes[1], lanes[index]
    for number, lane in ((1, background_lane), (2, content_lane), (index + 1, webcam_lane)):
        if stage.track_states.get(lane, {}).get('locked'):
            raise ValueError(f'Unlock video layer {number} before using the auto 3-layer layout.')
    common = dict(media_id=media.id, start=start, duration=duration, in_point=in_point, group_id=group)
    blur = max(1., float(stage.settings.blur or 12.))
    background = TimelineItem(uid(), track=background_lane, role='normal', crop=Crop(), transform=Transform(.5, .5, 1.),
        effects=[dict(name='Gaussian Blur', enabled=True, horizontal=blur, vertical=blur, linked=True, border='Reflect', blend=100.)], **common)
    webcam = TimelineItem(uid(), track=webcam_lane, role='normal', is_webcam=True, crop=Crop(), transform=Transform(.5, .5, 1.), **common)
    if layout.get('mode') == 'preset':
        from .video_presets import apply
        apply(stage, webcam, layout['values'])
        webcam.video_preset_id = layout.get('id', '')
    else:
        fit_webcam_crop(stage, media, webcam, Crop(*layout['crop']))
    content = TimelineItem(uid(), track=content_lane, crop=Crop(), transform=Transform(.5, .5, 1.),
        role='normal' if any(i.role == 'content' for i in stage.timeline) else 'content', **common)
    fit_content(stage, media, content, webcam_bottom(stage, media, webcam))
    layers = [background, content, webcam]
    stage.timeline.extend(layers)
    return layers


CUSTOM = '__custom_crop__'


def preset_crop(values, media):
    """The webcam crop a saved Video preset would give this media (normalized)."""
    from .video_presets import validate
    values = validate(values)
    width, height = max(1, media.width), max(1, media.height)
    return Crop(values['crop_left'] / width, values['crop_top'] / height,
                1 - (values['crop_left'] + values['crop_right']) / width,
                1 - (values['crop_top'] + values['crop_bottom']) / height).clamped()


def _same(a, b, tolerance=1e-4):
    return all(abs(getattr(a, k) - getattr(b, k)) <= tolerance for k in ('x', 'y', 'width', 'height'))


class AutoLayoutDialog(QDialog):
    """Pick a saved webcam preset or draw the webcam crop; both share one crop view.

    Choosing a preset shows its crop. Editing the crop by hand switches the choice to
    "Custom crop", so the result is always exactly what the view shows.
    """
    def __init__(self, parent, records, image, media):
        super().__init__(parent)
        from .widgets import CropCanvas
        self.records = list(records); self.media = media
        self.setWindowTitle('Auto 3-layer layout'); self.setObjectName('autoLayoutDialog'); self.resize(880, 660)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Webcam source'))
        self.combo = SafeComboBox(); self.combo.setObjectName('autoLayoutPresetCombo')
        for record in self.records:
            self.combo.addItem(record['name'], record['id'])
        self.combo.addItem('Custom crop (draw below)', CUSTOM)
        layout.addWidget(self.combo)
        head = QHBoxLayout()
        hint = QLabel('Choose a saved preset, or draw, move or resize the webcam region. Wheel zooms · middle drag pans.')
        hint.setWordWrap(True); head.addWidget(hint, 1)
        fit = QPushButton('Fit'); reset = QPushButton('Reset Crop'); head.addWidget(fit); head.addWidget(reset)
        layout.addLayout(head)
        self.canvas = CropCanvas(image, Crop()); self.canvas.setObjectName('autoLayoutCropCanvas')
        layout.addWidget(self.canvas, 1)
        note = QLabel('The webcam is fitted to the top of the frame, the content fills the space below it and the background is blurred automatically.')
        note.setWordWrap(True); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Confirm')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        fit.clicked.connect(self.canvas.reset_view)
        reset.clicked.connect(lambda: self.set_crop(Crop(), user=True))
        self.combo.currentIndexChanged.connect(self.choice_changed)
        self.canvas.cropChanged.connect(self.crop_edited)
        self.choice_changed()

    def record(self):
        return next((r for r in self.records if r['id'] == self.combo.currentData()), None)

    def set_crop(self, crop, user=False):
        self.canvas.crop = Crop(**crop.__dict__).clamped(); self.canvas.update()
        if user: self.crop_edited(self.canvas.crop)

    def choice_changed(self, *_):
        record = self.record()
        if record is not None:
            self.set_crop(preset_crop(record['values'], self.media))

    def crop_edited(self, crop):
        record = self.record()
        if record is not None and not _same(crop, preset_crop(record['values'], self.media)):
            self.combo.blockSignals(True); self.combo.setCurrentIndex(self.combo.count() - 1); self.combo.blockSignals(False)

    @Slot(object)
    def set_source_image(self,image):
        if self.isVisible() and image is not None and not image.isNull():
            self.canvas.image=image;self.canvas.update()

    def result_options(self):
        record = self.record()
        if record is not None:
            return dict(mode='preset', id=record['id'], values=copy.deepcopy(record['values']))
        crop = self.canvas.crop.clamped()
        return dict(mode='crop', crop=(crop.x, crop.y, crop.width, crop.height))


def source_image(window, media):
    """First usable picture of the source for the crop dialog."""
    image = QImage(media.path) if media.kind == 'image' else QImage()
    if image.isNull() and media.kind == 'video':
        preview=getattr(window,'preview',None)
        for item in window.project.timeline:
            if item.media_id==media.id and preview is not None:
                image=preview.frames.get(preview.active_frames.get(item.id),QImage())
                if not image.isNull():break
    if image.isNull() and media.thumbnail:
        image = QImage(media.thumbnail)
    if image.isNull():
        image = QImage(max(16, media.width or 1280), max(16, media.height or 720), QImage.Format_RGB32)
        image.fill(QColor('black'))
    return image


def ask(window, assets):
    """Return the layout options, or None to place the media normally."""
    videos = [a for a in assets if getattr(a, 'kind', '') == 'video' and not getattr(a, 'timeline_preset', None)]
    if not videos:
        return None
    from .video_presets import records_from_settings
    dialog = AutoLayoutDialog(window, records_from_settings(window.settings), source_image(window, videos[0]), videos[0])
    from threading import Event
    cancel=Event();dialog.finished.connect(lambda *_:cancel.set())
    timer=QTimer(dialog);timer.setSingleShot(True)
    def decode():
        if cancel.is_set() or getattr(window,'_closing',False):return
        from .ui import Worker
        from .widgets import extract_frame
        worker=Worker(extract_frame,videos[0].path,max(0.,window.project.mark_in),window.settings.get('ffmpeg','ffmpeg'),cancel_check=cancel.is_set)
        worker.cancel_callback=cancel.set;worker.signals.result.connect(dialog.set_source_image);window.start_worker(worker)
    if videos[0].kind=='video':timer.timeout.connect(decode);timer.start(0)
    try:
        if dialog.exec() != QDialog.Accepted:return None
        return dialog.result_options()
    finally:
        cancel.set();timer.stop();dialog.deleteLater()
