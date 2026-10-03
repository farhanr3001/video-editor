"""Create a separate, unanimated demo; author its keys through the app UI."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kinetic_cut.model import Project,TimelineItem,Transform

root=Path(__file__).resolve().parents[1]
target=root/'Keyframe Punch Zoom Demo.kcut'
if target.exists():raise SystemExit('Demo already exists; refusing to overwrite')
source=Project.load(root/'Apartment Tour - xQc.kcut')
media=copy.deepcopy(source.media[0])
assert Path(media.path).is_file()
p=Project(name='Keyframe Punch Zoom Demo',media=[media])
p.settings.width=1280; p.settings.height=720; p.settings.fps=60
p.timeline=[TimelineItem('demo_video',media.id,'video_1',0,7,12,transform=Transform(.5,.5,1),link_id='demo_pair'),
            TimelineItem('demo_audio',media.id,'audio_1',0,7,12,link_id='demo_pair')]
p.save(target)
print(target)
