"""Editor-side MCP operations. All entry points run on the Qt GUI thread."""
import copy
import hashlib
import json
import math
import time
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QAbstractButton, QAbstractSlider,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QLabel,
    QDialog, QTabWidget, QWidget)
from .model import Project, ProjectSettings, TimelineItem, MediaItem, Caption, CaptionStyle, Crop, Transform, uid


def tool(name, description, properties=None, required=(), readonly=False):
    return dict(name=name,description=description,inputSchema=dict(type='object',properties=properties or {},required=list(required),additionalProperties=False),
                annotations=dict(readOnlyHint=readonly,destructiveHint=not readonly,openWorldHint=False))

S={'type':'string'}; N={'type':'number'}; B={'type':'boolean'}; O={'type':'object'}
COMMANDS=('add_title_object','apply_effect_to','viewer_command','timeline_command',
    'split_selected','delete_selected','delete_gaps','timeline_clipboard',
    'apply_vertical','generate_captions','generate_tts_dialogue','apply_visual_fx',
    'set_caption_style','apply_vertical_framing',
    'remove_silence','highlight_reel','instant_package',
    'toggle_play','stop','mark_in','mark_out','add_video_track','add_audio_track',
    'frame_source','download_media','apply_transition','remove_transition',
    'add_graphic_object','remove_media','open_keyframes','open_motion_composition')
TOOLS=[
    tool('get_state','Read current project, revision, selection, playback and task status. section=summary omits the full project.',{'section':{'type':'string','enum':['all','summary']}},readonly=True),
    tool('get_capabilities','Discover every editable data field, edit operation, available effect and tool workflow.',readonly=True),
    tool('apply_edits','Apply an atomic batch as ONE undo step. Requires the revision from get_state. See get_capabilities for operations. All times in seconds.',{'revision':S,'operations':{'type':'array','items':O,'minItems':1,'maxItems':500}},('revision','operations')),
    tool('synthesize_dialogue','Synthesize voiceover speech using local neural TTS (Adam Narrator or other voices) and place it directly on the timeline with waveform and caption-ready role="source_audio".',{'text':S,'voice':{'type':'string','default':'adam-narrator'},'start':N,'track':S,'rate':{'type':'integer','minimum':-50,'maximum':50},'pitch':{'type':'integer','minimum':-20,'maximum':20},'gain_db':N},('text',)),
    tool('apply_visual_fx','Apply and configure a Visual FX (Punch Zoom, Camera Shake, Crash Zoom, etc.) with custom parameters on any timeline clip in one call.',{'item_id':S,'effect':S,'properties':O},('item_id','effect')),
    tool('apply_transition','Apply and configure a video transition (Cross Dissolve, Dip to Color / White Flash, Wipe Left/Right/Up/Down, Push Left/Right/Up/Down, Slide In/Out, Zoom In, Digital Glitch, etc.) between clips or on an edit cut in one call.',{'name':S,'track':S,'left_item_id':S,'right_item_id':S,'cut_time':N,'duration':N,'alignment':{'type':'string','enum':['center','start','end']},'properties':O},('name',)),
    tool('add_graphic','Add a vector graphic or editable Motion Composition. For compositions use properties.scene; discover its schema with get_capabilities.',{'graphic_type':{'type':'string','enum':['Motion Composition','Circle','Pointing Arrow','Square','Rectangle','Timer / Countdown','Speech Bubble / Quote Card','Progress Bar','Callout Badge']},'track':S,'start':N,'duration':N,'properties':O},('graphic_type',)),
    tool('set_caption_style','Apply curated viral subtitle style presets (crime_red, viral_yellow, cyber_cyan, mrbeast_gold, clean_card) or customize font, colors, animation, size, glow, and lower-third position across captions in one call.',{'preset':{'type':'string','enum':['crime_red','viral_yellow','cyber_cyan','mrbeast_gold','clean_card']},'properties':O,'caption_ids':{'type':'array','items':S}}),
    tool('apply_vertical_framing','Format and align clips for 9:16 vertical video shorts: vertically center foreground clips (y=0.5), configure ambient background fill layers (role="background"), and optionally adjust framing scale.',{'mode':{'type':'string','enum':['center_and_fill','fit_width','fill_916']},'foreground_track':S,'background_track':S,'scale':N}),
    tool('get_timeline_summary','Return a concise structured summary of timeline tracks, clips, in/out timings, audio levels, active effects, subtitle cards, and video transitions.',readonly=True),
    tool('import_media','Index local media asynchronously without duplicating source files. Returns a job ID. Poll get_jobs, then use insert_media in apply_edits.',{'paths':{'type':'array','items':S,'minItems':1,'maxItems':100}},('paths',)),
    tool('download_media','Download video or audio from YouTube, YouTube Shorts, TikTok, TikTok Sounds, Instagram, or Twitter/X and optionally auto-import into the project media bin.',{'url':S,'mode':{'type':'string','enum':['video','audio'],'default':'video'},'target_res':S,'cookies_path':S,'auto_import':B,'wait':B},('url',)),
    tool('get_jobs','Read import/action jobs and render queue states. Complete is the only successful render terminal state.',readonly=True),
    tool('seek','Seek the timeline in seconds; then request get_preview. Decode may still be pending.',{'seconds':N},('seconds',)),
    tool('get_preview','Return an image of the current viewer or full editor. Includes actual playhead and frame status. Seek separately; sample again if decoding is pending.',{'area':{'type':'string','enum':['preview','workspace']},'max_width':{'type':'integer','minimum':160,'maximum':1920}},readonly=True),
    tool('select_items','Select timeline clips, captions, or transitions for editor commands and inspector controls.',{'ids':{'type':'array','items':S},'caption_ids':{'type':'array','items':S},'transition_id':S}),
    tool('history','Undo or redo an edit.',{'direction':{'type':'string','enum':['undo','redo']}},('direction',)),
    tool('project_file','New/open/save/checkpoint a project. Switches checkpoint current work first. Saves require explicit path; overwrite=false protects existing files.',{'operation':{'type':'string','enum':['new','open','save','checkpoint']},'path':S,'name':S,'overwrite':B},('operation',)),
    tool('queue_export','Queue a snapshot in Deliver. Rendering is asynchronous; poll get_jobs. Does not retry failed jobs.',{'path':S,'encoder':{'type':'string','enum':['Auto','CPU','NVIDIA','AMD','Intel']},'codec':{'type':'string','enum':['h264','h265']},'bitrate_mbps':N,'burn_subtitles':B,'export_audio':B,'start':B,'overwrite':B},('path',)),
    tool('render_control','Start queued renders or cancel the active render.',{'operation':{'type':'string','enum':['start','cancel']}},('operation',)),
    tool('editor_command','Run an existing editor workflow: effects, titles, crop, captions, silence/vocal processing, placement, clipboard or transport. Discover argument names with get_capabilities. Returns a command job; inspect_ui handles any prompts.',{'command':{'type':'string','enum':list(COMMANDS)},'arguments':O},('command',)),
    tool('inspect_ui','Discover live editor controls, menus and open dialogs, with target IDs for ui_control. Includes full effects inspector. No screen coordinates needed.',readonly=True),
    tool('ui_control','Operate any advertised live UI control. click returns an action job to avoid blocking on dialogs. Set controls by value; choose combo/tab index or text. Some workflows require download/output prompts.',{'target':S,'operation':{'type':'string','enum':['click','set','focus','accept','reject']},'value':{}},('target','operation')),
]


