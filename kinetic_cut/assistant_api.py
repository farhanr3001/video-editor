"""Editor-side MCP operations. All entry points run on the Qt GUI thread."""
from .motion_audio import MAX_CUES
import copy
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QAbstractButton, QAbstractSlider,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QLabel,
    QDialog, QTabWidget, QWidget)
from .model import Project, ProjectSettings, TimelineItem, MediaItem, Caption, CaptionStyle, Crop, Transform, uid
from .tracking_effect import MODES as TRACKING_MODES
from .motion_presets import PRESETS as MOTION_PRESETS,is_motion


def tool(name, description, properties=None, required=(), readonly=False):
    return dict(name=name,description=description,inputSchema=dict(type='object',properties=properties or {},required=list(required),additionalProperties=False),
                annotations=dict(readOnlyHint=readonly,destructiveHint=not readonly,idempotentHint=readonly,openWorldHint=False))

S={'type':'string'}; N={'type':'number'}; B={'type':'boolean'}; O={'type':'object'}
COMMANDS=('add_title_object','apply_effect_to','viewer_command','timeline_command',
    'split_selected','delete_selected','delete_gaps','timeline_clipboard',
    'apply_vertical','generate_captions','generate_tts_dialogue','apply_visual_fx',
    'set_caption_style','apply_vertical_framing',
    'remove_silence','highlight_reel','instant_package',
    'toggle_play','stop','mark_in','mark_out','add_video_track','add_audio_track',
    'frame_source','download_media','apply_transition','remove_transition',
    'add_graphic_object','remove_media','open_keyframes','open_motion_composition')
