"""Render two accessory stills from a local 2-second analysis sample."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QImage
from kinetic_cut.model import MediaItem, TimelineItem, Project
from kinetic_cut.vision_effects import apply, fingerprint, prepare_export


def main():
    root = Path(sys.argv[1]).resolve()
    source = root/'input.mp4'
    image = QImage(str(root/'frame.png'))
    media = MediaItem('visual-check', str(source), 'video', source.name, 2, image.width(), image.height())
    item = TimelineItem('visual-check-item', media.id, 'video_1', 0, 2)
    info = json.loads((root/'analysis'/'info.json').read_text())
    analysis = dict(info, root=str(root/'analysis'), source=fingerprint(media),
                    crop=vars(item.crop.clamped()), source_start=0, source_end=2)
    for name, output in (('Puppy Ears & Nose','puppy.png'),
                         ('Cat Ears & Whiskers','cat.png'),
                         ('AR Plague Mask','ar-plague.png'),
                         ('AR Pixel Glasses','ar-glasses.png')):
        item.effects = [dict(name=name, enabled=True, analysis=analysis)]
        if not apply(image,item,media,1.0).save(str(root/output)):
            raise RuntimeError(f'Could not save {output}')
    if '--export-check' in sys.argv:
        import threading
        project=Project(media=[media],timeline=[item])
        project.settings.fps=15
        rendered=prepare_export(project,'ffmpeg',None,threading.Event())
        if not Path(rendered[item.id]).is_file():
            raise RuntimeError('Effect export cache was not created')
        print('Export effect cache:', rendered[item.id])


if __name__ == '__main__':
    main()