def revision(project):
    data=project.to_dict(); data.pop('playhead',None); data.pop('modified_at',None)
    return hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()[:20]


def merge(target, values):
    if not isinstance(values,dict):raise ValueError('values must be an object')
    for key,value in values.items():
        if key not in target:raise ValueError('Unknown field: '+key)
        if isinstance(target[key],dict) and isinstance(value,dict):
            # Effect dictionaries and track maps have extensible keys.
            target[key].update(copy.deepcopy(value))
        else:target[key]=copy.deepcopy(value)


def validate(project):
    def types(obj):
        if not is_dataclass(obj):return
        for field in fields(obj):
            value=getattr(obj,field.name); annotation=str(field.type)
            expected={'str':str,'bool':bool,'int':int,'float':(int,float)}.get(annotation)
            # Font sizes/outlines are continuous in the inspector and scaled
            # export snapshots even though older dataclass hints said int.
            if isinstance(obj,CaptionStyle) and annotation=='int':expected=(int,float)
            if expected and (not isinstance(value,expected) or annotation in {'int','float'} and isinstance(value,bool)):
                raise ValueError('Invalid type for '+field.name)
            if annotation.startswith('list') and not isinstance(value,list):raise ValueError('Expected list: '+field.name)
            if annotation.startswith('dict') and not isinstance(value,dict):raise ValueError('Expected object: '+field.name)
            if is_dataclass(value):types(value)
            elif isinstance(value,list):
                for item in value:types(item)
    types(project)
    def finite(value):
        if isinstance(value,float) and not math.isfinite(value):raise ValueError('Non-finite numeric value')
        if isinstance(value,dict):
            for v in value.values():finite(v)
        elif isinstance(value,list):
            for v in value:finite(v)
    finite(project.to_dict())
    for collection in (project.media,project.timeline,project.captions,project.transitions):
        ids=[x.id for x in collection]
        if any(not isinstance(x,str) or not x for x in ids) or len(ids)!=len(set(ids)):raise ValueError('IDs must be unique nonempty strings')
    s=project.settings
    if not (64<=s.width<=8192 and 64<=s.height<=8192 and 1<=s.fps<=240):raise ValueError('Invalid project resolution or frame rate')
    tracks=project.video_tracks+project.audio_tracks
    if len(tracks)!=len(set(tracks)) or not project.video_tracks or not project.audio_tracks:raise ValueError('Invalid track lists')
    for item in project.timeline:
        if item.track not in tracks:raise ValueError('Unknown track: '+item.track)
        if item.start<-1e-7 or item.duration<.01 or item.in_point<-1e-7 or not .01<=item.speed<=100:raise ValueError('Invalid clip timing/speed')
        if not 0<=item.opacity<=100 or item.fade_in<0 or item.fade_out<0:raise ValueError('Invalid opacity/fade')
        if item.crop != item.crop.clamped():raise ValueError('Crop must fit normalized source bounds')
        if not .001<=item.transform.scale<=100 or not .001<=item.transform.effective_scale_y<=100:raise ValueError('Invalid transform scale')
        if item.role in {'title', 'graphic'}:
            if item.track not in project.video_tracks:raise ValueError('Titles and graphics require video tracks')
            if item.role=='graphic' and item.graphic_type.lower() in ('motion','motion composition'):
                from .motion import validate
                item.graphic_data['scene']=validate(item.graphic_data.get('scene',{}))
        else:
            media=project.media_by_id(item.media_id)
            if media is None:raise ValueError('Clip references missing media')
            if media.kind=='audio' and item.track not in project.audio_tracks:raise ValueError('Audio media requires an audio track')
            if media.kind=='image' and item.track not in project.video_tracks:raise ValueError('Images require a video track')
            if media.kind!='image' and item.in_point+item.source_duration>media.duration+.05:raise ValueError('Clip extends past source duration')
    for c in project.captions:
        if c.start<-1e-7 or c.end<=c.start:raise ValueError('Invalid caption timing')
    for tr in project.transitions:
        if tr.track not in project.video_tracks:raise ValueError('Transitions require a video track')
        if tr.start<-1e-7 or not 0.05<=tr.duration<=10.0:raise ValueError('Invalid transition timing/duration')