GUIDE_SECTIONS={
    'connection':'1. Connect to the actual running editor',
    'startup':'2. First actions in a new editing chat',
    'edits':'3. Revisions, transactions and project safety',
    'media':'4. Media and asynchronous work',
    'framing':'5. Framing, time and units',
    'effects':'6. Effects, transitions and motion graphics',
    'captions':'7. Captions, templates and transcripts',
    'review':'8. Review and audio',
    'export':'9. Save, export and confirm delivery',
    'troubleshooting':'10. UI fallback and recovery',
    'tools':'11. Complete exposed tool index',
}
TOOLS=[
    tool('get_editor_guide','Read the bundled neutral MCP manual: connection, tools, units, revisions and jobs. No personal editing preferences or private files. Start here, then get_state and get_capabilities for live context.',{'section':{'type':'string','enum':['all',*GUIDE_SECTIONS],'default':'all'}},readonly=True),
    tool('add_motion_sound_cue','Read a short local sound (up to 60s), trim silent edges, and attach it to a motion composition asynchronously as ONE undo step. No audio timeline lane is added. Source time follows graphic moves/trims/re-time. Event may bind to a layer start/end or selected key time. Poll get_jobs; edit_motion_composition scene_settings.sound_cues edits/removes existing cues.',{'revision':S,'item_id':S,'path':S,'time':N,'gain_db':{'type':'number','minimum':-60,'maximum':0},'event':{'type':'string','enum':['time','layer_start','layer_end','keyframe']},'node_id':S,'channel':S,'key_time':N},('revision','item_id','path','time')),
    tool('motion_sound_job_control','Cancel a sound cue import before it commits. No partial scene edit is applied.',{'job_id':S},('job_id',)),
    tool('create_edit_contact_sheet','Create timestamped production-compositor review frames and short audio peak/silence checks asynchronously WITHOUT seeking the editor. Snapshot/revision reported. 1–12 timestamps, 160–640px wide. Poll get_jobs, then get_edit_contact_sheet. Does not prove continuous playback or caption speech sync.',{'timestamps':{'type':'array','items':N,'minItems':1,'maxItems':12},'width':{'type':'integer','minimum':160,'maximum':640}},('timestamps',)),
    tool('get_edit_contact_sheet','Read a completed review report and its image.',{'job_id':S},('job_id',),readonly=True),
    tool('edit_review_job_control','Cancel a running contact-sheet job. The editor/project remains unchanged.',{'job_id':S},('job_id',)),
    tool('analyze_source_media','Look at and listen to an imported SOURCE video/audio (not the timeline) asynchronously, without touching the project or playhead. kinds: frames (labelled contact sheet of up to 12 source frames: sample=even | shots | loud_moments, or explicit timestamps), audio (loudness curve, silent ranges, unusually loud moments with peak time and rise in dB), shots (scene-change cut times, about 1/12 s precision). Times are source seconds; start/end limit the range (max 1 h). Loud is level only, not meaning: check frames and transcripts. Shot detection is the slow part on long media, so narrow the range or drop it when not needed. Poll get_jobs, then get_source_analysis.',{'media_id':S,'kinds':{'type':'array','items':{'type':'string','enum':['frames','audio','shots']},'minItems':1,'uniqueItems':True},'start':N,'end':N,'sample':{'type':'string','enum':['even','shots','loud_moments']},'count':{'type':'integer','minimum':1,'maximum':12},'timestamps':{'type':'array','items':N,'minItems':1,'maxItems':12},'width':{'type':'integer','minimum':160,'maximum':640},'shot_threshold':{'type':'number','minimum':.1,'maximum':.9}},('media_id',)),
    tool('get_source_analysis','Read a completed source analysis: JSON report plus the labelled frame sheet image when frames were requested.',{'job_id':S},('job_id',),readonly=True),
    tool('source_analysis_job_control','Cancel a running source analysis. The project and source files are unchanged.',{'job_id':S}, ('job_id',)),
    tool('anchor_captions_to_video','Place specified captions just INSIDE the bottom of the active webcam clip on a video track. Samples its evaluated crop/transform at each caption midpoint. Atomic/one undo; rejects rotated or undersized regions. Review animated framing separately.',{'revision':S,'track':S,'caption_ids':{'type':'array','items':S,'minItems':1},'margin':N},('revision','track','caption_ids')),
    tool('review_edit','Read missing media, visual coverage gaps, caption bounds/platform margins and timing concerns without seeking or changing edits.',readonly=True),
    tool('review_caption_timing','Read caption timing/text anomalies without changing the project. Flags estimated word timings, overlaps, malformed alignment and unusually long words for audio review.',readonly=True),
    tool('generate_source_transcripts','Generate a reusable local SOURCE transcript index asynchronously without adding captions or changing edits. Poll get_jobs. Sources must already be imported; repeated/trimmed clips share their source index.',{'media_ids':{'type':'array','items':S,'minItems':1,'maxItems':100},'force':B},('media_ids',)),
    tool('search_transcripts','Search spoken words across indexed imported sources; returns source timestamps, word timings and every matching timeline cut. Missing sources must be generated first. Pagination uses offset/limit. start/end limit results to a source-time range; detail=text returns only media_id, segment, start, end and text (much smaller).',{'query':S,'media_ids':{'type':'array','items':S},'limit':{'type':'integer','minimum':1,'maximum':500},'offset':{'type':'integer','minimum':0},'start':{'type':'number','minimum':0},'end':{'type':'number','minimum':0},'detail':{'type':'string','enum':['full','text']}},readonly=True),
    tool('transcript_job_control','Cancel source transcription. Completed source indexes remain reusable; no timeline edits are made.',{'job_id':S},('job_id',)),
    tool('get_state','Read current project, revision, selection and task status. section=all (default) returns the project with timeline fields still at their defaults omitted (detail=full restores every field) and captions in compact form (a shared caption_styles table and timed-word counts instead of word timings); captions returns full captions with word timings, optionally limited to start/end timeline seconds (section=all also honours start/end for timeline items and captions); summary omits the project; diagnostics is summary plus the playback/renderer diagnostics block, only needed when debugging playback.',{'section':{'type':'string','enum':['all','summary','diagnostics','captions']},'start':{'type':'number','minimum':0},'end':{'type':'number','minimum':0},'detail':{'type':'string','enum':['compact','full']}},readonly=True),
    tool('get_capabilities','Discover every editable data field, edit operation, available effect and tool workflow.',readonly=True),
    tool('apply_edits','Apply an atomic batch as ONE undo step. Requires the revision from get_state. See get_capabilities for operations. All times in seconds.',{'revision':S,'operations':{'type':'array','items':O,'minItems':1,'maxItems':500}},('revision','operations')),
    tool('synthesize_dialogue','Synthesize voiceover speech using local neural TTS (Adam Narrator or other voices) and place it directly on the timeline with waveform and caption-ready role="source_audio".',{'text':S,'voice':{'type':'string','default':'adam-narrator'},'start':N,'track':S,'rate':{'type':'integer','minimum':-50,'maximum':50},'pitch':{'type':'integer','minimum':-20,'maximum':20},'gain_db':N},('text',)),
    tool('apply_visual_fx','Apply and configure a Visual FX (Punch Zoom, Camera Shake, Crash Zoom, etc.) with custom parameters on any timeline clip in one call.',{'item_id':S,'effect':S,'properties':O},('item_id','effect')),
    tool('track_object','Analyse a selected source region asynchronously and add an Object Tracking effect as ONE undo step. Requires a current revision and unlocked video/image clip. Region and correction boxes are [x,y,width,height] normalized to the FULL source, before crop. Times are source seconds. No models/downloads. Poll get_jobs; Complete is success. Cancel with tracking_job_control. Censor loss uses Full frame protection by default; unsafe unreviewed censor loss refuses the edit.',
         {'revision':S,'item_id':S,'reference_source_time':N,
          'region':{'type':'array','items':{'type':'number','minimum':0,'maximum':1},'minItems':4,'maxItems':4},
          'anchors':{'type':'array','maxItems':128,'items':{'type':'object','properties':{'time':N,'box':{'type':'array','items':{'type':'number','minimum':0,'maximum':1},'minItems':4,'maxItems':4}},'required':['time','box'],'additionalProperties':False}},
          'mode':{'type':'string','enum':list(TRACKING_MODES),'default':'Censor Bar'},
          'properties':O,'sample_fps':{'type':'number','minimum':1,'maximum':60,'default':15},
          'search_radius':{'type':'number','minimum':.02,'maximum':.6,'default':.22},
          'confidence_threshold':{'type':'number','minimum':.2,'maximum':.95,'default':.58},
          'existing_effect_index':{'type':'integer','minimum':0}},
         ('revision','item_id','reference_source_time','region')),
    tool('tracking_job_control','Cancel one running Object Tracking job. No partial trajectory is applied. Poll get_jobs until Cancelled; source files are unchanged.',{'job_id':S,'operation':{'type':'string','enum':['cancel']}},('job_id','operation')),
    tool('apply_transition','Apply and configure a video transition (Cross Dissolve, Dip to Color / White Flash, Wipe Left/Right/Up/Down, Push Left/Right/Up/Down, Slide In/Out, Zoom In, Digital Glitch, etc.) between clips or on an edit cut in one call.',{'name':S,'track':S,'left_item_id':S,'right_item_id':S,'cut_time':N,'duration':N,'alignment':{'type':'string','enum':['center','start','end']},'properties':O},('name',)),
    tool('add_graphic','Add a vector graphic, motion preset or editable Motion Composition. Preset properties use the fields in get_capabilities.motion_presets; compositions use properties.scene.',{'graphic_type':{'type':'string','enum':['Motion Composition',*MOTION_PRESETS,'Circle','Pointing Arrow','Square','Rectangle','Timer / Countdown','Speech Bubble / Quote Card','Progress Bar','Callout Badge']},'track':S,'start':N,'duration':N,'properties':O},('graphic_type',)),
    tool('add_story_graphic','Add a ready-made motion graphic template (see get_capabilities.story_templates for names and fields) as an ordinary editable Motion Composition. properties = template fields; duration rescales timing. Returns lint warnings and the scene layer ids to refine with edit_motion_composition.',{'template':S,'properties':O,'track':S,'start':N,'duration':N},('template',)),
    tool('get_motion_composition','Read a composition scene, layer bounds and exact source-time state without seeking playback.',{'item_id':S,'seconds':N},('item_id',),readonly=True),
    tool('get_motion_preview','Render one exact composition frame, including alpha, without seeking or modifying the timeline.',{'item_id':S,'seconds':N,'max_width':{'type':'integer','minimum':160,'maximum':1920}},('item_id',),readonly=True),
    tool('get_motion_contact_sheet','Render several composition frames on the GPU (same renderer as playback/export) into ONE labelled contact sheet image. Use instead of many get_motion_preview calls.',{'item_id':S,'times':{'type':'array','items':N,'minItems':1,'maxItems':36},'columns':{'type':'integer','minimum':1,'maximum':8},'cell_width':{'type':'integer','minimum':120,'maximum':540}},('item_id','times'),readonly=True),
    tool('motion_scene_file','Load a composition scene from a local .json file (a scene object, or {"scene":...,"duration":...}) into a new Motion Composition or replace an existing one (item_id) as ONE undo step; or save a composition scene to a .json file. Use for large scenes instead of sending them inline.',{'operation':{'type':'string','enum':['load','save']},'path':S,'revision':S,'item_id':S,'track':S,'start':N,'duration':N,'overwrite':B},('operation','path')),
    tool('list_fonts','List font families available to motion text and captions (bundled and installed), with their styles (italic/bold weights). Filter with query.',{'query':S,'limit':{'type':'integer','minimum':1,'maximum':500}},readonly=True),
    tool('add_motion_sound_cues','Attach up to 128 sound cues in ONE undo step (each like add_motion_sound_cue: path, time, gain_db, event, node_id, channel, key_time). Asynchronous; poll get_jobs.',{'revision':S,'item_id':S,'cues':{'type':'array','minItems':1,'maxItems':128,'items':O}},('revision','item_id','cues')),
    tool('motion_assets','Reusable motion assets (text reveals, UI cards, toasts, tab bars, cursors, calendars, lines, devices, stacks, scene hand-offs, and the user\'s saved assets). list returns names/categories/descriptions; insert adds one to a composition as one editable group at canvas x,y and composition time (ONE undo step); save stores layer_ids (sharing one parent) as a new user asset.',{'operation':{'type':'string','enum':['list','insert','save']},'revision':S,'item_id':S,'name':S,'x':N,'y':N,'time':N,'layer_ids':{'type':'array','items':S},'category':S},('operation',)),
    tool('edit_motion_composition','Atomic one-undo layer/keyframe edits. Requires current project revision. Operations: add_layer(node), update_layer(id,values), remove_layer(id, including descendants), move_layer(id,before), set_key(id,channel,time,value,interpolation,bezier), remove_key(id,channel,time), animate(id,preset,start,duration,amount; presets fade_in, fade_out, pop_in, pop_out, slide_in_left/right/up/down, draw_on, wipe_out, pulse, shake, spin_in), pulse(id,channel,times[],base,peak,attack,decay: use for beat/word sync with times from get_state captions or source analysis), scene_settings(values: canvas, motion_blur, sound_cues, camera, post, floor, background). insert_asset(name,x,y,time: see motion_assets), add_scene(id,start,end,fade_in,fade_out,handoff blur|slide|fade,amount,children[]), sequence(ids[],start,overlap: lay scene groups end to end). Times are composition SOURCE seconds unless an operation sets clock:\"timeline\" (then time/times/start are timeline seconds and are converted using the clip start, in_point and speed).',{'revision':S,'item_id':S,'operations':{'type':'array','items':O,'minItems':1,'maxItems':256}},('revision','item_id','operations')),
    tool('configure_motion_preset','Update an existing motion preset with one undo step. Preserves custom layers and unrelated scene edits. Discover fields using get_capabilities.motion_presets.',{'revision':S,'item_id':S,'properties':O},('revision','item_id','properties')),
    tool('set_caption_style','Apply curated viral subtitle style presets (crime_red, viral_yellow, cyber_cyan, mrbeast_gold, clean_card) or customize font, colors, animation, size, glow, and lower-third position across captions in one call.',{'preset':{'type':'string','enum':['crime_red','viral_yellow','cyber_cyan','mrbeast_gold','clean_card']},'properties':O,'caption_ids':{'type':'array','items':S}}),
    tool('apply_vertical_framing','Format and align clips for 9:16 vertical video shorts: vertically center foreground clips (y=0.5), configure ambient background fill layers (role="background"), and optionally adjust framing scale.',{'mode':{'type':'string','enum':['center_and_fill','fit_width','fill_916']},'foreground_track':S,'background_track':S,'scale':N}),
    tool('get_timeline_summary','Return a concise structured summary of timeline tracks, clips, in/out timings, audio levels, active effects, subtitle cards, and video transitions.',readonly=True),
    tool('import_media','Index local media asynchronously without duplicating source files. Returns a job ID. Poll get_jobs, then use insert_media in apply_edits.',{'paths':{'type':'array','items':S,'minItems':1,'maxItems':100}},('paths',)),
    tool('download_media','Download video or audio from YouTube, YouTube Shorts, Twitch clips (twitch.tv/<channel>/clip/<id> or clips.twitch.tv/<id>), TikTok, TikTok Sounds, Instagram, or Twitter/X and optionally auto-import into the project media bin.',{'url':S,'mode':{'type':'string','enum':['video','audio'],'default':'video'},'target_res':S,'cookies_path':S,'auto_import':B,'wait':B},('url',)),
    tool('get_jobs','Read import/action jobs and render queue states. Running jobs are complete; finished jobs are compact (large results are omitted) and only the latest `finished` (default 5) are listed. Pass job_id for one job in full. Complete is the only successful render terminal state.',{'job_id':S,'finished':{'type':'integer','minimum':0,'maximum':100}},readonly=True),
    tool('seek','Seek the timeline in seconds; then request get_preview. Decode may still be pending.',{'seconds':N},('seconds',)),
    tool('get_preview','Return an image of the current viewer or full editor. Includes actual playhead and frame status. Seek separately; sample again if decoding is pending.',{'area':{'type':'string','enum':['preview','workspace']},'max_width':{'type':'integer','minimum':160,'maximum':1920}},readonly=True),
    tool('select_items','Select timeline clips, captions, or transitions for editor commands and inspector controls.',{'ids':{'type':'array','items':S},'caption_ids':{'type':'array','items':S},'transition_id':S}),
    tool('history','Undo or redo an edit.',{'direction':{'type':'string','enum':['undo','redo']}},('direction',)),
    tool('project_file','New/open/save/checkpoint a project. Switches checkpoint current work first. Saves require explicit path; overwrite=false protects existing files.',{'operation':{'type':'string','enum':['new','open','save','checkpoint']},'path':S,'name':S,'overwrite':B},('operation',)),
    tool('queue_export','Queue a snapshot in Deliver. Rendering is asynchronous; poll get_jobs. Does not retry failed jobs.',{'path':S,'encoder':{'type':'string','enum':['Auto','CPU','NVIDIA','AMD','Intel']},'codec':{'type':'string','enum':['h264','h265']},'bitrate_mbps':N,'burn_subtitles':B,'export_audio':B,'start':B,'overwrite':B},('path',)),
    tool('exit_application','Close the Kinetic Cut app, like File > Exit. Refused while the project has unsaved changes unless discard_unsaved is true (save first with project_file), and while a render is running. The app closes just after this response, so the MCP connection drops; relaunch it to reconnect.',{'discard_unsaved':B}),
    tool('render_control','Start queued renders or cancel the active render.',{'operation':{'type':'string','enum':['start','cancel']}},('operation',)),
    tool('editor_command','Run an existing editor workflow: effects, titles, crop, captions, silence/vocal processing, placement, clipboard or transport. Discover argument names with get_capabilities. Returns a command job; inspect_ui handles any prompts.',{'command':{'type':'string','enum':list(COMMANDS)},'arguments':O},('command',)),
    tool('inspect_ui','Discover live editor controls, menus and open dialogs, with target IDs for ui_control. Includes full effects inspector. No screen coordinates needed.',readonly=True),
    tool('ui_control','Operate any advertised live UI control. click returns an action job to avoid blocking on dialogs. Set controls by value; choose combo/tab index or text. Some workflows require download/output prompts.',{'target':S,'operation':{'type':'string','enum':['click','set','focus','accept','reject']},'value':{}},('target','operation')),
]


