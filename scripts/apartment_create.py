"""Reproducible edit decisions for the user's apartment short, never source writes."""
import os,sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/apartment-edit'
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('KINETIC_CUT_HOME',str(OUT/'home'))
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,ProjectSettings,TimelineItem,Crop,Transform,Caption,CaptionStyle,uid
from kinetic_cut.media import probe
from kinetic_cut.captions import _from_segments
from kinetic_cut.exporter import export,PRESETS

app=QApplication([])
path=ROOT/'Apartment Tour - xQc.kcut'
if path.exists():raise SystemExit('Project already exists; refusing to replace it.')
p=Project(name='Apartment Tour | xQc',settings=ProjectSettings(fps=60,blur=32,background_brightness=.85))
p.video_tracks=['video_1','video_2','video_3']; p.audio_tracks=['audio_1']
p.track_names={'video_1':'Ambient blur','video_2':'Apartment tour','video_3':'Webcam reaction','audio_1':'Original dialogue'}
p.media=[probe(f'C:/Users/F/Videos/NoPixel5/new house pt{n}.mp4') for n in range(1,4)]
p.subtitle_style=CaptionStyle(font='Nirmala UI',size=64,color='#FFFFFF',highlight='#FFD05A',outline_width=5,animation='punch',position_y=.815,uppercase=True,shadow=2)
# No repeated content: part 2 starts after its overlap with part 1. Part 3's
# price beat is absent from the selected part-2 footage, despite source overlap.
decisions=[
    (1,1.0,3.5,'Courtyard hook',False),
    (2,17.9,22.0,'First impression',True),
    (2,24.1,28.8,'Working elevator reaction',True),
    (2,36.3,44.3,'Door reveal and balcony',True),
    (3,64.0,67.0,'Quick room look',False),
    (3,14.7,16.8,'The price',True),
    (3,25.25,27.75,'Verdict',True),
    (3,58.15,60.1,'Easy sign-off',True),
]
cursor=0.; edl=[]
for number,begin,end,description,speech in decisions:
    begin=round(begin*60)/60; end=round(end*60)/60; duration=end-begin
    media=p.media[number-1]; link=uid()
    # Explicit video/audio separation: clones stay linked and audio plays once.
    bg=TimelineItem(uid(),media.id,'video_1',cursor,duration,begin,link,role='background',link_id=link)
    gameplay=TimelineItem(uid(),media.id,'video_2',cursor,duration,begin,link,
        crop=Crop(.215,0,.69,.97),transform=Transform(x=.5,y=.625,scale=1080/(1920*.69*(1920/1080))),link_id=link)
    cam=TimelineItem(uid(),media.id,'video_3',cursor,duration,begin,link,
        crop=Crop(0,225/1080,396/1920,305/1080),
        transform=Transform(x=.5,y=.19,scale=800/(396*(1920/1080)*.92)),role='facecam',link_id=link,is_webcam=True)
    sound=TimelineItem(uid(),media.id,'audio_1',cursor,duration,begin,link,role='audio',link_id=link,
        fade_in=.012,fade_out=.018,gain_db=6 if speech else -3)
    p.timeline.extend([bg,gameplay,cam,sound])
    if speech:
        rows=json.loads((OUT/f'transcript{number}.json').read_text())
        selected=[]
        for row in rows:
            words=[dict(w) for w in row['words'] if begin <= w['start'] < end and w['end'] <= end+.03]
            if not words:continue
            if number==2 and 25<row['start']<26:
                words[0]['text']='A'
            for word in words:
                word['text']=word['text'].strip().rstrip('.')
                if word['text'].casefold()=='shit':word['text']='sh*t'
            selected.append(dict(start=words[0]['start'],end=words[-1]['end'],text=' '.join(w['text'] for w in words),words=words))
        captions=_from_segments(selected,cursor-begin,p.subtitle_style,words_per_caption=3,hold_seconds=.12)
        for caption in captions:caption.end=min(caption.end,cursor+duration)
        p.captions.extend(captions)
    edl.append(dict(part=number,source_in=begin,source_out=end,timeline_in=cursor,timeline_out=cursor+duration,purpose=description))
    cursor+=duration

def card(start,end,text,size=55,color='#FFD05A'):
    style=copy.deepcopy(p.subtitle_style); style.size=size; style.color=color; style.position_y=.375; style.animation='pop'
    p.captions.append(Caption(uid(),start,end,text,style,customize=True))
card(0,2.45,'xQc\'s NEW GTA APARTMENT',53)
room=edl[4]; card(room['timeline_in'],room['timeline_out']-.05,'THE ROOM TOUR',52)
# Keep price together rather than splitting a single amount into separate cards.
price=edl[5]; p.captions=[c for c in p.captions if c.is_hook or not(price['timeline_in']<=c.start<price['timeline_out'])]
style=copy.deepcopy(p.subtitle_style); style.size=80; style.color='#FFD05A'
p.captions.append(Caption(uid(),price['timeline_in']+.6,price['timeline_out']-.1,'125,000?',style,customize=True))
p.captions.sort(key=lambda c:c.start)
p.mark_out=p.duration; p.playhead=0
p.save(path)
(OUT/'edit-decisions.json').write_text(json.dumps(edl,indent=2))
print(f'Saved {path}; {p.duration:.3f} seconds, {len(p.captions)} captions',flush=True)
output=ROOT/'exports/Apartment Tour - xQc.mp4'
if output.exists():raise SystemExit('Output already exists; refusing to replace it.')
export(p,str(output),PRESETS['YouTube Shorts · Quality'],progress=lambda v,t:print(f'{v:.3f} {t}',flush=True))
print('Export complete',flush=True)