def edited(project, operations):
    if not isinstance(operations,list) or not 1<=len(operations)<=500:raise ValueError('Provide 1–500 operations')
    stage=copy.deepcopy(project); created=[]
    for op in operations:
        kind=op.get('op'); values=op.get('values',{})
        if kind in {'add','update','remove'}:
            collection=op.get('collection')
            if collection not in {'timeline','captions','transitions'}:raise ValueError('Use timeline, captions, or transitions; import source media with import_media')
            raw=stage.to_dict(); rows=raw[collection]; identifier=op.get('id')
            if kind=='add':
                identifier=identifier or uid()
                if collection=='timeline':
                    base=asdict(TimelineItem(identifier,'',stage.video_tracks[-1],0,5,role='title'))
                    if values.get('graphic_type','').lower() in ('motion','motion composition'):base['transform']['y']=.5
                elif collection=='captions':
                    base=asdict(Caption(identifier,0,1,''))
                else:
                    from .transitions import Transition, default_transition_properties, SUBSECTION_BY_TRANSITION
                    name=values.get('name','Cross Dissolve')
                    category=values.get('category') or SUBSECTION_BY_TRANSITION.get(name,'Dissolve')
                    track=values.get('track',stage.video_tracks[0])
                    dur=float(values.get('duration',0.80))
                    start=float(values.get('start',0.0))
                    base=asdict(Transition(identifier,name,category,track,start,dur,properties=default_transition_properties(name)))
                merge(base,values); base['id']=identifier; rows.append(base); created.append(identifier)
            else:
                target=next((x for x in rows if x['id']==identifier),None)
                if target is None:raise ValueError('Unknown item: '+str(identifier))
                track_name=target.get('track','subtitle_1')
                if stage.track_states.get(track_name,{}).get('locked'):raise ValueError('Unlock the track before editing')
                if kind=='remove':rows.remove(target)
                else:
                    if 'id' in values:raise ValueError('Item IDs cannot be changed')
                    merge(target,values)
            stage=Project.from_dict(raw)
        elif kind=='settings':
            raw=stage.to_dict(); merge(raw['settings'],values); stage=Project.from_dict(raw)
        elif kind=='subtitle_style':
            raw=stage.to_dict(); merge(raw['subtitle_style'],values); stage=Project.from_dict(raw)
        elif kind=='rename_project':stage.name=str(op['name'])
        elif kind=='add_track':
            if op.get('kind') not in {'video','audio'}:raise ValueError('Track kind must be video or audio')
            created.append(stage.add_track(op['kind']))
        elif kind=='track':
            track=op['track']
            if track not in stage.video_tracks+stage.audio_tracks+['subtitle_1']:raise ValueError('Unknown track')
            if 'name' in op:stage.track_names[track]=str(op['name'])
            states=op.get('states',{})
            if set(states)-{'locked','visible','muted'} or any(not isinstance(v,bool) for v in states.values()):raise ValueError('Invalid track states')
            stage.track_states.setdefault(track,{}).update(states)
        elif kind=='duplicate_track':created.append(stage.duplicate_track(op['track']))
        elif kind=='move_track':
            if not stage.move_track(op['track'],int(op['direction'])):raise ValueError('Track cannot move there')
        elif kind=='delete_track':
            if stage.track_states.get(op['track'],{}).get('locked'):raise ValueError('Track is locked')
            if not stage.delete_track(op['track']):raise ValueError('Cannot delete last track in a section')
        elif kind=='split':created.extend(stage.split_selection(op['ids'],float(op['at']),op.get('linked',True)))
        elif kind=='trim':stage.trim_items(op['ids'],float(op['delta']),op['edge'])
        elif kind=='link':stage.link_selection(op['ids'],op.get('unlink',False))
        elif kind=='insert_media':
            from .media_insert import plan,commit
            assets=[stage.media_by_id(i) for i in op['ids']]
            if not all(assets):raise ValueError('Unknown media ID')
            planned,ids,caps=plan(stage,assets,op.get('track',''),float(op.get('start',stage.duration)))
            commit(stage,planned); created.extend(sorted(ids|caps))
        elif kind=='insert_clip':
            media=stage.media_by_id(op.get('media_id',''))
            if media is None:raise ValueError('Unknown media ID')
            track=op.get('track','')
            if track not in stage.video_tracks+stage.audio_tracks:raise ValueError('Unknown track')
            if media.kind=='audio' and track not in stage.audio_tracks:raise ValueError('Audio media requires an audio track')
            if media.kind in {'video','image'} and track not in stage.video_tracks:raise ValueError('Visual media requires a video track')
            if stage.track_states.get(track,{}).get('locked'):raise ValueError('Destination track is locked')
            in_point=float(op.get('in_point',0.0))
            duration=float(op.get('duration',media.duration if media.kind!='image' else 5.0))
            start=float(op.get('start',stage.duration))
            role=op.get('role','normal')
            gain_db=float(op.get('gain_db',0.0))
            fade_in=float(op.get('fade_in',0.0))
            fade_out=float(op.get('fade_out',0.0))
            item_id=op.get('id') or uid()
            new_item=TimelineItem(item_id,media.id,track,start,duration,in_point,role=role,gain_db=gain_db,fade_in=fade_in,fade_out=fade_out)
            if 'effects' in op and isinstance(op['effects'],list):
                new_item.effects=copy.deepcopy(op['effects'])
            if 'crop' in op and isinstance(op['crop'],dict):
                merge(asdict(new_item.crop),op['crop'])
            if 'transform' in op and isinstance(op['transform'],dict):
                merge(asdict(new_item.transform),op['transform'])
            raw=stage.to_dict(); raw['timeline'].append(asdict(new_item))
            stage=Project.from_dict(raw); created.append(item_id)
        elif kind=='set_caption_style':
            from .caption_presets import CAPTION_PRESETS
            from .caption_templates import CAPTION_TEMPLATES
            template_map = {t["id"]: t for t in CAPTION_TEMPLATES}
            target = op.get('template') or op.get('preset', '')
            preset_dict = copy.deepcopy(template_map.get(target, CAPTION_PRESETS.get(target, {})))
            if 'properties' in op and isinstance(op['properties'],dict):
                merge(preset_dict,op['properties'])
            raw=stage.to_dict(); merge(raw['subtitle_style'],preset_dict)
            caption_ids=op.get('caption_ids')
            if caption_ids:
                for c in raw['captions']:
                    if c['id'] in caption_ids:
                        c['customize']=True
                        merge(c['style'],preset_dict)
            else:
                for c in raw['captions']:
                    merge(c['style'],preset_dict)
            stage=Project.from_dict(raw)
        elif kind=='apply_vertical_framing':
            fg_track=op.get('foreground_track','video_2')
            bg_track=op.get('background_track','video_1')
            scale=op.get('scale')
            raw=stage.to_dict()
            for item in raw['timeline']:
                if item.get('track')==fg_track:
                    item['transform']['y']=0.5
                    item['transform']['anchor_y']=0.0
                    if scale is not None:
                        item['transform']['scale']=float(scale)
                        if item['transform'].get('scale_linked',True):
                            item['transform']['scale_y']=float(scale)
                elif item.get('track')==bg_track:
                    item['role']='background'
                    item['transform']['x']=0.5
                    item['transform']['y']=0.5
                    item['transform']['scale']=1.0
                    if item['transform'].get('scale_linked',True):
                        item['transform']['scale_y']=1.0
            stage=Project.from_dict(raw)
        elif kind=='insert_transition':
            from .transitions import Transition, SUBSECTION_BY_TRANSITION, default_transition_properties
            name=op.get('name','Cross Dissolve')
            track=op.get('track',stage.video_tracks[0])
            if track not in stage.video_tracks:raise ValueError('Transitions require a video track')
            if stage.track_states.get(track,{}).get('locked'):raise ValueError('Destination track is locked')
            dur=float(op.get('duration',0.80))
            if not 0.05<=dur<=10.0:raise ValueError('Transition duration must be between 0.05 and 10.0 seconds')
            align=op.get('alignment','center')
            left_id=op.get('left_item_id','')
            right_id=op.get('right_item_id','')
            cut_time=op.get('cut_time')
            props=default_transition_properties(name)
            if 'properties' in op and isinstance(op['properties'],dict):
                props.update(copy.deepcopy(op['properties']))
            category=SUBSECTION_BY_TRANSITION.get(name,'Dissolve')
            left=stage.item_by_id(left_id) if left_id else None
            right=stage.item_by_id(right_id) if right_id else None
            if left and right:
                cut_t=left.start+left.duration
                start_t=cut_t-dur/2.0 if align=='center' else (cut_t if align=='start' else cut_t-dur)
            elif left:
                cut_t=left.start+left.duration
                start_t=cut_t-dur/2.0 if align=='center' else (cut_t if align=='start' else cut_t-dur)
            elif right:
                cut_t=right.start
                start_t=cut_t-dur/2.0 if align=='center' else (cut_t if align=='start' else cut_t-dur)
            elif cut_time is not None:
                cut_t=float(cut_time)
                start_t=cut_t-dur/2.0 if align=='center' else (cut_t if align=='start' else cut_t-dur)
            else:
                start_t=float(op.get('start',0.0))
            trans_id=op.get('id') or uid()
            new_trans=Transition(trans_id,name,category,track,start_t,dur,left_id,right_id,align,props)
            raw=stage.to_dict(); raw['transitions'].append(asdict(new_trans))
            stage=Project.from_dict(raw); created.append(trans_id)
        else:raise ValueError('Unknown edit operation: '+str(kind))
    validate(stage)
    # A batch may unlock a track first, but must not silently add into locked lanes.
    previous={i.id:i for i in project.timeline}
    for i in stage.timeline:
        if stage.track_states.get(i.track,{}).get('locked') and (i.id not in previous or i!=previous[i.id]):raise ValueError('Destination track is locked')
    return stage,created


