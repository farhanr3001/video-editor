"""Build the small, shipped effects browser examples on a native Windows GPU.

Run on a private desktop with an isolated KINETIC_CUT_HOME. No owner projects,
settings, optional-model downloads or AI imagery are used. Existing effect
recipes/shaders render the demonstrations; the effect engines stay unchanged.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SIZE = (384, 216)
FPS = 30
VERSION = 1
TRANSITION_VERSION = 2


def run(only=None):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QImage
    from PySide6.QtCore import Qt
    from PIL import Image
    import av
    import numpy as np
    from kinetic_cut import effects_library as L
    from kinetic_cut.effects import CATALOG, MATRICES, EFFECT_ICONS, CATEGORY_STYLE
    from kinetic_cut.model import Project, ProjectSettings, MediaItem, TimelineItem, Transform
    from kinetic_cut.visual_fx import VISUAL_FX_SET, default_visual_fx
    from kinetic_cut.creative_effects import NAMES as CREATIVE, default_effect
    from kinetic_cut.transitions import Transition, default_transition_properties
    from kinetic_cut.gpu_export import recipe, worker
    from kinetic_cut.exporter import ExportPreset
    from kinetic_cut.motion_gpu_render import scene_image
    from kinetic_cut.motion import validate
    from kinetic_cut.motion_presets import PRESETS, build
    from kinetic_cut.icons import resource_path

    app = QApplication.instance() or QApplication([])
    for font in ('Inter-400-normal.ttf', 'Inter-600-normal.ttf'):
        QFontDatabase.addApplicationFont(str(ROOT/'assets/fonts'/font))
    target = ROOT/'assets/effects-library'; target.mkdir(exist_ok=True)
    output = ROOT/'build/effects-library-20261105/generated'; output.mkdir(parents=True, exist_ok=True)
    photos = {n: target/'samples'/(n+'.jpg') for n in ('lake', 'camera')}
    for path in photos.values(): assert path.is_file(), path
    metadata = L.manifest()
    settings = ProjectSettings(width=SIZE[0], height=SIZE[1], fps=FPS)
    preset = ExportPreset('Library sample', 'h264', 1.8, 128, 'Bundled, silent example')
    background = '#202a36'; ink = '#e9edf2'; accent = '#f09579'; blue = '#84b6d1'

    def text(identifier, value, x=192, y=108, size=34, **extra):
        node = dict(id=identifier, kind='text', text=value, font='Inter', font_size=size,
                    fill=ink, x=x, y=y, width=330, height=70)
        node.update(extra); return node

    def rect(identifier, x, y, w, h, fill, **extra):
        return dict(id=identifier, kind='rectangle', x=x, y=y, width=w, height=h,
                    fill=fill, **extra)

    def keys(*pairs): return [dict(time=t, value=v, interpolation='Linear') for t, v in pairs]

    def scene(nodes):
        return validate(dict(canvas=list(SIZE), nodes=[rect('backdrop', 192, 108, 384, 216, background), *nodes]))

    def source_scene(kind, name=''):
        if kind == 'cursor':
            from kinetic_cut.motion_assets import CURSOR
            return scene([rect('screen', 192, 108, 320, 174, '#303c4b', radius=7),
                rect('topbar', 192, 33, 320, 24, '#3c4a5b'),
                text('heading', 'WORKSPACE', 118, 34, 10),
                rect('side', 63, 120, 40, 115, '#273341', radius=4),
                rect('card', 182, 107, 153, 76, '#496775', radius=6),
                rect('detail', 182, 163, 153, 20, '#3c4a5b', radius=4),
                dict(id='pointer', kind='path', path=CURSOR, x=192, y=108,
                     scale=.75, scale_y=.75, fill='#ffffff', stroke='#162330', stroke_width=2)])
        if kind == 'tracked':
            return scene([dict(id='grid', kind='grid', width=330, height=170, x=192, y=108, fill='#3a495b', stroke_width=.8, columns=12, rows=6),
                dict(id='object', kind='rectangle', width=66, height=55, radius=8, x=192, y=108, fill=accent,
                     keyframes={'x':keys((0,116),(1.6,265),(3.2,116),(4.8,265))}),
                dict(id='outline', kind='rectangle', width=88, height=77, x=192, y=108, fill='none', stroke=blue, stroke_width=2,
                     keyframes={'x':keys((0,116),(1.6,265),(3.2,116),(4.8,265))}),
                text('label', 'TRACKED REGION', 192, 187, 11)])
        if kind == 'motion':
            return scene([rect('lane',192,137,324,2,'#465568'),
                dict(id='subject', kind='ellipse', width=42, height=42, y=108, fill=accent,
                     keyframes={'x':keys(*[(n*1.2,62 if n%2==0 else 322) for n in range(13)])}),
                text('movement', 'MOTION',192,48,18),
                dict(id='clock',kind='text',font='Inter',font_size=14,fill=ink,x=192,y=181,
                     width=160,height=35,text_mode='counter',number_decimals=1,number_suffix=' s',
                     keyframes={'number':keys((0,0),(14,14))})])
        return scene([rect('outline',192,108,238,130,'#2d3b4a',radius=10),
                      text('title', name,192,108,28)])

    def encode(path, frames):
        with av.open(str(path), 'w') as movie:
            stream = movie.add_stream('libx264', rate=FPS)
            stream.width, stream.height = SIZE; stream.pix_fmt = 'yuv420p'
            stream.options = {'crf':'20','preset':'fast','threads':'2'}
            for n, image in enumerate(frames):
                image = image.convertToFormat(QImage.Format_RGBA8888)
                rgba = np.frombuffer(image.constBits(), np.uint8).reshape(SIZE[1], image.bytesPerLine())[:, :SIZE[0]*4].reshape(SIZE[1], SIZE[0], 4)
                frame = av.VideoFrame.from_ndarray(rgba[:,:,:3].copy(), format='rgb24'); frame.pts=n
                for packet in stream.encode(frame): movie.mux(packet)
            for packet in stream.encode(): movie.mux(packet)

    def still_scene(raw, name):
        path = target/'samples'/(name+'.png')
        image = scene_image(raw, .8, SIZE, FPS)
        assert not image.isNull(); image.save(str(path)); return path

    cursor = still_scene(source_scene('cursor'), 'cursor')
    tracking = source_scene('tracked')
    tracked_still = still_scene(tracking, 'tracked')
    face_target = still_scene(scene([
        rect('target',192,76,78,84,'#3d586c',radius=12),
        rect('brackets',192,76,104,110,'none',stroke=blue,stroke_width=3,radius=4),
        text('label','FACE TARGET',192,177,13)]), 'focus-target')
    moving = target/'samples/moving-object.kcpreview'
    duration = 0.
    if moving.exists():
        with av.open(str(moving)) as existing: duration = float(existing.duration or 0)/av.time_base
    if duration < 13.9:
        raw=source_scene('motion'); encode(moving,(scene_image(raw,n/FPS,SIZE,FPS) for n in range(14*FPS)))

    def native(name, directory, temporal):
        source = photos['camera'] if name in ('Zoom to Object','Object Shake','Circle Facecam') else photos['lake']
        if name == 'Zoom to Cursor': source = cursor
        if name == 'Zoom to Tracked Region': source = tracked_still
        if name == 'Zoom to Face': source = face_target
        if name == 'Text Shake': source = still_scene(source_scene('type','MAKE IT MOVE'), 'text-shake')
        from kinetic_cut.animated_transitions import EXTRA_NAMES, descriptor
        if name in EXTRA_NAMES:
            # These existing preview shaders are newer than the source tree's
            # native DLL mode table. Use the existing Qt Quick path directly;
            # the library build must not change any installed effect engine.
            from kinetic_cut.gpu_transition_stage import TransitionStage
            from kinetic_cut.transitions import apply_easing
            stage=TransitionStage(*SIZE)
            trans=Transition('sample',name,'','video_1',.65,1.5,'left','right','center',default_transition_properties(name))
            data=descriptor(trans)
            left=QImage(str(photos['lake'])).scaled(*SIZE,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            right=QImage(str(photos['camera'])).scaled(*SIZE,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            result=directory/'sample.mp4'
            try:
                encode(result,(stage.render(left,right,apply_easing(max(0.,min(1.,(k/FPS-.65)/1.5)),data['easing']),data['mode'],data['params'],SIZE[0]/SIZE[1]) for k in range(round(3.2*FPS))))
            finally:stage.close();app.processEvents()
            return result,dict(engine='existing Qt Quick / Direct3D 11 transition shader',source='lake.jpg + camera.jpg')
        duration = 3.2 if temporal else .2
        speed = L.SPEEDS.get(name,1.)
        if name in L.SPEEDS: source = moving
        kind = 'video' if source == moving else 'image'
        media = MediaItem('source',str(source),kind,'Library sample',14 if kind=='video' else 6,960 if kind=='image' and source.suffix=='.jpg' else SIZE[0],540 if kind=='image' and source.suffix=='.jpg' else SIZE[1],FPS)
        item = TimelineItem('sample','source','video_1',0,duration,transform=Transform(x=.5,y=.5),speed=speed)
        project = Project(settings=copy.deepcopy(settings),media=[media],timeline=[item])
        if name in VISUAL_FX_SET:
            effect=default_visual_fx(name)
            if effect['timing_mode']!='entire_clip':effect['start_time']=.35
            if name=='Zoom to Object':effect.update(center_x=.6,center_y=.55)
            item.effects=[effect]
        elif name in CREATIVE:item.effects=[default_effect(name,item)]
        elif name in MATRICES:item.effects=[dict(name=name,enabled=True,amount=100.)]
        elif name=='Gaussian Blur':item.effects=[dict(name=name,enabled=True,horizontal=12.,vertical=12.,blend=100.,border='Reflect')]
        elif name=='Circle Facecam':item.transform.shape='circle'
        elif name in ('Black & White','Light Boost','Cinematic Contrast'):
            values={'Black & White':(True,0,1.08,0,.2),'Light Boost':(False,.08,1.08,1.06,.2),'Cinematic Contrast':(False,-.03,1.16,.84,.18)}[name]
            item.grayscale,item.brightness,item.contrast,item.saturation,item.sharpen=values
        elif name=='Fade In / Out':item.fade_in=.7;item.fade_out=.7
        elif name in L.TRANSITION_SET:
            right=copy.deepcopy(media);right.id='incoming';right.path=str(photos['camera']);right.width,right.height=960,540;right.kind='image'
            item.duration=duration/2
            next_item=TimelineItem('incoming','incoming','video_1',duration/2,duration/2,transform=Transform(x=.5,y=.5))
            project.media.append(right);project.timeline.append(next_item)
            project.transitions=[Transition('transition',name,'','video_1',duration/2-.75,1.5,item.id,next_item.id,'center',default_transition_properties(name))]
        job=recipe(project,preset,directory,False,{})
        config=directory/'job.json';config.write_text(json.dumps(job),encoding='utf-8')
        code=worker(config)
        status=json.loads(Path(job['status']).read_text())
        if code or status.get('state')!='Complete':raise RuntimeError(name+': '+repr(status))
        result=directory/'sample.mp4'
        # Raw H.264 packets have no container timestamps. Give them the sample's
        # exact cadence while remuxing; never re-encode the GPU-rendered frames.
        from kinetic_cut.process import run as command
        ffmpeg=ROOT/'build/distribution-stage/KineticCut/_internal/assets/tools/ffmpeg.exe'
        remux=command([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-r',str(FPS),
                       '-i',job['output'],'-c:v','copy','-an','-movflags','+faststart',str(result)],capture_output=True)
        if remux.returncode:raise RuntimeError(remux.stderr.decode(errors='replace'))
        return result, dict(engine='native D3D11 compositor',source=source.name,frames=status.get('frames'))

    def graphic_scene(name):
        if name in PRESETS:
            fields={'title':'STUDIO CAMERA'} if name!='Animated Total' else {'title':'TOTAL VIEWS','value':128000}
            if name in ('Product Price Card','Price Range Card','Product Showcase'):fields['image']=str(photos['camera'])
            return build(name,SIZE,3.2,fields)['scene']
        if name=='Motion Composition':
            return scene([text('heading','CREATE',192,92,42,keyframes={'y':keys((0,118),(.7,92))}),
                rect('line',192,135,140,3,accent,keyframes={'scale':keys((0,0),(.8,1)),'scale_y':keys((0,1),(.8,1))}),
                text('sub','IN MOTION',192,158,13,start=.4)])
        if name=='Object Tracking':return tracking
        if name=='Text':return scene([text('text','Your text here',192,108,28)])
        if name=='Headline':return scene([rect('card',192,108,280,100,'#ffffff',radius=3),text('headline','YOUR HEADLINE',192,108,26,fill='#13171e',bold=True)])
        if name=='Timer / Countdown':
            return scene([dict(id='number',kind='text',x=192,y=105,font='Inter',font_size=56,fill=ink,width=300,height=100,text_mode='counter',number_decimals=0,number_prefix='00:0',keyframes={'number':keys((0,5),(3.2,2))})])
        if name=='Progress Bar':return scene([rect('track',192,108,280,16,'#3d4b5c',radius=8),rect('progress',192,108,280,16,blue,radius=8,keyframes={'width':keys((0,14),(3.2,280)),'x':keys((0,59),(3.2,192))})])
        if name in ('Circle','Square','Rectangle'):
            return scene([dict(id='shape',kind='ellipse' if name=='Circle' else 'rectangle',x=192,y=108,width=116 if name!='Rectangle' else 230,height=116,fill='none',stroke=accent,stroke_width=5,radius=3)])
        if name=='Pointing Arrow':return scene([dict(id='arrow',kind='path',x=192,y=108,path=[['M',-95,0],['L',95,0],['M',53,-38],['L',95,0],['L',53,38]],fill='none',stroke=blue,stroke_width=7)])
        if name=='Speech Bubble / Quote Card':return scene([rect('quote',192,103,278,108,'#3a4c5b',radius=12),text('quote-text','A moment worth sharing',192,103,19)])
        if name=='Callout Badge':return scene([rect('badge',192,108,220,68,accent,radius=28),text('badge-text','WAIT FOR IT',192,108,22,fill='#20242d',bold=True)])
        # Static utility/analysis/audio cards: a specific icon or visual mark,
        # never a fake camera animation or a photographic face.
        from kinetic_cut.icons import lucide_icon
        group=L.GROUPS[name];symbol=EFFECT_ICONS.get(name,CATEGORY_STYLE[group][0])
        if group=='Face Filters':symbol={'Big Eyes':'eye','Big Nose':'move','Big Lips':'speech','Face Twist':'rotate-cw','Custom Face':'sliders-horizontal','Puppy Ears & Nose':'bone','Cat Ears & Whiskers':'cat','AR Plague Mask':'venetian-mask','AR Pixel Glasses':'glasses'}[name]
        icon_path=target/'samples'/('icon-'+L.asset_key(name)+'.png')
        lucide_icon(symbol,blue,72).pixmap(72,72).save(str(icon_path))
        nodes=[dict(id='symbol',kind='image',source=str(icon_path),x=192,y=91,width=70,height=70),text('label',name,192,160,16)]
        if group=='Audio':
            nodes=[]
            for n in range(36):
                value=(.2+.8*abs(math.sin(n*.67)))*55
                if name=='Low Cut' and n<10:value*=.25
                if name=='Fade In / Out':value*=min(1,n/7,(35-n)/7)
                nodes.append(rect('bar'+str(n),65+n*7.2,99,3,value,blue if n<18 else accent,radius=1))
            if name=='Fade In / Out':
                nodes.extend([dict(id='fade-envelope',kind='path',x=0,y=0,path=[['M',65,99],['L',115,56],['L',267,56],['L',317,99]],fill='none',stroke=accent,stroke_width=2),
                              rect('playhead',65,99,2,100,ink,keyframes={'x':keys((0,65),(3.2,317))})])
            nodes.append(text('label',name,192,166,18))
        return scene(nodes)

    names=[name for name in L.ALL_NAMES if not only or name in only]
    failed=[];started=time.monotonic()
    for n,name in enumerate(names):
        try:
            key=L.asset_key(name);temporal=name in L.ANIMATED_NAMES
            current=metadata.get(name,{})
            version=3 if name=='Fade In / Out' else TRANSITION_VERSION if name in L.TRANSITION_SET or name in L.SPEEDS or L.GROUPS[name]=='Face Filters' or name=='Progress Bar' else VERSION
            if current.get('version')==version and L.asset_path(current,'thumbnail') and (not temporal or L.asset_path(current,'preview')):
                continue
            directory=output/key;directory.mkdir(exist_ok=True)
            native_name=(name in VISUAL_FX_SET or name in CREATIVE or name in MATRICES or name in L.SPEEDS or name in L.TRANSITION_SET or name in ('Gaussian Blur','Circle Facecam','Black & White','Light Boost','Cinematic Contrast'))
            if native_name:
                movie,detail=native(name,directory,temporal)
            else:
                raw=graphic_scene(name)
                movie=directory/'sample.mp4'
                if temporal:encode(movie,(scene_image(raw,k/FPS,SIZE,FPS) for k in range(round(3.2*FPS))))
                else:
                    image=scene_image(raw,1.2,SIZE,FPS);image.save(str(target/(key+'.webp')),'WEBP',90)
                detail=dict(engine='Qt Quick / Direct3D 11 motion stage',source='designed motion graphics')
            if temporal or native_name:
                with av.open(str(movie)) as source:
                    decoded=list(source.decode(video=0))
                assert decoded,name
                thumb_index = min(len(decoded)-1, max(0, round(len(decoded)*(.46 if temporal else .5))))
                thumb = decoded[thumb_index].to_image()
                thumb.save(target/(key+'.webp'),quality=89,method=6)
                if temporal:
                    import shutil
                    shutil.copy2(movie,target/(key+'.kcpreview'))
                detail['decoded_frames']=len(decoded)
            metadata[name]=dict(version=version,category=L.GROUPS[name],thumbnail=key+'.webp',preview=key+'.kcpreview' if temporal else None,temporal=temporal,**detail)
            pending=target/'manifest.pending.json';pending.write_text(json.dumps(dict(schema=1,effects=metadata),ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(target/'manifest.json')
            print(json.dumps(dict(done=n+1,total=len(names),effect=name,animated=temporal,seconds=round(time.monotonic()-started,1))),flush=True)
        except Exception as error:
            import traceback
            traceback.print_exc();failed.append(dict(effect=name,error=str(error)))
    report=dict(passed=not failed and all(name in metadata for name in names),count=len(metadata),expected=len(L.ALL_NAMES),failures=failed,seconds=time.monotonic()-started)
    (output.parent/'asset-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--only',nargs='*');args=parser.parse_args()
    raise SystemExit(run(args.only))
