"""Exact sparse native-graphic rasters consumed directly by the GPU worker."""
import copy,json,math,sys
from pathlib import Path


def samples(project,item,frames):
    fps=project.settings.fps
    if frames<=0:return []
    result={0,frames-1}
    def interval(a,b):
        first=max(0,math.floor(a*fps)-1);last=min(frames-1,math.ceil(b*fps)+1)
        if last>=first:result.update(range(first,last+1))
    def curves(data,convert=lambda t:t,tail=0.):
        for keys in data.get('keyframes',{}).values():
            keys=sorted(keys,key=lambda key:key['time'])
            if len(keys)==1:interval(convert(keys[0]['time']),convert(keys[0]['time']+tail))
            for left,right in zip(keys,keys[1:]):
                # Identical key values form an exact hold, even if the keys
                # are many seconds apart. Easing cannot change a zero delta.
                if left.get('value')!=right.get('value'):interval(convert(left['time']),convert(right['time']+tail))
    curves(item.__dict__)
    if item.fade_in:interval(0,item.fade_in)
    if item.fade_out:interval(item.duration-item.fade_out,item.duration)
    from .motion_presets import is_motion
    if item.role!='graphic' or not is_motion(item.graphic_type):
        # Only arrows have no implicit time-driven drawing in this branch.
        if item.role!='graphic' or 'arrow' not in item.graphic_type.lower():return list(range(frames))
        return sorted(result)
    from .motion import validate
    scene=validate(item.graphic_data.get('scene',{}))
    if item.speed<=0:return list(range(frames))
    convert=lambda t:(t-item.in_point)/item.speed
    blur=scene.get('motion_blur',{});tail=blur.get('shutter',180)/360/max(1,fps) if blur.get('samples',1)>1 else 0.
    for node in scene['nodes']:
        # Include hidden nodes conservatively; no scene mutation/cache heuristics.
        curves(node,convert,tail)
        if node.get('mask'):curves(node['mask'],convert,tail)
        for boundary in (node.get('start',0),node.get('end',1e5)):interval(convert(boundary),convert(boundary+tail))
        mode=node.get('text_mode','none')
        if mode=='typewriter' and node.get('caret',False):return list(range(frames))
        if mode in ('character','word','typewriter','rolling'):
            duration=node.get('entry_duration',.9 if mode=='rolling' else .4)
            if mode!='rolling':duration+=len(node.get('text',''))*node.get('stagger',.06 if mode=='typewriter' else .04)
            interval(convert(node.get('start',0)),convert(node.get('start',0)+duration+tail))
    return sorted(result)


def layers(project,items,directory):
    fps=project.settings.fps;width,height=project.settings.width,project.settings.height
    groups={}
    for item in items:
        if item.muted or not project.track_states.get(item.track,{}).get('visible',True):continue
        groups.setdefault(item.track,[]).append(item)
    output=[];sources={}
    for index,(track,group) in enumerate(groups.items()):
        first=min(math.ceil(i.start*fps-1e-7) for i in group);last=max(math.ceil((i.start+i.duration)*fps-1e-7) for i in group)
        count=last-first
        if count<=0:continue
        if count>250000:raise ValueError('Native graphic stream exceeds sample budget')
        selected={0,count-1}
        for item in group:
            begin=math.ceil(item.start*fps-1e-7);end=math.ceil((item.start+item.duration)*fps-1e-7)
            for n in samples(project,item,end-begin):selected.add(begin-first+n)
            for n in (begin-first-1,begin-first,end-first-1,end-first):
                if 0<=n<count:selected.add(n)
            for node in item.graphic_data.get('scene',{}).get('nodes',[]):
                if node.get('kind')=='image' and not Path(node.get('source','')).is_file():raise ValueError('Motion image is missing: '+str(node.get('source','')))
        stage=copy.copy(project);stage.timeline=group;stage.captions=[];stage.transitions=[]
        path=Path(directory)/f'native-graphics-{index}.json';marker=str(path.with_suffix('.rgba'));selected=sorted(selected)
        path.write_text(json.dumps(dict(project=stage.to_dict(),first=first,frames=count,sample_frames=selected,native_animation=True)),encoding='utf-8')
        command=[sys.executable]+([] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve().parent.parent/'main.py')])+['--preview-effect-source',str(path)]
        sources[marker]=dict(command=command,width=width,height=height,fps=fps,frames=count,sample_frames=selected,log=str(path.with_suffix('.log')))
        output.append(dict(id=f'__native_graphics_{index}',track=track,path=marker,cpu=True,still=False,clock=marker,start=first/fps,end=last/fps,in_point=0.,speed=1.,size=[width,height],crop=[0,0,1,1],box=[0,0,width,height],opacity=1.,operations=[]))
    return output,sources