class EditorAPI:
    def __init__(self,window):self.w=window; self.jobs={}; self.targets={}
    def dispatch(self,name,args):
        method=getattr(self,'call_'+name,None)
        if method is None:raise ValueError('Unknown editor tool')
        return method(**args)
    def editing(self):
        if QApplication.activeModalWidget():raise ValueError('A dialog is open. Use inspect_ui/ui_control to finish or dismiss it first.')
        if self.w.delivery.running:raise ValueError('Wait for the active render or cancel it before editing')
        from .workspace import set_page
        if self.w.current_page:set_page(self.w,0)
    def install(self,stage):
        self.w.commit_history(); self.w._restoring=True
        try:self.w.set_project(stage)
        finally:self.w._restoring=False
        self.w.model_changed()
    def call_get_state(self,section='all'):
        w=self.w
        result=dict(name=w.project.name,revision=revision(w.project),playhead=w.project.playhead,duration=w.project.duration,
            selected_ids=sorted(w.timeline.selected_ids),caption_ids=sorted(w.timeline.selected_caption_ids),
            selected_transition_id=getattr(w.timeline,'selected_transition_id',''),
            background_tasks=len(w._workers),page={0:'Edit',1:'Deliver',2:'Phone Connect'}.get(w.current_page,'Edit'),jobs=self.call_get_jobs())
        if section!='summary':result['project']=w.project.to_dict()
        return result
    def call_get_capabilities(self):
        from .effects import CATALOG
        from .transitions import TRANSITION_SUBSECTIONS
        from .graphics import GRAPHICS_CATALOG
        from .motion import schema
        import inspect
        return dict(effects=CATALOG,transitions=TRANSITION_SUBSECTIONS,graphics=list(GRAPHICS_CATALOG.keys()),commands={name:str(inspect.signature(getattr(self.w,name))) for name in COMMANDS},fields={c.__name__:{f.name:str(f.type) for f in fields(c)} for c in (ProjectSettings,TimelineItem,MediaItem,Caption,CaptionStyle,Crop,Transform)},
            operations={'add/update/remove':'collection: timeline|captions|transitions, id, values (partial fields; nested dictionaries merge). New timeline entries default to title; media clips require role=normal and media_id; transitions require name, duration, track.',
                'settings/subtitle_style':'values: partial fields','rename_project':'name','add_track':'kind: video|audio','track':'track, optional name, states: locked/visible/muted',
                'duplicate_track/delete_track':'track','move_track':'track, direction: -1|1','split':'ids, at, linked (default true)',
                'trim':'ids, delta, edge: left|right','link':'ids, unlink','insert_media':'ids (media pool IDs), start, track',
                'insert_clip':'media_id, track, start, duration, in_point, role, gain_db, effects, crop, transform',
                'insert_transition':'name, track, duration, alignment (center/start/end), optional left_item_id, right_item_id, cut_time, properties',
                'set_caption_style':'preset (crime_red, viral_yellow, cyber_cyan, mrbeast_gold, clean_card), properties (partial dict), optional caption_ids',
                'apply_vertical_framing':'mode (center_and_fill, fit_width, fill_916), foreground_track, background_track, optional scale'},
            motion_composition=schema(),guidance='Use inspect_ui/ui_control for all remaining inspector, effects, captions, optional analysis, Power Bin and menu workflows. These use the same controls as the user. Dialogs may require another ui_control call. Models are not downloaded silently. apply_edits is atomic; inspect updated state after every batch.')
    def call_apply_edits(self,revision,operations):
        self.editing()
        if revision!=globals()['revision'](self.w.project):raise ValueError('Project changed. Refresh get_state before editing.')
        stage,created=edited(self.w.project,operations); self.install(stage)
        return dict(revision=globals()['revision'](stage),created_ids=created,undoable=True)
    def call_synthesize_dialogue(self,text,voice='adam-narrator',start=None,track=None,rate=0,pitch=0,gain_db=0.0):
        self.editing()
        if not text or not str(text).strip():raise ValueError('Dialogue text cannot be empty')
        result=self.w.generate_tts_dialogue(
            initial_text=str(text).strip(),
            voice=str(voice),
            headless=True,
            start=float(start) if start is not None else None,
            track=str(track) if track else None,
            rate=int(rate),
            pitch=int(pitch),
            gain_db=float(gain_db)
        )
        if not result:raise RuntimeError('TTS dialogue synthesis failed')
        return dict(revision=globals()['revision'](self.w.project),media_id=result['media_id'],clip_id=result['clip_id'],
                    track=result['track'],start=result['start'],duration=result['duration'],path=result['path'])
    def call_apply_visual_fx(self,item_id,effect,properties=None):
        self.editing()
        fx_dict=self.w.apply_visual_fx(item_id,effect,properties=properties or {})
        if fx_dict is None:raise ValueError(f'Could not apply Visual FX {effect} to item {item_id}')
        return dict(revision=globals()['revision'](self.w.project),item_id=str(item_id),effect=effect,properties=fx_dict)
    def call_set_caption_style(self,preset=None,template=None,properties=None,caption_ids=None):
        self.editing()
        result=self.w.set_caption_style(preset=preset,template=template,properties=properties,caption_ids=caption_ids)
        return dict(revision=globals()['revision'](self.w.project),style=result)
    def call_apply_vertical_framing(self,mode="center_and_fill",foreground_track="video_2",background_track="video_1",scale=None):
        self.editing()
        result=self.w.apply_vertical_framing(mode=mode,foreground_track=foreground_track,background_track=background_track,scale=scale)
        return dict(revision=globals()['revision'](self.w.project),result=result)
    def call_apply_transition(self,name,track=None,left_item_id='',right_item_id='',cut_time=None,duration=0.80,alignment='center',properties=None):
        self.editing()
        trans=self.w.apply_transition(
            name=name,
            track=track or '',
            left_item_id=left_item_id or '',
            right_item_id=right_item_id or '',
            cut_time=float(cut_time) if cut_time is not None else None,
            duration=float(duration),
            alignment=alignment,
            properties=properties or {}
        )
        if trans is None:raise ValueError(f'Could not apply transition {name}')
        return dict(
            revision=globals()['revision'](self.w.project),
            transition_id=trans.id,
            name=trans.name,
            category=trans.category,
            track=trans.track,
            start=round(trans.start,3),
            duration=round(trans.duration,3),
            end=round(trans.end,3),
            left_item_id=trans.left_item_id,
            right_item_id=trans.right_item_id,
            alignment=trans.alignment,
            properties=trans.properties
        )
    def call_add_graphic(self,graphic_type='Circle',track='',start=None,duration=None,properties=None):
        self.editing()
        item=self.w.add_graphic_object(
            name=graphic_type,
            track=track or '',
            start=start,
            duration=duration,
            properties=properties or {}
        )
        if item is None:raise ValueError(f'Could not add graphic object {graphic_type}')
        return dict(
            revision=globals()['revision'](self.w.project),
            item_id=item.id,
            graphic_type=item.graphic_type,
            track=item.track,
            start=round(item.start,3),
            duration=round(item.duration,3),
            properties=item.graphic_data
        )
    def call_get_timeline_summary(self):
        p=self.w.project
        summary={
            'project_name':p.name,
            'duration':round(p.duration,3),
            'playhead':round(p.playhead,3),
            'resolution':f'{p.settings.width}x{p.settings.height}',
            'fps':p.settings.fps,
            'video_tracks':[],
            'audio_tracks':[],
            'captions':[],
            'transitions':[]
        }
        for track in p.video_tracks:
            clips=[i for i in p.timeline if i.track==track]
            clips.sort(key=lambda x:x.start)
            summary['video_tracks'].append({
                'track':track,
                'name':p.track_names.get(track,track),
                'clips':[{
                    'id':c.id,
                    'start':round(c.start,2),
                    'duration':round(c.duration,2),
                    'in_point':round(c.in_point,2),
                    'role':c.role,
                    'media_id':c.media_id,
                    'media_name':getattr(p.media_by_id(c.media_id),'name',''),
                    'effects':[e.get('name') for e in c.effects if isinstance(e,dict)]
                } for c in clips]
            })
        for track in p.audio_tracks:
            clips=[i for i in p.timeline if i.track==track]
            clips.sort(key=lambda x:x.start)
            summary['audio_tracks'].append({
                'track':track,
                'name':p.track_names.get(track,track),
                'clips':[{
                    'id':c.id,
                    'start':round(c.start,2),
                    'duration':round(c.duration,2),
                    'in_point':round(c.in_point,2),
                    'gain_db':round(c.gain_db,1),
                    'role':c.role,
                    'media_id':c.media_id,
                    'media_name':getattr(p.media_by_id(c.media_id),'name','')
                } for c in clips]
            })
        for c in sorted(p.captions,key=lambda x:x.start):
            summary['captions'].append({
                'id':c.id,
                'start':round(c.start,2),
                'end':round(c.end,2),
                'text':c.text,
                'is_hook':c.is_hook
            })
        for t in sorted(p.transitions,key=lambda x:x.start):
            summary['transitions'].append({
                'id':t.id,
                'name':t.name,
                'category':t.category,
                'track':t.track,
                'start':round(t.start,3),
                'duration':round(t.duration,3),
                'end':round(t.end,3),
                'left_item_id':t.left_item_id,
                'right_item_id':t.right_item_id,
                'alignment':t.alignment,
                'properties':t.properties
            })
        return summary
    def new_job(self,label):
        key=uid(); self.jobs[key]=dict(id=key,label=label,state='Running',started=time.time())
        if len(self.jobs)>100:
            old=next((k for k,v in self.jobs.items() if v['state']!='Running'),None)
            if old:self.jobs.pop(old)
        return self.jobs[key]
    def call_import_media(self,paths):
        self.editing()
        if not isinstance(paths,list) or not 1<=len(paths)<=100:raise ValueError('Provide 1–100 local media paths')
        paths=list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
        if any(not Path(p).is_file() for p in paths):raise ValueError('One or more media files do not exist')
        from .ui import Worker
        from .media import probe
        project=self.w.project; job=self.new_job('Import media')
        worker=Worker(lambda:[probe(p,self.w.settings.get('ffprobe','ffprobe'),self.w.settings.get('ffmpeg','ffmpeg')) for p in paths])
        def finish(items):
            if project is not self.w.project:job.update(state='Failed',error='Project changed during import; retry in the intended project'); return
            self.w.media_added(items)
            from .media_insert import source_key
            job.update(state='Complete',media_ids=[m.id for m in project.media if source_key(m.path) in {source_key(p) for p in paths}])
        worker.signals.result.connect(finish); worker.signals.error.connect(lambda e:job.update(state='Failed',error=e[-2000:])); self.w.start_worker(worker)
        return dict(job)
    def call_download_media(self,url,mode='video',target_res='',cookies_path='',auto_import=True,wait=True):
        self.editing()
        if not url or not str(url).strip():raise ValueError('URL cannot be empty')
        url=str(url).strip(); mode='audio' if str(mode).lower()=='audio' else 'video'
        from .ui import Worker
        from .downloader_dialog import download_media_synchronous
        from .media import probe

        job=self.new_job(f'Download media ({mode})')
        project=self.w.project

        def do_download():
            res=download_media_synchronous(url, mode=mode, target_res=target_res, cookies_path=cookies_path or None)
            path=res.get('path')
            probe_item=None
            if auto_import and path and Path(path).is_file():
                probe_item=probe(path, self.w.settings.get('ffprobe','ffprobe'), self.w.settings.get('ffmpeg','ffmpeg'))
            return res, probe_item

        if wait:
            from PySide6.QtCore import QEventLoop
            loop=QEventLoop()
            result_box={}
            error_box=[]

            def on_success(payload):
                res, probe_item = payload
                media_id = None
                if probe_item is not None and project is self.w.project:
                    self.w.media_added([probe_item])
                    media_id = probe_item.id
                result_box['data'] = {
                    'ok': True,
                    'path': res['path'],
                    'name': res['name'],
                    'title': res.get('title', ''),
                    'mode': res['mode'],
                    'size_bytes': res.get('size_bytes', 0),
                    'media_id': media_id,
                    'imported': bool(media_id),
                }
                job.update(state='Complete', **result_box['data'])
                loop.quit()

            def on_failure(err):
                error_box.append(err)
                job.update(state='Failed', error=err[-2000:])
                loop.quit()

            worker = Worker(do_download)
            worker.signals.result.connect(on_success)
            worker.signals.error.connect(on_failure)
            self.w.start_worker(worker)
            loop.exec()

            if error_box:
                raise RuntimeError(f'Download failed: {error_box[0]}')
            return result_box.get('data', dict(job))
        else:
            def on_async_success(payload):
                res, probe_item = payload
                media_id = None
                if probe_item is not None and project is self.w.project:
                    self.w.media_added([probe_item])
                    media_id = probe_item.id
                job.update(
                    state='Complete',
                    path=res['path'],
                    name=res['name'],
                    title=res.get('title', ''),
                    mode=res['mode'],
                    size_bytes=res.get('size_bytes', 0),
                    media_id=media_id,
                    imported=bool(media_id),
                )

            def on_async_failure(err):
                job.update(state='Failed', error=err[-2000:])

            worker = Worker(do_download)
            worker.signals.result.connect(on_async_success)
            worker.signals.error.connect(on_async_failure)
            self.w.start_worker(worker)
            return dict(job)
    def call_get_jobs(self):
        from .render_queue import elapsed
        return dict(tasks=list(self.jobs.values()),renders=[dict(id=j.setdefault('assistant_id',uid()),state=j['state'],path=j['output'],elapsed=elapsed(j),error=j.get('error','')) for j in self.w.delivery.jobs],
                    rendering=self.w.delivery.running,progress=self.w.delivery.progress.value())
    def call_seek(self,seconds):
        if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid seek time')
        self.w.transport.pause(); self.w.seek(min(seconds,self.w.project.duration)); return dict(playhead=self.w.project.playhead)
    def call_get_preview(self,area='preview',max_width=1280):
        if area not in {'preview','workspace'}:raise ValueError('Unknown preview area')
        widget=self.w if area=='workspace' else self.w.preview
        pixels=widget.grab().toImage(); max_width=max(160,min(1920,int(max_width)))
        if pixels.width()>max_width:pixels=pixels.scaledToWidth(max_width,Qt.SmoothTransformation)
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); pixels.save(buffer,'PNG')
        return {'_mcp_content':[dict(type='text',text=json.dumps(dict(playhead=self.w.project.playhead,area=area,note='Current displayed frame; seek decoding is asynchronous.'))),dict(type='image',data=bytes(buffer.data().toBase64()).decode(),mimeType='image/png')]}
    def call_select_items(self,ids=None,caption_ids=None,transition_id=None):
        self.editing(); ids=ids or []; caption_ids=caption_ids or []
        if set(ids)-{i.id for i in self.w.project.timeline} or set(caption_ids)-{c.id for c in self.w.project.captions}:raise ValueError('Unknown selection ID')
        if transition_id and not self.w.project.transition_by_id(transition_id):raise ValueError('Unknown transition ID')
        self.w.timeline.select_ids(set(ids),next(iter(ids),'')); self.w.timeline.selected_caption_ids=set(caption_ids)
        self.w.timeline.selected_caption=next(iter(caption_ids),'')
        if transition_id:self.w.select_transition(transition_id)
        elif ids:self.w.select_item(ids[0])
        elif caption_ids:self.w.select_caption(caption_ids[0])
        self.w.timeline.viewport().update(); return dict(selected_ids=ids,caption_ids=caption_ids,transition_id=transition_id or getattr(self.w.timeline,'selected_transition_id',''))
    def call_history(self,direction):
        self.editing()
        if direction not in {'undo','redo'}:raise ValueError('Use undo or redo')
        getattr(self.w,direction)(); return self.call_get_state('summary')
    def checkpoint(self):
        from .config import DATA_DIR
        path=DATA_DIR/'assistant-checkpoints'/f'{time.strftime("%Y%m%d-%H%M%S")}-{uid()}.kcut'
        copy.deepcopy(self.w.compounds.root()).save(path); return str(path)
    def call_project_file(self,operation,path='',name='Untitled Short',overwrite=False):
        self.editing()
        if operation=='checkpoint':return dict(path=self.checkpoint())
        if operation=='new':
            backup=self.checkpoint(); self.w.set_project(Project(name=name)); return dict(checkpoint=backup,revision=revision(self.w.project))
        if operation=='open':
            project=Project.load(path); validate(project); backup=self.checkpoint(); self.w.set_project(project)
            self.w._saved_project_key=self.w._history_key(project); return dict(checkpoint=backup,revision=revision(project))
        if operation=='save':
            if not path or Path(path).suffix.lower()!='.kcut':raise ValueError('Provide a .kcut output path')
            if Path(path).exists() and not overwrite:raise ValueError('File exists; explicitly set overwrite=true to replace it')
            self.w.compounds.root().save(path); self.w._saved_project_key=self.w._history_key(self.w.project)
            from .project_manager import remember
            remember(self.w,path,capture=True); return dict(path=str(Path(path).resolve()))
        raise ValueError('Unknown project operation')
    def call_queue_export(self,path,encoder='Auto',codec='h264',bitrate_mbps=10,burn_subtitles=True,export_audio=True,start=False,overwrite=False):
        from .exporter import ExportPreset
        validate(self.w.project)
        if not self.w.project.timeline:raise ValueError('Timeline is empty')
        output=Path(path).resolve()
        if output.suffix.lower()!='.mp4':raise ValueError('Provide an .mp4 output path')
        if any(Path(m.path).resolve()==output for m in self.w.project.media):raise ValueError('Export to a new file, not an original source media path')
        if output.exists() and not overwrite:raise ValueError('Output exists; set overwrite=true explicitly')
        if encoder not in {'Auto','CPU','NVIDIA','AMD','Intel'} or codec not in {'h264','h265'} or not 0.1<=bitrate_mbps<=200:raise ValueError('Invalid export settings')
        d=self.w.delivery
        if any(Path(j['output']).resolve()==output and j['state'] in {'Queued','Rendering'} for j in d.jobs):raise ValueError('Output already queued')
        job=dict(assistant_id=uid(),project=copy.deepcopy(self.w.project),output=str(output),preset=ExportPreset('AI export',codec,bitrate_mbps,192,'Custom'),hardware=encoder,
                 burn=bool(burn_subtitles and self.w.project.captions),audio=bool(export_audio),state='Queued',elapsed=0.)
        d.jobs.append(job); d.refresh()
        if start:d.render_all()
        return dict(id=job['assistant_id'],state=job['state'],path=str(output))
    def call_render_control(self,operation):
        if operation=='start':self.w.delivery.render_all()
        elif operation=='cancel':
            cancel=getattr(self.w.delivery,'render_cancel',None)
            if cancel:cancel.set()
        else:raise ValueError('Unknown render operation')
        return self.call_get_jobs()
    def call_editor_command(self,command,arguments=None):
        import inspect
        self.editing()
        if command not in COMMANDS:raise ValueError('Unknown editor command')
        function=getattr(self.w,command); arguments=arguments or {}; inspect.signature(function).bind(**arguments)
        job=self.new_job(command)
        def invoke():
            try:
                function(**arguments); job.update(state='Complete',note='Command returned; poll background/render status before claiming work is finished.')
            except Exception as error:job.update(state='Failed',error=str(error))
        QTimer.singleShot(0,invoke); return dict(job)
    def call_inspect_ui(self):
        self.targets={}; result=[]
        roots=[self.w]+[x for x in QApplication.topLevelWidgets() if isinstance(x,QDialog) and x.isVisible() and x.window() is not self.w]
        seen=set()
        for root in roots:
            for obj in [root]+root.findChildren(QAction)+root.findChildren(QWidget):
                if id(obj) in seen:continue
                seen.add(id(obj))
                if not isinstance(obj,(QAction,QAbstractButton,QAbstractSlider,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QTextEdit,QPlainTextEdit,QLabel,QDialog,QTabWidget)):continue
                if not isinstance(obj,QAction) and not obj.isVisible():continue
                key=hex(id(obj)); self.targets[key]=obj
                text=obj.text() if hasattr(obj,'text') else obj.windowTitle() if isinstance(obj,QDialog) else ''
                if isinstance(obj,QLineEdit) and obj.echoMode()!=QLineEdit.Normal:text='[hidden]'
                row=dict(target=key,type=type(obj).__name__,text=text[:1000],enabled=obj.isEnabled(),name=obj.objectName())
                if isinstance(obj,(QComboBox,QTabWidget)):
                    row.update(index=obj.currentIndex(),options=[obj.itemText(i) if isinstance(obj,QComboBox) else obj.tabText(i) for i in range(obj.count())])
                if isinstance(obj,(QAbstractSlider,QSpinBox,QDoubleSpinBox)):row.update(value=obj.value(),minimum=obj.minimum(),maximum=obj.maximum())
                if isinstance(obj,(QAction,QAbstractButton)) and obj.isCheckable():row['checked']=obj.isChecked()
                result.append(row)
        return dict(controls=result,modal=bool(QApplication.activeModalWidget()))
    def call_ui_control(self,target,operation,value=None):
        import shiboken6
        obj=self.targets.get(target)
        if obj is None or not shiboken6.isValid(obj):raise ValueError('Control expired; call inspect_ui again')
        if not obj.isEnabled():raise ValueError('Control is disabled')
        if operation in {'click','accept','reject'}:
            if operation=='click' and not isinstance(obj,(QAction,QAbstractButton)):raise ValueError('Control is not clickable')
            if operation!='click' and not isinstance(obj,QDialog):raise ValueError('Target is not a dialog')
            job=self.new_job('UI '+operation)
            def invoke():
                try:
                    if not shiboken6.isValid(obj):raise ValueError('Control expired')
                    if operation=='click':obj.trigger() if isinstance(obj,QAction) else obj.click()
                    else:getattr(obj,operation)()
                    job.update(state='Complete',note='UI command returned; background processing may continue. Check get_jobs/get_state.')
                except Exception as e:job.update(state='Failed',error=str(e))
            QTimer.singleShot(0,invoke); return dict(job)
        if operation=='focus':obj.setFocus(); return dict(ok=True)
        if operation!='set':raise ValueError('Unknown control operation')
        if isinstance(obj,(QAction,QAbstractButton)) and obj.isCheckable():
            if not isinstance(value,bool):raise ValueError('Checkbox value must be boolean')
            obj.setChecked(value)
        elif isinstance(obj,(QSpinBox,QDoubleSpinBox,QAbstractSlider)):
            if not isinstance(value,(float,int)) or not math.isfinite(value) or not obj.minimum()<=value<=obj.maximum():raise ValueError('Value outside control range')
            obj.setValue(value if isinstance(obj,QDoubleSpinBox) else int(value));
            if hasattr(obj,'editingFinished'):obj.editingFinished.emit()
        elif isinstance(obj,QComboBox):
            index=value if isinstance(value,int) else obj.findText(str(value))
            if isinstance(index,int) and 0<=index<obj.count():obj.setCurrentIndex(index)
            elif obj.isEditable():obj.setEditText(str(value))
            else:raise ValueError('Unknown combo option')
        elif isinstance(obj,QTabWidget):
            if not isinstance(value,int) or not 0<=value<obj.count():raise ValueError('Invalid tab index')
            obj.setCurrentIndex(value)
        elif isinstance(obj,QLineEdit):obj.setText(str(value)); obj.editingFinished.emit()
        elif isinstance(obj,(QTextEdit,QPlainTextEdit)):obj.setPlainText(str(value))
        else:raise ValueError('Control does not accept a value')
        return dict(ok=True)