def coerce_numbers(name,args):
    """Clients with an older tool list can send numbers as strings; accept them where the schema says number."""
    entry=next((t for t in TOOLS if t['name']==name),None)
    props=(entry or {}).get('inputSchema',{}).get('properties',{})
    def number(value,kind):
        if isinstance(value,str) and not isinstance(value,bool):
            try:
                parsed=float(value.strip())
            except ValueError:return value
            return int(parsed) if kind=='integer' and parsed==int(parsed) else parsed
        return value
    result=dict(args)
    for key,value in args.items():
        schema=props.get(key,{}); kind=schema.get('type')
        if kind in ('number','integer'):result[key]=number(value,kind)
        elif kind=='array' and isinstance(value,list) and schema.get('items',{}).get('type') in ('number','integer'):
            result[key]=[number(v,schema['items']['type']) for v in value]
    return result


def revision(project):
    data=project.to_dict(); data.pop('playhead',None); data.pop('modified_at',None)
    for media in data.get('media',[]):
        for derived in ('thumbnail','video_codec','stream_durations'):media.pop(derived,None)    # filled in by background probing; not an edit
    return hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()[:20]


def merge(target, values):
    if not isinstance(values,dict):raise ValueError('values must be an object')
    for key,value in values.items():
        if key not in target:raise ValueError('Unknown field: '+key)
        if isinstance(target[key],dict) and isinstance(value,dict):
            # Effect dictionaries and track maps have extensible keys.
            target[key].update(copy.deepcopy(value))
        else:target[key]=copy.deepcopy(value)


