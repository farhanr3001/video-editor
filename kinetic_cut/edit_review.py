"""MCP authoring geometry and conservative structural review."""
import copy
import math
from pathlib import Path
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage


def anchor_captions(window, project, track, caption_ids, margin=16):
    from .keyframes import evaluated
    from .visuals import caption_geometry
    if track not in project.video_tracks:raise ValueError('Choose the webcam video track.')
    if not math.isfinite(margin) or not 0<=margin<=200:raise ValueError('Margin must be 0–200 output pixels.')
    if project.track_states.get('subtitle_1',{}).get('locked'):raise ValueError('The subtitle track is locked.')
    ids=set(caption_ids)
    if not ids or ids-{c.id for c in project.captions}:raise ValueError('Choose existing captions.')
    frame=QRectF(0,0,project.settings.width,project.settings.height); dummy=QImage(1,1,QImage.Format_ARGB32)
    result=[]
    for caption in project.captions:
        if caption.id not in ids:continue
        stamp=(caption.start+caption.end)/2
        item=next((i for i in project.timeline if i.track==track and i.start<=stamp<i.start+i.duration and not i.muted),None)
        if not item or item.role in ('title','graphic','background'):raise ValueError('No webcam clip underneath caption '+caption.id)
        sample=evaluated(item,stamp-item.start)
        if any(abs(v)>1e-6 for v in (sample.transform.rotation,sample.transform.pitch,sample.transform.yaw)):
            raise ValueError('Caption anchoring requires an axis-aligned webcam region.')
        if caption.is_hook:raise ValueError('Disable hook placement before anchoring '+caption.id)
        # Use the production viewer geometry; no playback seek or document swap.
        from .widgets import PreviewCanvas
        from types import SimpleNamespace
        rect=PreviewCanvas._layer_rect(SimpleNamespace(project=project),sample,dummy,frame,item.role=='facecam').intersected(frame)
        rect=rect.adjusted(margin,margin,-margin,-margin)
        if rect.isEmpty():raise ValueError('Webcam region is too small for the requested margin.')
        caption.style=copy.deepcopy(project.caption_style(caption)); caption.customize=True
        style=caption.style; style.anchor='Bottom'; style.alignment='Center'
        style.position_x=rect.center().x()/frame.width(); style.position_y=rect.bottom()/frame.height()
        bounds=caption_geometry(project,caption,frame)[2]
        # Preserve requested typography. Report oversize text rather than hide a
        # font-size change inside a placement command.
        if bounds.width()>rect.width()+1 or bounds.height()>rect.height()+1:
            raise ValueError('Caption '+caption.id+' does not fit the webcam; shorten it or reduce its font size.')
        # Geometry includes antialias padding beyond its glyph anchor.
        style.position_y-=max(0,bounds.bottom()-rect.bottom())/frame.height()
        result.append(dict(caption_id=caption.id,position_x=style.position_x,position_y=style.position_y,anchor_item_id=item.id,sampled_at=stamp))
    return result


def structural(project):
    from .missing_media import export_issues
    from .caption_quality import review
    issues=[dict(kind='missing_media',message=m) for m in export_issues(project)]
    # Only flag gaps in the union of active video coverage; stacked lanes do not
    # need to be individually continuous.
    spans=sorted((max(0,i.start),i.start+i.duration) for i in project.timeline
                 if i.track in project.video_tracks and not i.muted
                 and project.track_states.get(i.track,{}).get('visible',True))
    edge=0
    for start,end in spans:
        if start-edge>1/project.settings.fps:issues.append(dict(kind='video_gap',start=edge,end=start))
        edge=max(edge,end)
    if project.duration-edge>1/project.settings.fps:issues.append(dict(kind='video_gap',start=edge,end=project.duration))
    frame=QRectF(0,0,project.settings.width,project.settings.height)
    safe=frame.adjusted(frame.width()*.08,frame.height()*.08,-frame.width()*.14,-frame.height()*.18)
    from .visuals import caption_geometry
    for caption in project.captions:
        bounds=caption_geometry(project,caption,frame)[2]
        if not frame.contains(bounds):issues.append(dict(kind='caption_outside_frame',caption_id=caption.id,start=caption.start))
        elif not safe.contains(bounds):issues.append(dict(kind='caption_platform_margin',caption_id=caption.id,start=caption.start))
    for item in project.timeline:
        if item.role!='graphic':continue
        if item.graphic_data.get('scene'):
            from .motion_geometry import layout
            from PySide6.QtGui import QTransform
            from .keyframes import evaluated
            sample=evaluated(item,item.duration/2); transform=QTransform()
            transform.translate(sample.transform.x*frame.width(),sample.transform.y*frame.height())
            transform.translate(sample.transform.anchor_x,sample.transform.anchor_y); transform.rotate(sample.transform.rotation)
            transform.scale(sample.transform.scale,sample.transform.effective_scale_y); transform.translate(-sample.transform.anchor_x,-sample.transform.anchor_y)
            transform.translate(-frame.width()/2,-frame.height()/2)
            canvas=item.graphic_data['scene'].get('canvas',[frame.width(),frame.height()])
            transform.scale(frame.width()/canvas[0],frame.height()/canvas[1])
            entries,_=layout(item.graphic_data['scene'],item.in_point+item.source_duration/2)
            for entry in entries.values():
                if not entry['visible'] or entry['node']['kind']=='group':continue
                bounds=transform.map(entry['hit']).boundingRect()
                if not safe.contains(bounds):issues.append(dict(kind='graphic_platform_margin',item_id=item.id,node_id=entry['node']['id'],sampled_at=item.start+item.duration/2))
        for cue in item.graphic_data.get('scene',{}).get('sound_cues',[]):
            if cue.get('source') and not Path(cue['source']).is_file():issues.append(dict(kind='missing_sound_cue',item_id=item.id,source=cue['source']))
        for node in item.graphic_data.get('scene',{}).get('nodes',[]):
            if node.get('kind')=='image' and node.get('source') and not Path(node['source']).is_file():issues.append(dict(kind='missing_graphic_image',item_id=item.id,node_id=node['id'],source=node['source']))
    return dict(duration=project.duration,issues=issues,caption_review=review(project),
                limitations='Structural/geometry checks flag candidates, including intentional gaps. Contact sheets are sampled frames, not proof of continuous playback or exact speech alignment.')
