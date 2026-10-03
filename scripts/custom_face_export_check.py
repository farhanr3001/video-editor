"""Exercise the same cached Custom Face renderer used by final export."""
import json
import sys
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from kinetic_cut.model import MediaItem,Project,TimelineItem
from kinetic_cut.vision_effects import fingerprint,prepare_export,valid_effect


def main():
    source=ROOT/'build/face-filter-check/input.mp4'
    analysis_root=ROOT/'build/custom-face-check/analysis'
    media=MediaItem('sample',str(source),'video',source.name,2,640,360)
    item=TimelineItem('effect-clip','sample','video_1',0,2)
    info=json.loads((analysis_root/'info.json').read_text())
    info.update(root=str(analysis_root),source=fingerprint(media),
                crop=vars(item.crop.clamped()),source_start=0,source_end=2)
    item.effects=[dict(name='Custom Face',enabled=True,analysis=info,
                       morph={'nose_size':140,'eye_spacing':65,'left_eye':50,'right_eye':50},
                       skin_color='#c38876',skin_strength=70)]
    project=Project(media=[media],timeline=[item])
    assert valid_effect(item.effects[0],media,item)
    renders=prepare_export(project,'ffmpeg',None,threading.Event())
    output=Path(renders[item.id])
    assert output.is_file() and output.stat().st_size>100_000
    print(output,output.stat().st_size)


if __name__=='__main__':
    main()
