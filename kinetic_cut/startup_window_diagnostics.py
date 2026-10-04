"""Exercise reuse of the affected controls after the editor is already visible."""
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from .model import CaptionStyle, MediaItem, Project, TimelineItem


def workflows(window, audit):
    from .caption_style_dialog import CaptionStyleDialog
    from .keyframe_editor import KeyframeEditor
    from .vfx_timing_dialog import VFXTimingDialog
    from .render_queue import RenderJobCard
    from .workspace import set_page
    media = MediaItem('fixture', 'missing-fixture.png', 'image', 'Fixture', 10, 1920, 1080)
    item = TimelineItem('item', media.id, 'video_1', 0, 5)
    window.set_project(Project(media=[media], timeline=[item]))
    window.timeline.select_ids({item.id}, item.id)
    result = []
    for create in (lambda:CaptionStyleDialog(CaptionStyle(), {}, window),
                   lambda:KeyframeEditor(window, item),
                   lambda:VFXTimingDialog(window, item, {'name':'Zoom In', 'properties':{}})):
        dialog = create()
        audit.allow(dialog); dialog.show(); QApplication.processEvents()
        result.append(type(dialog).__name__)
        dialog.close(); dialog.deleteLater(); QApplication.processEvents()
    set_page(window, 1); QApplication.processEvents()
    host = QWidget(window); layout = QVBoxLayout(host)
    for state in ('Queued', 'Cancelled', 'Failed', 'Rendering', 'Completed'):
        job = dict(state=state, project=window.project, output='fixture.mp4')
        row = RenderJobCard(job, 1, lambda _:None); layout.addWidget(row)
        host.show(); QApplication.processEvents()
        assert row.remove_button.isVisible() == (state in {'Queued', 'Cancelled', 'Failed'})
    host.hide(); host.deleteLater()
    set_page(window, 2); QApplication.processEvents()
    set_page(window, 0); QApplication.processEvents()
    result.extend(['Render queue states', 'Edit / Deliver / Phone page switches'])
    return result