def finite_numbers(value):
    """Reject invalid numbers before constructors or clamps can disguise them."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite numeric value')
    if isinstance(value, dict):
        for item in value.values():finite_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:finite_numbers(item)


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
    finite_numbers(project.to_dict())
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
            if item.role=='graphic' and is_motion(item.graphic_type):
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
        for identifier in (tr.left_item_id,tr.right_item_id):
            if identifier:
                item=project.item_by_id(identifier)
                if item is None or item.track!=tr.track:raise ValueError('Transition references missing or mismatched clips')


def edited(project, operations, report=None):
    if not isinstance(operations,list) or not 1<=len(operations)<=500:raise ValueError('Provide 1–500 operations')
    finite_numbers(operations)
    stage=copy.deepcopy(project); created=[]; report=report if report is not None else []
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
                    if is_motion(values.get('graphic_type','')):base['transform']['y']=.5
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
                if kind=='remove':
                    rows.remove(target)
                    if collection=='timeline':
                        raw['transitions']=[t for t in raw['transitions'] if identifier not in (t.get('left_item_id'),t.get('right_item_id'))]
                else:
                    if 'id' in values:raise ValueError('Item IDs cannot be changed')
                    previous=(target.get('text'),copy.deepcopy(target.get('word_timings')),list(target.get('highlighted_words',[]))) if collection=='captions' else None
                    merge(target,values)
                    if previous and isinstance(values.get('text'),str) and values['text']!=previous[0] and 'word_timings' not in values:
                        # A text edit keeps measured timing for unchanged words and estimates the rest inside the old span.
                        from .caption_words import retime
                        target['word_timings']=retime(previous[0],previous[1] or [],values['text'])
                        old_words,new_words=previous[0].split(),values['text'].split(); clean=lambda w:re.sub(r'\W','',w).casefold()
                        if 'highlighted_words' not in values:
                            target['highlighted_words']=[i for i in previous[2] if i<len(old_words) and i<len(new_words) and clean(old_words[i])==clean(new_words[i])]
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
                crop=asdict(new_item.crop); merge(crop,op['crop']); new_item.crop=Crop(**crop)
            if 'transform' in op and isinstance(op['transform'],dict):
                transform=asdict(new_item.transform); merge(transform,op['transform']); new_item.transform=Transform(**transform)
            raw=stage.to_dict(); raw['timeline'].append(asdict(new_item)); created.append(item_id)
            if op.get('with_audio'):
                if media.kind!='video' or not media.has_audio:raise ValueError('with_audio needs video media that has an audio stream')
                audio_track=op.get('audio_track') or next((t for t in stage.audio_tracks if not stage.track_states.get(t,{}).get('locked')),'')
                if audio_track not in stage.audio_tracks or stage.track_states.get(audio_track,{}).get('locked'):raise ValueError('audio_track must be an unlocked audio track')
                link=uid(); audio_id=op.get('audio_id') or uid()
                raw['timeline'][-1]['link_id']=raw['timeline'][-1]['group_id']=link
                audio=TimelineItem(audio_id,media.id,audio_track,start,duration,in_point,role='source_audio',gain_db=gain_db,fade_in=fade_in,fade_out=fade_out,link_id=link,group_id=link)
                raw['timeline'].append(asdict(audio)); created.append(audio_id)
            stage=Project.from_dict(raw)
        elif kind=='ripple_delete_range':
            from .range_edit import ripple_delete_range
            for number in (op.get('start'),op.get('end')):
                if isinstance(number,bool) or not isinstance(number,(int,float)):raise ValueError('ripple_delete_range needs numeric start and end (timeline seconds)')
            report.append(dict(op='ripple_delete_range',**ripple_delete_range(stage,float(op['start']),float(op['end']))))
        elif kind=='fit_region':
            from .range_edit import fit_region
            ids=op.get('ids') or ([op['id']] if op.get('id') else [])
            if not isinstance(ids,list):raise ValueError('ids must be a list of item IDs')
            report.extend(dict(op='fit_region',**d) for d in fit_region(stage,ids,op.get('source_rect'),op.get('target_rect'),op.get('mode','fit')))
        elif kind=='set_caption_style':
            from .caption_presets import CAPTION_PRESETS
            from .caption_templates import CAPTION_TEMPLATES
            template_map = {t["id"]: t for t in CAPTION_TEMPLATES}
            target = op.get('template') or op.get('preset', '')
            preset_dict = {k:copy.deepcopy(v) for k,v in template_map.get(target, CAPTION_PRESETS.get(target, {})).items() if k in CaptionStyle.__dataclass_fields__}
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
            if preset_dict.get('animation')=='smart highlight':
                from .caption_emphasis import mark_strong_words
                mark_strong_words([c for c in stage.captions if not caption_ids or c.id in caption_ids])
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
    previous_captions={c.id:c for c in project.captions}
    if stage.track_states.get('subtitle_1',{}).get('locked'):
        if any(c.id not in previous_captions or c!=previous_captions[c.id] for c in stage.captions):raise ValueError('Destination track is locked')
    previous_transitions={t.id:t for t in project.transitions}
    for t in stage.transitions:
        if stage.track_states.get(t.track,{}).get('locked') and (t.id not in previous_transitions or t!=previous_transitions[t.id]):raise ValueError('Destination track is locked')
    return stage,created


class EditorAPI:
    def __init__(self,window):self.w=window; self.jobs={}; self.targets={}; self._tracking_jobs={}
    def dispatch(self,name,args):
        method=getattr(self,'call_'+name,None)
        if method is None:raise ValueError('Unknown editor tool')
        return method(**coerce_numbers(name,args))
    def call_generate_source_transcripts(self,media_ids,force=False):
        from .transcript_ui import service
        return service(self.w).start(media_ids,force)
    def call_search_transcripts(self,query='',media_ids=None,limit=200,offset=0,start=None,end=None,detail='full'):
        from .transcripts import search
        return search(self.w.project,self.w.settings,query,media_ids,limit,offset,start,end,detail)
    def call_transcript_job_control(self,job_id):
        from .transcript_ui import service
        return service(self.w).cancel(job_id)
    def call_review_caption_timing(self):
        from .caption_quality import review
        return review(self.w.project)
    def call_anchor_captions_to_video(self,revision,track,caption_ids,margin=16):
        self.editing()
        if revision!=globals()['revision'](self.w.project):raise ValueError('Project changed. Refresh get_state.')
        from .edit_review import anchor_captions
        stage=copy.deepcopy(self.w.project); placements=anchor_captions(self.w,stage,track,caption_ids,margin)
        validate(stage); self.install(stage)
        return dict(revision=globals()['revision'](stage),placements=placements,undoable=True)
    def call_review_edit(self):
        from .edit_review import structural
        return structural(self.w.project)
    def call_create_edit_contact_sheet(self,timestamps,width=360):
        import threading
        from .config import CACHE_DIR
        from .review_frames import create
        from .caption_fonts import load_fonts
        from .ui import Worker
        if getattr(self.w,'_closing',False):raise ValueError('The editor is closing.')
        if not isinstance(timestamps,list) or not 1<=len(timestamps)<=12 or any(isinstance(t,bool) or not isinstance(t,(int,float)) or not math.isfinite(t) or not 0<=t<self.w.project.duration for t in timestamps):raise ValueError('Choose 1–12 timestamps inside the project.')
        if not isinstance(width,int) or not 160<=width<=640:raise ValueError('Review width must be 160–640.')
        if any(j.get('review') and j['state'] in ('Running','Cancelling') for j in self.jobs.values()):raise ValueError('A contact sheet is already running.')
        load_fonts(); snapshot=copy.deepcopy(self.w.project); settings=copy.deepcopy(self.w.settings); cancel=threading.Event()
        job=self.new_job('Edit contact sheet'); job.update(review=True,revision=revision(snapshot),cancellable=True,progress=0)
        if not hasattr(self,'_review_cancels'):self._review_cancels={}
        self._review_cancels[job['id']]=cancel
        directory=CACHE_DIR/'edit-reviews'/job['id']
        worker=Worker(lambda:create(snapshot,settings,timestamps,width,cancel,lambda p,m:worker.signals.progress.emit((p,m)),directory)); worker.cancel_callback=cancel.set
        def progress(value):job.update(progress=value[0],message=value[1])
        def ready(result):job.update(state='Cancelled' if cancel.is_set() else 'Complete',result=result,progress=100)
        def failed(error):job.update(state='Cancelled' if cancel.is_set() else 'Failed',error='' if cancel.is_set() else str(error)[-1800:])
        def finished():
            if job['state'] in ('Running','Cancelling'):failed('Contact-sheet generation did not complete.')
            job.update(cancellable=False,finished=time.time()); self._review_cancels.pop(job['id'],None)
        worker.signals.progress.connect(progress); worker.signals.result.connect(ready); worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:self.w.start_worker(worker)
        except Exception:cancel.set(); failed('Could not start review.'); finished(); raise
        return dict(job)
    def call_get_edit_contact_sheet(self,job_id):
        job=self.jobs.get(job_id)
        if not job or not job.get('review'):raise ValueError('Unknown contact-sheet job.')
        if job['state']!='Complete':return dict(job)
        import base64
        image=Path(job['result']['contact_sheet'])
        if not image.is_file():raise ValueError('Review cache was cleared. Generate the contact sheet again.')
        return {'_mcp_content':[dict(type='text',text=json.dumps(job)),dict(type='image',data=base64.b64encode(image.read_bytes()).decode(),mimeType='image/png')]}
    def call_edit_review_job_control(self,job_id):
        job=self.jobs.get(job_id); token=getattr(self,'_review_cancels',{}).get(job_id)
        if not job or not token or job['state'] not in ('Running','Cancelling'):raise ValueError('This contact-sheet job is not running.')
        token.set(); job['state']='Cancelling'; return dict(job)
    def call_analyze_source_media(self,media_id,kinds=None,start=0,end=None,sample='even',count=12,timestamps=None,width=320,shot_threshold=.3):
        import threading
        from .config import CACHE_DIR
        from . import source_analysis as sa
        from .ui import Worker
        if getattr(self.w,'_closing',False):raise ValueError('The editor is closing.')
        media=self.w.project.media_by_id(media_id)
        if not media:raise ValueError('Unknown media_id. Read get_state for the media pool.')
        if media.kind not in ('video','audio'):raise ValueError('Only video and audio sources can be analysed.')
        kinds=list(sa.KINDS if kinds is None else kinds)
        if not kinds or len(set(kinds))!=len(kinds) or any(k not in sa.KINDS for k in kinds):raise ValueError('kinds must be unique values from frames, audio, shots.')
        number=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
        end=media.duration if end is None else end
        if not number(start) or not number(end) or not 0<=start<end<=media.duration+.01:raise ValueError('Choose 0 <= start < end <= media duration (%.3f s).'%media.duration)
        end=min(end,media.duration)
        if end-start>sa.MAX_RANGE:raise ValueError('Analyse at most one hour at a time.')
        if sample not in sa.SAMPLING:raise ValueError('sample must be even, shots or loud_moments.')
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=12:raise ValueError('count must be 1-12.')
        if timestamps is not None and (not isinstance(timestamps,list) or not 1<=len(timestamps)<=12 or any(not number(t) or not start<=t<end for t in timestamps)):raise ValueError('timestamps: 1-12 source times inside the range.')
        if isinstance(width,bool) or not isinstance(width,int) or not 160<=width<=640:raise ValueError('width must be 160-640.')
        if not number(shot_threshold) or not .1<=shot_threshold<=.9:raise ValueError('shot_threshold must be 0.1-0.9.')
        if any(j.get('source_analysis') and j['state'] in ('Running','Cancelling') for j in self.jobs.values()):raise ValueError('A source analysis is already running.')
        media=copy.deepcopy(media); ffmpeg=self.w.settings.get('ffmpeg','ffmpeg'); cancel=threading.Event()
        job=self.new_job('Source analysis'); job.update(source_analysis=True,media_id=media_id,cancellable=True,progress=0)
        for name in ('_source_cancels','_source_reports'):
            if not hasattr(self,name):setattr(self,name,{})
        self._source_cancels[job['id']]=cancel
        directory=CACHE_DIR/'source-analysis'/job['id']
        worker=Worker(lambda:sa.analyze(media,ffmpeg,kinds,float(start),float(end),sample,count,timestamps,width,float(shot_threshold),cancel,lambda p,m:worker.signals.progress.emit((p,m)),directory)); worker.cancel_callback=cancel.set
        def progress(value):job.update(progress=value[0],message=value[1])
        def ready(report):
            self._source_reports[job['id']]=report
            if len(self._source_reports)>20:self._source_reports.pop(next(iter(self._source_reports)))
            job.update(state='Cancelled' if cancel.is_set() else 'Complete',progress=100,result=dict(kinds=kinds,read='get_source_analysis'))
        def failed(error):job.update(state='Cancelled' if cancel.is_set() else 'Failed',error='' if cancel.is_set() else str(error)[-1800:])
        def finished():
            if job['state'] in ('Running','Cancelling'):failed('Source analysis did not complete.')
            job.update(cancellable=False,finished=time.time()); self._source_cancels.pop(job['id'],None)
        worker.signals.progress.connect(progress); worker.signals.result.connect(ready); worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:self.w.start_worker(worker)
        except Exception:cancel.set(); failed('Could not start analysis.'); finished(); raise
        return dict(job)
    def call_get_source_analysis(self,job_id):
        job=self.jobs.get(job_id)
        if not job or not job.get('source_analysis'):raise ValueError('Unknown source-analysis job.')
        if job['state']!='Complete':return dict(job)
        report=getattr(self,'_source_reports',{}).get(job_id)
        if report is None:raise ValueError('This report is no longer held. Run the analysis again.')
        content=[dict(type='text',text=json.dumps(dict(job=dict(job),report=report)))]
        sheet=(report.get('frames') or {}).get('sheet')
        if sheet and Path(sheet).is_file():
            import base64
            content.append(dict(type='image',data=base64.b64encode(Path(sheet).read_bytes()).decode(),mimeType='image/png'))
        return {'_mcp_content':content}
    def call_source_analysis_job_control(self,job_id):
        job=self.jobs.get(job_id); token=getattr(self,'_source_cancels',{}).get(job_id)
        if not job or not token or job['state'] not in ('Running','Cancelling'):raise ValueError('This source analysis is not running.')
        token.set(); job['state']='Cancelling'; return dict(job)
    def call_add_motion_sound_cue(self,revision,item_id,path,time,gain_db=0,event='time',node_id='',channel='',key_time=0):
        import threading
        from .motion_audio_ui import inspect_sound
        from .motion_audio import validate as validate_cues,at
        from .ui import Worker
        self.editing()
        if getattr(self.w,'_closing',False) or getattr(self.w.transport,'closed',False):raise ValueError('The editor is closing.')
        project=self.w.project
        if revision!=globals()['revision'](project):raise ValueError('Project changed. Refresh get_state.')
        item=project.item_by_id(item_id)
        if not item or item.role!='graphic' or not is_motion(item.graphic_type) or project.track_states.get(item.track,{}).get('locked'):raise ValueError('Choose an unlocked motion composition.')
        snapshot=copy.deepcopy(item); scene=snapshot.graphic_data.get('scene',{})
        probe_cue=dict(id=uid(),source=str(Path(path).resolve()),time=time,gain_db=gain_db,event=event,node_id=node_id,channel=channel,key_time=key_time)
        validate_cues([probe_cue])
        if at(probe_cue,scene) is None:raise ValueError('The sound cue event does not exist in this composition.')
        if len(scene.get('sound_cues',[]))>=MAX_CUES:raise ValueError('Maximum %d sound cues per composition.'%MAX_CUES)
        cancel=threading.Event(); settings=copy.deepcopy(self.w.settings); job=self.new_job('Motion sound cue'); job.update(cancellable=True,item_id=item_id)
        if not hasattr(self,'_sound_cancels'):self._sound_cancels={}
        self._sound_cancels[job['id']]=cancel
        worker=Worker(lambda:inspect_sound(probe_cue['source'],settings,cancel)); worker.cancel_callback=cancel.set
        def done(result):
            try:
                if cancel.is_set():job['state']='Cancelled'; return
                if self.w.project is not project or globals()['revision'](project)!=revision or project.item_by_id(item_id)!=snapshot or getattr(self.w,'_closing',False) or self.w.delivery.running or QApplication.activeModalWidget():raise ValueError('The project/editor changed during sound import; no cue was applied.')
                result.pop('peaks',None); cue={**probe_cue,**result}; stage=copy.deepcopy(project)
                stage.item_by_id(item_id).graphic_data['scene'].setdefault('sound_cues',[]).append(cue)
                validate(stage); self.install(stage); job.update(state='Complete',cue_id=cue['id'],cue=cue,revision=globals()['revision'](stage),undoable=True)
            except Exception as error:job.update(state='Failed',error=str(error)[-1500:])
        def failed(error):job.update(state='Cancelled' if cancel.is_set() else 'Failed',error='' if cancel.is_set() else str(error)[-1500:])
        def finished():
            if job['state'] in ('Running','Cancelling'):failed('Sound cue import did not complete.')
            job.update(cancellable=False,finished=__import__('time').time()); self._sound_cancels.pop(job['id'],None)
        worker.signals.result.connect(done); worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:self.w.start_worker(worker)
        except Exception:cancel.set(); failed('Could not start sound import.'); finished(); raise
        return dict(job)
    def call_motion_sound_job_control(self,job_id):
        token=getattr(self,'_sound_cancels',{}).get(job_id)
        if not token or self.jobs[job_id]['state'] not in ('Running','Cancelling'):raise ValueError('This sound import is not running.')
        token.set(); self.jobs[job_id]['state']='Cancelling'; return dict(self.jobs[job_id])
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
    def call_get_state(self,section='all',start=None,end=None,detail='compact'):
        w=self.w
        result=dict(name=w.project.name,revision=revision(w.project),playhead=w.project.playhead,duration=w.project.duration,
            selected_ids=sorted(w.timeline.selected_ids),caption_ids=sorted(w.timeline.selected_caption_ids),
            selected_transition_id=getattr(w.timeline,'selected_transition_id',''),
            background_tasks=sum(not getattr(job,'maintenance',False) for job in w._workers),page={0:'Edit',1:'Deliver'}.get(w.current_page,'Edit'),jobs=self.call_get_jobs())
        if section not in ('all','summary','diagnostics','captions'):raise ValueError('Unknown state section; use all, summary, diagnostics or captions.')
        for bound in (start,end):
            if bound is not None and (isinstance(bound,bool) or not isinstance(bound,(int,float)) or bound<0):raise ValueError('start and end are nonnegative timeline seconds')
        if detail not in ('compact','full'):raise ValueError('detail must be compact or full')
        if section=='all':
            project=w.project.to_dict(); styles=[]
            if start is not None or end is not None:
                lo=0.0 if start is None else start; hi=float('inf') if end is None else end
                project['timeline']=[row for row in project['timeline'] if row['start']+row['duration']>lo and row['start']<hi]
                project['captions']=[row for row in project['captions'] if row['end']>lo and row['start']<hi]
                project['range_note']='Only timeline items and captions overlapping start/end are listed; media, settings, tracks and transitions are complete.'
            if detail=='compact':
                from .range_edit import compact_timeline
                project['timeline']=compact_timeline(project['timeline'])
                project['timeline_note']='Compact: fields equal to their defaults are omitted (see get_capabilities fields for defaults); detail=full returns every field.'
            for caption in project['captions']:
                style=caption.pop('style'); 
                if style not in styles:styles.append(style)
                caption['style_id']=styles.index(style); timings=caption.pop('word_timings',[]); caption['timed_words']=len(timings)
            project['caption_styles']=styles
            project['captions_note']='Compact: style_id indexes caption_styles; use get_state section=captions for full captions with word timings.'
            result['project']=project
        if section=='captions':
            full=w.project.to_dict(); styles=[]; rows=[]
            for caption in full['captions']:
                if (start is None or caption['end']>start) and (end is None or caption['start']<end):
                    style=caption.pop('style')
                    if style not in styles:styles.append(style)
                    caption['style_id']=styles.index(style); rows.append(caption)
            result.update(captions=rows,caption_styles=styles,subtitle_style=full['subtitle_style'],
                          captions_note='style_id indexes caption_styles; word_timings are seconds relative to each caption start.')
        if section=='diagnostics' and getattr(w,'event_monitor',None):
            from .playback_diagnostics_ui import snapshot
            result['playback_diagnostics']=snapshot(w)
        return result
    def call_get_editor_guide(self,section='all'):
        if not isinstance(section,str) or section not in {'all',*GUIDE_SECTIONS}:
            raise ValueError('Unknown guide section; use all or '+', '.join(GUIDE_SECTIONS))
        from .icons import resource_path
        from .version import VERSION
        try:markdown=resource_path('assets','docs','mcp-guide.md').read_text(encoding='utf-8')
        except OSError as error:
            raise RuntimeError('Bundled MCP guide is unavailable; update or repair this installation.') from error
        if section!='all':
            heading='## '+GUIDE_SECTIONS[section]+'\n'
            if heading not in markdown:raise RuntimeError('Bundled MCP guide section is missing; update or repair this installation.')
            start=markdown.index(heading);end=markdown.find('\n## ',start+len(heading))
            markdown=markdown[start:end if end!=-1 else len(markdown)].strip()
        return dict(app_version=VERSION,section=section,sections=['all',*GUIDE_SECTIONS],
                    scope='Neutral technical manual; read get_state and get_capabilities for live editor context.',markdown=markdown)
    def call_get_capabilities(self):
        from .effects import CATALOG
        from .transitions import TRANSITION_SUBSECTIONS
        from .graphics import GRAPHICS_CATALOG
        from .motion import schema
        from .tracking_effect import default_effect, MODES, LOSS_POLICIES
        import inspect
        return dict(editor_guide=dict(tool='get_editor_guide',sections=['all',*GUIDE_SECTIONS],scope='Technical MCP context only; no personal preferences or conversation memory.'),effects=CATALOG,transitions=TRANSITION_SUBSECTIONS,graphics=list(GRAPHICS_CATALOG.keys()),commands={name:str(inspect.signature(getattr(self.w,name))) for name in COMMANDS},fields={c.__name__:{f.name:str(f.type) for f in fields(c)} for c in (ProjectSettings,TimelineItem,MediaItem,Caption,CaptionStyle,Crop,Transform)},
            operations={'add/update/remove':'collection: timeline|captions|transitions, id, values (partial fields; nested dictionaries merge). New timeline entries default to title; media clips require role=normal and media_id; transitions require name, duration, track.',
                'settings/subtitle_style':'values: partial fields','rename_project':'name','add_track':'kind: video|audio','track':'track, optional name, states: locked/visible/muted',
                'duplicate_track/delete_track':'track','move_track':'track, direction: -1|1','split':'ids, at, linked (default true)',
                'trim':'ids, delta, edge: left|right','link':'ids, unlink','insert_media':'ids (media pool IDs), start, track',
                'insert_clip':'media_id, track, start, duration, in_point, role, gain_db, effects, crop, transform; with_audio (video media only) also adds its linked source_audio clip on audio_track (default first unlocked audio track, optional audio_id)',
                'ripple_delete_range':'start, end (timeline seconds): removes the range from every unlocked track, closes the gap, splits and trims captions to the words outside the range, and fixes transitions, like a manual Ripple Delete. Locked tracks are not shifted (listed in details)',
                'fit_region':'id or ids, source_rect {x,y,width,height} (normalized to the full source, default whole), target_rect {x,y,width,height} (normalized to the output frame, top-left origin, default whole), mode fit (default, whole region visible) or fill (box covered, region trimmed to its shape): sets crop and transform and reports layer_px',
                'insert_transition':'name, track, duration, alignment (center/start/end), optional left_item_id, right_item_id, cut_time, properties',
                'set_caption_style':'preset (crime_red, viral_yellow, cyber_cyan, mrbeast_gold, clean_card), properties (partial dict), optional caption_ids',
                'apply_vertical_framing':'mode (center_and_fill, fit_width, fill_916), foreground_track, background_track, optional scale'},
            source_transcripts=dict(generate='generate_source_transcripts',search='search_transcripts',cancel='transcript_job_control',ui='Audio > Search transcript',coordinates='Source seconds with timeline cut occurrences; regenerable local index, not project captions.'),
            source_analysis=dict(analyze='analyze_source_media',result='get_source_analysis',cancel='source_analysis_job_control',kinds=['frames','audio','shots'],sampling=['even','shots','loud_moments'],coordinates='Source seconds of an imported media item; independent of the timeline.'),
            edit_review=dict(structural='review_edit',frames='create_edit_contact_sheet',result='get_edit_contact_sheet',captions='review_caption_timing',placement='anchor_captions_to_video'),
            motion_sound=dict(add='add_motion_sound_cue',cancel='motion_sound_job_control',storage='scene.sound_cues',events=['time','layer_start','layer_end','keyframe'],gain_db=[-60,0],time='Composition source seconds; up to 128 cues (add many at once with add_motion_sound_cues), 60-second sound inputs. Layer/key event must exist. Key dragging follows the bound key; removing the event requires removing/rebinding its cue.'),
            motion_composition=schema(),story_templates=__import__('kinetic_cut.motion_templates',fromlist=['catalog']).catalog(),motion_presets=__import__('kinetic_cut.motion_presets',fromlist=['catalog']).catalog(),
            object_tracking=dict(tool='track_object',cancel_tool='tracking_job_control',
                coordinates='Full-source normalized [x,y,width,height], before crop/transform; source seconds = in_point + (timeline time - start) * speed',
                modes=list(MODES),loss_policies=list(LOSS_POLICIES),defaults=default_effect(),
                analysis='Model-free, asynchronous local region tracking. Sample rate 1–60 fps, 10,000 samples / 1 MiB maximum. Includes forward/backward tracking and manual source-time corrections. Image clips use static/manual regions. Rotation is an appearance property, not automatically tracked.',
                workflow='Read get_state revision. Submit track_object; poll get_jobs. Only Complete changes the project, as one undo step. Changed/locked/closed projects reject late results. No silent downloads. Censor losses require Full frame protection; fresh analysis resets loss review.'),
            guidance='Use inspect_ui/ui_control for all remaining inspector, effects, captions, optional analysis, Power Bin and menu workflows. These use the same controls as the user. Dialogs may require another ui_control call. Models are not downloaded silently. apply_edits is atomic; inspect updated state after every batch.')
    def call_apply_edits(self,revision,operations):
        self.editing()
        if revision!=globals()['revision'](self.w.project):raise ValueError('Project changed. Refresh get_state before editing.')
        details=[]; stage,created=edited(self.w.project,operations,details); self.install(stage)
        result=dict(revision=globals()['revision'](stage),created_ids=created,undoable=True)
        if details:result['details']=details
        return result
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
    def _motion_item(self,item_id):
        item=self.w.project.item_by_id(item_id)
        if not item or item.role!='graphic' or not is_motion(item.graphic_type):raise ValueError('Select a Motion Composition item')
        return item
    def call_add_story_graphic(self,template,properties=None,track='',start=None,duration=None):
        from . import motion_templates as T
        from .motion import validate
        from .motion_fx import lint
        self.editing(); p=self.w.project.settings
        scene,params,d=T.build(template,properties,(p.width,p.height),duration)
        scene=validate(scene); warnings=lint(scene)
        item=self.w.add_graphic_object(name='Motion Composition',track=track or '',start=start,duration=d,properties={'scene':scene})
        if item is None:raise ValueError('Could not add the template')
        return dict(revision=globals()['revision'](self.w.project),item_id=item.id,template=template,parameters=params,track=item.track,start=round(item.start,3),duration=round(item.duration,3),layers=[n['id'] for n in scene['nodes']],warnings=warnings)
    def call_get_motion_composition(self,item_id,seconds=None):
        from .motion import validate
        from .motion_geometry import layout
        item=self._motion_item(item_id); seconds=item.in_point if seconds is None else float(seconds)
        if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid composition time')
        scene=validate(item.graphic_data['scene']); entries,_=layout(scene,seconds)
        return dict(revision=revision(self.w.project),item_id=item.id,seconds=seconds,source_range=[item.in_point,item.in_point+item.source_duration],preset=item.graphic_data.get('preset'),parameters=copy.deepcopy(item.graphic_data.get('parameters',{})),scene=scene,
                    layers=[dict(id=n['id'],visible=entries[n['id']]['visible'],bounds=[entries[n['id']]['hit'].boundingRect().x(),entries[n['id']]['hit'].boundingRect().y(),entries[n['id']]['hit'].boundingRect().width(),entries[n['id']]['hit'].boundingRect().height()]) for n in scene['nodes']])
    def call_get_motion_preview(self,item_id,seconds=None,max_width=640):
        state=self.call_get_motion_composition(item_id,seconds); scene=state['scene']; w,h=scene['canvas']; factor=min(max(160,min(1920,int(max_width)))/w,1920/max(w,h))
        size=(max(2,round(w*factor)),max(2,round(h*factor))); renderer='gpu'
        try:
            from .motion_gpu_render import scene_image
            image=scene_image(scene,state['seconds'],size,self.w.project.settings.fps)
        except Exception:
            from .motion import draw
            image=draw(scene,state['seconds'],size,self.w.project.settings.fps); renderer='painter fallback'
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); image.save(buffer,'PNG')
        return {'_mcp_content':[dict(type='text',text=json.dumps(dict(item_id=item_id,seconds=state['seconds'],coordinates='composition source seconds',alpha=True,renderer=renderer))),dict(type='image',data=bytes(buffer.data().toBase64()).decode(),mimeType='image/png')]}
    def call_get_motion_contact_sheet(self,item_id,times,columns=4,cell_width=270):
        from PySide6.QtGui import QImage,QPainter,QColor,QFont
        from .motion import validate
        item=self._motion_item(item_id); scene=validate(item.graphic_data['scene']); w,h=scene['canvas']
        if not isinstance(times,list) or not 1<=len(times)<=36:raise ValueError('times must list 1-36 composition seconds')
        columns=max(1,min(8,int(columns))); cell=max(120,min(540,int(cell_width))); ch=round(cell*h/max(1,w)); rows=(len(times)+columns-1)//columns
        sheet=QImage(columns*cell,rows*(ch+22),QImage.Format_ARGB32); sheet.fill(QColor('#202226')); painter=QPainter(sheet); renderer='gpu'
        try:
            for n,t in enumerate(times):
                t=float(t)
                if not math.isfinite(t) or t<0:raise ValueError('Invalid composition time')
                try:
                    from .motion_gpu_render import scene_image
                    frame=scene_image(scene,t,(cell,ch),self.w.project.settings.fps)
                except Exception:
                    from .motion import draw
                    frame=draw(scene,t,(cell,ch),self.w.project.settings.fps); renderer='painter fallback'
                x=(n%columns)*cell; y=(n//columns)*(ch+22); painter.fillRect(x,y,cell,ch,QColor('#000000')); painter.drawImage(x,y,frame)
                painter.setPen(QColor('#ffd84d')); font=QFont('Inter'); font.setPixelSize(14); painter.setFont(font); painter.drawText(x+6,y+ch+16,'%.2fs'%t)
        finally:painter.end()
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); sheet.save(buffer,'PNG')
        return {'_mcp_content':[dict(type='text',text=json.dumps(dict(item_id=item_id,times=[float(t) for t in times],columns=columns,renderer=renderer,coordinates='composition source seconds'))),dict(type='image',data=bytes(buffer.data().toBase64()).decode(),mimeType='image/png')]}
    def call_motion_scene_file(self,operation,path,revision=None,item_id='',track='',start=None,duration=None,overwrite=False):
        from .motion import validate as validate_scene
        file=Path(path).expanduser()
        if file.suffix.lower()!='.json':raise ValueError('Scene files must be .json (project files are never read or written here)')
        if operation=='save':
            item=self._motion_item(item_id)
            if file.exists() and not overwrite:raise ValueError('File exists; pass overwrite=true to replace it')
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(json.dumps(dict(scene=item.graphic_data['scene'],duration=item.duration),indent=1),encoding='utf-8')
            return dict(path=str(file),item_id=item_id,layers=len(item.graphic_data['scene'].get('nodes',[])))
        if operation!='load':raise ValueError('operation must be load or save')
        if not file.is_file() or file.stat().st_size>20*1024*1024:raise ValueError('Scene file not found or larger than 20 MB')
        data=json.loads(file.read_text(encoding='utf-8')); scene=data.get('scene',data) if isinstance(data,dict) else None
        if not isinstance(scene,dict):raise ValueError('The file must hold a scene object')
        p=self.w.project.settings; scene.setdefault('canvas',[p.width,p.height]); scene=validate_scene(scene)
        length=float(duration or (data.get('duration') if isinstance(data,dict) else None) or 5)
        if item_id:
            if revision is None:raise ValueError('revision is required to replace a composition')
            result=self._motion_edit(revision,item_id,lambda graphic:{**graphic,'scene':scene})
            return dict(result,layers=len(scene['nodes']))
        self.editing()
        item=self.w.add_graphic_object(name='Motion Composition',track=track or '',start=start,duration=length,properties={'scene':scene})
        if item is None:raise ValueError('Could not add the composition')
        return dict(revision=globals()['revision'](self.w.project),item_id=item.id,track=item.track,start=round(item.start,3),duration=round(item.duration,3),layers=len(scene['nodes']))
    def call_list_fonts(self,query='',limit=200):
        from PySide6.QtGui import QFontDatabase
        from .caption_fonts import load_fonts
        from .icons import resource_path
        load_fonts(); bundled=set()
        for file in resource_path('assets','fonts').iterdir():
            if file.suffix.lower() in ('.ttf','.otf'):
                font_id=QFontDatabase.addApplicationFont(str(file))
                if font_id>=0:bundled.update(QFontDatabase.applicationFontFamilies(font_id))
        q=(query or '').lower(); out=[]
        for family in sorted(set(QFontDatabase.families())|bundled):
            if q and q not in family.lower():continue
            styles=QFontDatabase.styles(family)
            out.append(dict(family=family,bundled=family in bundled,styles=styles,italic=any('italic' in s.lower() or 'oblique' in s.lower() for s in styles)))
        out.sort(key=lambda f:(not f['bundled'],f['family'].lower()))
        return dict(fonts=out[:max(1,min(500,int(limit)))],total=len(out),note='Use family names in text layers (font) and runs (font). Italic/bold per run: runs=[{text,italic,bold,font,size,fill}].')
    def call_add_motion_sound_cues(self,revision,item_id,cues):
        import threading
        from .motion_audio_ui import inspect_sound
        from .motion_audio import validate as validate_cues,at
        from .ui import Worker
        self.editing(); project=self.w.project
        if revision!=globals()['revision'](project):raise ValueError('Project changed. Refresh get_state.')
        item=project.item_by_id(item_id)
        if not item or item.role!='graphic' or not is_motion(item.graphic_type) or project.track_states.get(item.track,{}).get('locked'):raise ValueError('Choose an unlocked motion composition.')
        if not isinstance(cues,list) or not 1<=len(cues)<=MAX_CUES:raise ValueError('Provide 1-%d cues'%MAX_CUES)
        snapshot=copy.deepcopy(item); scene=snapshot.graphic_data.get('scene',{})
        if len(scene.get('sound_cues',[]))+len(cues)>MAX_CUES:raise ValueError('A composition supports at most %d sound cues.'%MAX_CUES)
        probes=[]
        for raw in cues:
            if not isinstance(raw,dict) or not raw.get('path'):raise ValueError('Every cue needs a path and time')
            probe=dict(id=uid(),source=str(Path(raw['path']).resolve()),time=float(raw.get('time',0)),gain_db=float(raw.get('gain_db',0)),event=raw.get('event','time'),node_id=raw.get('node_id',''),channel=raw.get('channel',''),key_time=float(raw.get('key_time',0)))
            validate_cues([probe])
            if at(probe,scene) is None:raise ValueError('Cue event does not exist: %s'%probe['node_id'])
            probes.append(probe)
        cancel=threading.Event(); settings=copy.deepcopy(self.w.settings); job=self.new_job('Motion sound cues'); job.update(cancellable=True,item_id=item_id,count=len(probes))
        if not hasattr(self,'_sound_cancels'):self._sound_cancels={}
        self._sound_cancels[job['id']]=cancel
        def work():
            results={}; out=[]
            for probe in probes:
                if cancel.is_set():break
                if probe['source'] not in results:results[probe['source']]=inspect_sound(probe['source'],settings,cancel)
                result=dict(results[probe['source']]); result.pop('peaks',None); out.append({**probe,**result})
            return out
        worker=Worker(work); worker.cancel_callback=cancel.set
        def done(result):
            try:
                if cancel.is_set():job['state']='Cancelled'; return
                if self.w.project is not project or globals()['revision'](project)!=revision or project.item_by_id(item_id)!=snapshot or getattr(self.w,'_closing',False) or self.w.delivery.running or QApplication.activeModalWidget():raise ValueError('The project changed while sounds were read; nothing was added.')
                stage=copy.deepcopy(project); stage.item_by_id(item_id).graphic_data['scene'].setdefault('sound_cues',[]).extend(result)
                validate(stage); self.install(stage); job.update(state='Complete',cue_ids=[c['id'] for c in result],revision=globals()['revision'](stage),undoable=True)
            except Exception as error:job.update(state='Failed',error=str(error)[-1500:])
        def failed(error):job.update(state='Cancelled' if cancel.is_set() else 'Failed',error='' if cancel.is_set() else str(error)[-1500:])
        def finished():
            if job['state'] in ('Running','Cancelling'):failed('Sound cue import did not complete.')
            job.update(cancellable=False,finished=__import__('time').time()); self._sound_cancels.pop(job['id'],None)
        worker.signals.result.connect(done); worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:self.w.start_worker(worker)
        except Exception:cancel.set(); failed('Could not start sound import.'); finished(); raise
        return dict(job)
    def call_motion_assets(self,operation,revision=None,item_id='',name='',x=None,y=None,time=None,layer_ids=None,category=''):
        from . import motion_assets as A
        if operation=='list':
            items=[entry for entry in A.catalogue() if not category or entry['category']==category]
            return dict(assets=[{k:v for k,v in entry.items() if k!='file'} for entry in items],categories=list(A.CATEGORIES))
        if operation=='insert':
            if revision is None or not item_id or not name:raise ValueError('insert needs revision, item_id and name')
            item=self._motion_item(item_id); at=item.in_point if time is None else float(time)
            holder={}
            def change(graphic):
                scene,group=A.insert(graphic['scene'],name,x,y,at); holder['group']=group; return {**graphic,'scene':scene}
            result=self._motion_edit(revision,item_id,change); return dict(result,group_id=holder['group'])
        if operation=='save':
            item=self._motion_item(item_id)
            if not name or not layer_ids:raise ValueError('save needs name and layer_ids')
            at=item.in_point if time is None else float(time)
            path=A.save(A.capture(item.graphic_data['scene'],list(layer_ids),name,at)); return dict(saved=name,path=str(path))
        raise ValueError('operation must be list, insert or save')
    def _motion_edit(self,current_revision,item_id,fn):
        self.editing()
        if current_revision!=revision(self.w.project):raise ValueError('Project changed. Refresh get_state before editing.')
        item=self._motion_item(item_id)
        if self.w.project.track_states.get(item.track,{}).get('locked'):raise ValueError('Destination track is locked')
        stage=copy.deepcopy(self.w.project); target=stage.item_by_id(item_id); target.graphic_data=fn(copy.deepcopy(target.graphic_data)); validate(stage); self.install(stage)
        return dict(revision=revision(self.w.project),item_id=item_id,undoable=True)
    def call_edit_motion_composition(self,revision,item_id,operations):
        from .motion_editing import apply
        item=self._motion_item(item_id); operations=self._composition_clock(item,operations)
        def change(data):data['scene']=apply(data['scene'],operations); return data
        return self._motion_edit(revision,item_id,change)
    @staticmethod
    def _composition_clock(item,operations):
        """Operations may set clock:'timeline' to give times in timeline seconds; convert them to composition source seconds."""
        if not isinstance(operations,list):return operations
        out=[]
        for op in operations:
            if isinstance(op,dict) and op.get('clock')=='timeline':
                op=dict(op); op.pop('clock'); convert=lambda v:item.in_point+(float(v)-item.start)*item.speed
                for key in ('time','start'):
                    if key in op:op[key]=convert(op[key])
                if isinstance(op.get('times'),list):op['times']=[convert(v) for v in op['times']]
                for key in ('duration','attack','decay'):
                    if key in op:op[key]=float(op[key])*item.speed
            out.append(op)
        return out
    def call_configure_motion_preset(self,revision,item_id,properties):
        from .motion_presets import update
        return self._motion_edit(revision,item_id,lambda data:update(data,properties))
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
    def call_track_object(self,revision,item_id,reference_source_time,region,anchors=None,
                          mode=None,properties=None,sample_fps=15,search_radius=.22,
                          confidence_threshold=.58,existing_effect_index=None):
        self.editing()
        if getattr(self.w.transport,'closed',False):raise ValueError('The editor is closing; object tracking cannot start.')
        project=self.w.project
        if revision!=globals()['revision'](project):raise ValueError('Project changed. Refresh get_state before tracking.')
        item=project.item_by_id(item_id)
        if not item or item.track not in project.video_tracks or project.track_states.get(item.track,{}).get('locked'):
            raise ValueError('Select an unlocked video/image clip before tracking.')
        media=project.media_by_id(item.media_id)
        if not media or media.kind not in ('video','image') or not Path(media.path).is_file():
            raise ValueError('Object tracking requires an available video or still-image source.')
        if getattr(self.w,'_tracking_cancel',None) is not None:
            raise ValueError('Another object analysis is running. Cancel it or wait for completion.')
        from .object_tracking import analyze, validate as validate_analysis, _box
        from .tracking_effect import NAME, default_effect, validate as validate_effect, export_error
        if existing_effect_index is not None:
            if (isinstance(existing_effect_index,bool) or not isinstance(existing_effect_index,int)
                    or not 0<=existing_effect_index<len(item.effects) or item.effects[existing_effect_index].get('name')!=NAME):
                raise ValueError('existing_effect_index must identify an Object Tracking effect on this clip.')
            effect=copy.deepcopy(item.effects[existing_effect_index])
            if mode is None:mode=effect.get('mode','Censor Bar')
            previous_mode=effect.get('mode','Censor Bar')
            effect['mode']=mode
            if mode!=previous_mode:effect['loss_policy']=default_effect(mode)['loss_policy']
        else:
            mode=mode or 'Censor Bar'; effect=default_effect(mode)
        if properties is None:properties={}
        protected={'name','analysis','mode','enabled','loss_reviewed'}
        if not isinstance(properties,dict) or set(properties)-set(default_effect(mode)) or set(properties)&protected:
            raise ValueError('Unknown or protected tracking property. Supply appearance/loss-policy properties; analysis is generated locally.')
        effect.update(copy.deepcopy(properties)); effect['analysis']={}; effect['loss_reviewed']=False
        effect=validate_effect(effect)
        region=_box(region)
        def bounded_number(value,low,high,label):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
                raise ValueError('Invalid object tracking '+label)
            return float(value)
        start=item.in_point; end=start+item.source_duration
        reference_source_time=bounded_number(reference_source_time,start,end,'reference source time')
        sample_fps=bounded_number(sample_fps,1,60,'sample rate')
        search_radius=bounded_number(search_radius,.02,.6,'search radius')
        confidence_threshold=bounded_number(confidence_threshold,.2,.95,'confidence threshold')
        if anchors is None:anchors=[]
        if not isinstance(anchors,list) or len(anchors)>128:raise ValueError('Provide at most 128 source-time correction anchors.')
        anchors=copy.deepcopy(anchors)
        for anchor in anchors:
            if not isinstance(anchor,dict) or set(anchor)-{'time','box'} or 'box' not in anchor:
                raise ValueError('Correction anchors require source time and normalized box only.')
            anchor['time']=bounded_number(anchor.get('time'),start,end,'correction source time'); anchor['box']=_box(anchor['box'])
        import threading
        from .ui import Worker
        snapshot=copy.deepcopy(item); media_snapshot=copy.deepcopy(media)
        cancel=threading.Event(); job=self.new_job('Object Tracking'); job.update(progress=0.,message='Starting local object analysis',item_id=item.id,cancellable=True)
        self._tracking_jobs[job['id']]=cancel; self.w._tracking_cancel=cancel
        worker=Worker(lambda:analyze(media_snapshot,snapshot,reference_source_time,region,anchors,
            lambda percent,message:worker.signals.progress.emit((percent,message)),cancel,
            sample_fps=sample_fps,search_radius=search_radius,confidence_threshold=confidence_threshold))
        def progress(value):
            if job['state']=='Running':job.update(progress=max(0.,min(100.,float(value[0]))),message=str(value[1])[:500])
        def done(analysis):
            try:
                if cancel.is_set():job.update(state='Cancelled',message='Tracking cancelled; clip unchanged.'); return
                current=project.item_by_id(item.id)
                source=project.media_by_id(item.media_id)
                if (getattr(self.w.transport,'closed',False) or self.w.project is not project
                        or current is not item or current!=snapshot or source is not media or source!=media_snapshot
                        or self.w.current_page!=0 or self.w.delivery.running or QApplication.activeModalWidget()
                        or project.track_states.get(item.track,{}).get('locked')
                        or globals()['revision'](project)!=revision):
                    raise ValueError('The project, clip, source, track or editor state changed during tracking. No changes were applied; refresh get_state and retry.')
                if not validate_analysis(analysis):raise ValueError('Tracking returned an invalid or incomplete trajectory; no changes were applied.')
                result_effect=copy.deepcopy(effect); result_effect.update(analysis=analysis,anchors=anchors,
                    sample_fps=sample_fps,search_radius=search_radius,confidence_threshold=confidence_threshold,loss_reviewed=False)
                stage=copy.deepcopy(project); target=stage.item_by_id(item.id)
                if existing_effect_index is None:target.effects.append(result_effect); index=len(target.effects)-1
                else:target.effects[existing_effect_index]=result_effect; index=existing_effect_index
                # Validate the final effect combination, including a proposed
                # Follow Crop, before touching the live project/history.
                error=export_error(result_effect,stage.media_by_id(item.media_id),target)
                if error:raise ValueError(error)
                validate(stage)
                self.install(stage)
                job.update(state='Complete',progress=100.,message='Object Tracking applied; Undo available.',
                    effect_index=index,mode=mode,sample_count=len(analysis['frames']),
                    lost_samples=sum(frame['status']=='lost' for frame in analysis['frames']),
                    revision=globals()['revision'](stage),undoable=True)
            except Exception as error:job.update(state='Failed',error=str(error)[-2000:])
        def failed(detail):
            job.update(state='Cancelled' if cancel.is_set() else 'Failed',
                       error='' if cancel.is_set() else str(detail)[-2000:],message='Tracking cancelled; clip unchanged.' if cancel.is_set() else 'Object analysis failed; clip unchanged.')
        def finished():
            if job['state'] in ('Running','Cancelling'):
                failed('Tracking did not complete; no changes were applied.')
            if getattr(self.w,'_tracking_cancel',None) is cancel:self.w._tracking_cancel=None
            self._tracking_jobs.pop(job['id'],None); job.update(cancellable=False,finished=time.time())
        worker.cancel_callback=cancel.set
        worker.signals.progress.connect(progress); worker.signals.result.connect(done)
        worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:self.w.start_worker(worker)
        except Exception:
            cancel.set(); finished(); job.update(state='Failed',error='Could not start object tracking worker.'); raise
        return dict(job)
    def call_tracking_job_control(self,job_id,operation):
        if operation!='cancel':raise ValueError('Use cancel for an Object Tracking job.')
        cancel=self._tracking_jobs.get(job_id); job=self.jobs.get(job_id)
        if cancel is None or job is None or job['state'] not in ('Running','Cancelling'):
            raise ValueError('This Object Tracking job is not running.')
        cancel.set(); job.update(state='Cancelling',message='Cancelling object analysis; waiting for source handles to close.')
        return dict(job)
    def call_import_media(self,paths):
        self.editing()
        if not isinstance(paths,list) or not 1<=len(paths)<=100:raise ValueError('Provide 1–100 local media paths')
        paths=list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
        if any(not Path(p).is_file() for p in paths):raise ValueError('One or more media files do not exist')
        from .ui import Worker
        from .media import probe
        import threading
        project=self.w.project; settings=copy.deepcopy(self.w.settings); cancel=threading.Event(); job=self.new_job('Import media')
        def prepare():
            items=[]
            for path in paths:
                if cancel.is_set():raise InterruptedError('Import cancelled')
                items.append(probe(path,settings.get('ffprobe','ffprobe'),settings.get('ffmpeg','ffmpeg'),timeout=30))
            if cancel.is_set():raise InterruptedError('Import cancelled')
            return items
        worker=Worker(prepare); worker.cancel_callback=cancel.set
        def finish(items):
            if cancel.is_set() or getattr(self.w,'_closing',False):return
            if project is not self.w.project:job.update(state='Failed',error='Project changed during import; retry in the intended project'); return
            self.w.media_added(items)
            from .media_insert import source_key
            job.update(state='Complete',media_ids=[m.id for m in project.media if source_key(m.path) in {source_key(p) for p in paths}])
        def finished():
            if job['state']=='Running':
                job.update(state='Cancelled' if cancel.is_set() or getattr(self.w,'_closing',False) else 'Failed',
                           error='Import cancelled; no media was imported.' if cancel.is_set() else 'Import did not complete.')
            job['finished']=time.time()
        worker.signals.result.connect(finish); worker.signals.error.connect(lambda e:job.update(state='Cancelled' if cancel.is_set() else 'Failed',error=e[-2000:]))
        worker.signals.finished.connect(finished); self.w.start_worker(worker)
        return dict(job)
    def call_download_media(self,url,mode='video',target_res='',cookies_path='',auto_import=True,wait=True):
        self.editing()
        if not url or not str(url).strip():raise ValueError('URL cannot be empty')
        url=str(url).strip(); mode='audio' if str(mode).lower()=='audio' else 'video'
        from .ui import Worker
        from .downloader_dialog import download_media_synchronous
        from .media import probe
        import threading
        job=self.new_job(f'Download media ({mode})')
        project=self.w.project; settings=copy.deepcopy(self.w.settings); cancel=threading.Event()
        from PySide6.QtCore import QEventLoop
        loop=QEventLoop(self.w) if wait else None
        result_box={}; error_box=[]

        def cancelled():return cancel.is_set() or getattr(self.w,'_closing',False) or self.w.transport.closed
        def mark_cancelled():job.update(state='Cancelled',error='Download cancelled; no media was imported.')

        def do_download():
            if cancel.is_set():raise InterruptedError('Download cancelled')
            res=download_media_synchronous(url,mode=mode,target_res=target_res,cookies_path=cookies_path or None,cancel_check=cancel.is_set)
            if cancel.is_set():raise InterruptedError('Download cancelled')
            path=res.get('path')
            probe_item=None
            if auto_import and path and Path(path).is_file():
                probe_item=probe(path,settings.get('ffprobe','ffprobe'),settings.get('ffmpeg','ffmpeg'),timeout=30)
            if cancel.is_set():raise InterruptedError('Download cancelled')
            return res, probe_item

        def on_success(payload):
            if cancelled():mark_cancelled(); return
            res,probe_item=payload; media_id=None
            if probe_item is not None and project is self.w.project:
                self.w.media_added([probe_item]); media_id=probe_item.id
            result_box['data']=dict(ok=True,path=res['path'],name=res['name'],title=res.get('title',''),mode=res['mode'],
                                    size_bytes=res.get('size_bytes',0),media_id=media_id,imported=bool(media_id))
            job.update(state='Complete',**result_box['data'])

        def on_failure(err):
            if cancelled():mark_cancelled(); return
            error_box.append(err); job.update(state='Failed',error=err[-2000:])

        def finished():
            if cancelled():mark_cancelled()
            elif job['state']=='Running':
                error_box.append('Download did not complete'); job.update(state='Failed',error=error_box[-1])
            if loop:loop.quit()

        worker=Worker(do_download); worker.cancel_callback=cancel.set
        worker.signals.result.connect(on_success); worker.signals.error.connect(on_failure); worker.signals.finished.connect(finished)
        self.w.start_worker(worker)
        if wait:
            if not cancelled():loop.exec()
            loop.deleteLater()
            if cancelled():mark_cancelled(); raise InterruptedError('Download cancelled')
            if error_box:raise RuntimeError(f'Download failed: {error_box[0]}')
            if 'data' not in result_box:raise RuntimeError('Download did not complete')
            return result_box['data']
        if cancelled():mark_cancelled()
        return dict(job)
    def call_get_jobs(self,job_id=None,finished=5):
        from .render_queue import elapsed
        if isinstance(finished,bool) or not isinstance(finished,int) or not 0<=finished<=100:raise ValueError('finished must be 0-100')
        transcripts=getattr(self.w,'transcript_service',None)
        every=list(self.jobs.values())+(list(transcripts.jobs.values()) if transcripts else [])
        if job_id is not None:
            job=next((j for j in every if j.get('id')==job_id),None)
            if job is None:raise ValueError('Unknown job ID')
            return dict(tasks=[job])
        def compact(job):
            row={}
            for key,value in job.items():
                size=len(json.dumps(value,default=str))
                row[key]=value if size<=1500 else f'(omitted, {size} bytes; get_jobs job_id={job.get("id")} returns it)'
            return row
        running=[j for j in every if j.get('state') in ('Running','Cancelling')]
        done=[j for j in every if j.get('state') not in ('Running','Cancelling')]
        tasks=running+[compact(j) for j in done[-finished:]] if finished else running
        return dict(tasks=tasks,older_finished=max(0,len(done)-finished),renders=[dict(id=j.setdefault('assistant_id',uid()),state=j['state'],path=j['output'],elapsed=elapsed(j),error=j.get('error','')) for j in self.w.delivery.jobs],
                    rendering=self.w.delivery.running,progress=self.w.delivery.progress.value())
    def call_seek(self,seconds):
        if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid seek time')
        self.w.transport.pause(); self.w.seek(min(seconds,self.w.project.duration)); return dict(playhead=self.w.project.playhead)
    def call_get_preview(self,area='preview',max_width=1280):
        if area not in {'preview','workspace'}:raise ValueError('Unknown preview area')
        widget=self.w if area=='workspace' else self.w.preview
        from .ui_capture import capture
        surfaces=[getattr(self.w.preview,'gpu',None)]
        if area=='workspace':surfaces.append(getattr(self.w.timeline,'gpu',None))
        pixels=capture(widget,surfaces); max_width=max(160,min(1920,int(max_width)))
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
            self.w._saved_project_key=self.w._history_key(project)
            from .close_guard import mark_saved
            mark_saved(self.w,project); return dict(checkpoint=backup,revision=revision(project))
        if operation=='save':
            if not path or Path(path).suffix.lower()!='.kcut':raise ValueError('Provide a .kcut output path')
            if Path(path).exists() and not overwrite:raise ValueError('File exists; explicitly set overwrite=true to replace it')
            self.w.compounds.root().save(path); self.w._saved_project_key=self.w._history_key(self.w.project)
            from .close_guard import mark_saved
            mark_saved(self.w)
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
    def call_exit_application(self,discard_unsaved=False):
        if not isinstance(discard_unsaved,bool):raise ValueError('discard_unsaved must be true or false')
        w=self.w
        if getattr(w,'_closing',False):raise ValueError('The app is already closing.')
        if w.delivery.running:raise ValueError('A render is running; wait for it to finish or cancel it with render_control, then exit.')
        from .close_guard import has_unsaved
        unsaved=has_unsaved(w)
        if unsaved and not discard_unsaved:
            raise ValueError(f'"{w.compounds.root().name}" has unsaved changes. Save it with project_file, or call exit_application with discard_unsaved=true to close without saving.')
        w._exit_confirmed=True
        def close():
            if not w.close():w._exit_confirmed=False       # something refused (for example a task that must finish first)
        QTimer.singleShot(400,close)
        return dict(state='closing',discarded_unsaved=bool(unsaved),note='Kinetic Cut closes in a moment and the connection will drop. Relaunch the app and enable the connection to continue.')
    def call_render_control(self,operation):
        if operation=='start':self.w.delivery.render_all()
        elif operation=='cancel':
            cancel=getattr(self.w.delivery,'render_cancel',None)
            if cancel:cancel.set()
        else:raise ValueError('Unknown render operation')
        return self.call_get_jobs()
    def call_editor_command(self,command,arguments=None):
        import inspect,shiboken6
        self.editing()
        if command not in COMMANDS:raise ValueError('Unknown editor command')
        function=getattr(self.w,command); arguments=arguments or {}; inspect.signature(function).bind(**arguments)
        job=self.new_job(command)
        def invoke():
            try:
                before={i.id for i in self.w.project.timeline}; before_captions={c.id for c in self.w.project.captions}
                result=function(**arguments)
                def finish():
                    created=[i.id for i in self.w.project.timeline if i.id not in before]
                    made_captions=[c.id for c in self.w.project.captions if c.id not in before_captions]
                    extra=dict(created_ids=created) if created else {}
                    if command=='generate_captions':
                        report=dict(getattr(self.w,'_caption_report',{}) or {})
                        state=report.get('state')
                        if state in ('refused','failed','cancelled','discarded'):
                            job.update(state='Failed',error=report.get('reason') or report.get('error') or state,report=report);return
                        report['caption_ids']=made_captions[:200]; extra['report']=report
                    job.update(state='Complete',note='Command returned; poll background/render status before claiming work is finished.',**extra)
                if command=='generate_captions' and result is not None:
                    def settle():
                        if not shiboken6.isValid(self.w):return
                        if (getattr(self.w,'_caption_report',{}) or {}).get('state')=='running':QTimer.singleShot(300,settle);return
                        try:finish()
                        except Exception as error:job.update(state='Failed',error=str(error))
                    settle()
                else:finish()
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
