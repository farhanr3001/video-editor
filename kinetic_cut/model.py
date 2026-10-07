from __future__ import annotations

import json
import copy
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable
from .transitions import Transition


def uid() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Crop:
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0

    def clamped(self) -> "Crop":
        w = min(1.0, max(0.02, self.width))
        h = min(1.0, max(0.02, self.height))
        x = min(1.0 - w, max(0.0, self.x))
        y = min(1.0 - h, max(0.0, self.y))
        return Crop(x, y, w, h)


@dataclass
class Transform:
    x: float = 0.5
    y: float = 0.62
    scale: float = 1.0
    scale_y: float | None = None
    scale_linked: bool = True
    rotation: float = 0.0
    shape: str = "rectangle"
    flip_horizontal: bool = False
    flip_vertical: bool = False
    anchor_x: float = 0.0
    anchor_y: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    @property
    def effective_scale_y(self) -> float:
        return self.scale if self.scale_y is None else self.scale_y


@dataclass
class MediaItem:
    id: str
    path: str
    kind: str
    name: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    thumbnail: str = ""
    timeline_preset: dict = field(default_factory=dict)
    compound: dict = field(default_factory=dict)
    has_alpha: bool = False
    pool_hidden: bool = False
    stream_durations: dict = field(default_factory=dict)
    video_codec: str = ""


@dataclass
class TimelineItem:
    id: str
    media_id: str
    track: str
    start: float
    duration: float
    in_point: float = 0.0
    group_id: str = ""
    crop: Crop = field(default_factory=Crop)
    transform: Transform = field(default_factory=Transform)
    gain_db: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    muted: bool = False
    role: str = "normal"
    link_id: str | None = None
    pan: float = 0.0
    pitch_semitones: float = 0.0
    pitch_cents: float = 0.0
    opacity: float = 100.0
    composite_mode: str = "Normal"
    crop_softness: float = 0.0
    retain_image_position: bool = False
    effects: list[dict] = field(default_factory=list)
    grayscale: bool = False
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    sharpen: float = 0.0
    speed: float = 1.0
    title_text: str = ""
    title_style: Any = None
    tts_enabled: bool = False
    tts_voice: str = ""
    tts_speed: int = 0
    tts_pitch: int = 0
    is_webcam: bool = False
    keyframes: dict[str,list[dict]] = field(default_factory=list)
    graphic_type: str = ""
    graphic_data: dict[str, Any] = field(default_factory=dict)
    source_mismatch: bool = False
    source_requirement: dict = field(default_factory=dict)
    video_preset_id: str = ""

    def __post_init__(self):
        from .keyframes import clean
        self.keyframes=clean(self.keyframes)
        if self.role=="title":
            if self.title_style is None:self.title_style=CaptionStyle(name="Basic Title",animation="none",background_enabled=False)
            elif isinstance(self.title_style,dict):self.title_style=CaptionStyle(**self.title_style)
        elif self.role=="graphic":
            if not isinstance(self.graphic_data,dict):self.graphic_data={}
            if self.graphic_type.lower() in ('motion','motion composition'):
                from .motion import validate,default_scene
                self.graphic_data['scene']=validate(self.graphic_data.get('scene',default_scene()))

    def source_time(self, timeline_time: float) -> float:
        return self.in_point+(timeline_time-self.start)*self.speed

    @property
    def source_duration(self) -> float:
        return self.duration*self.speed


@dataclass
class CaptionStyle:
    name: str = "Impact Pop"
    font: str = "Arial"
    size: int = 72
    color: str = "#55ffff"
    highlight: str = "#E8FF4D"
    outline: str = "#000000"
    outline_width: int = 7
    shadow: int = 3
    animation: str = "pop"
    position_y: float = 0.78
    uppercase: bool = False
    font_face: str = "Bold"
    line_spacing: float = 0.0
    kerning: float = 0.0
    alignment: str = "Center"
    position_x: float = 0.5
    zoom_x: float = 1.0
    zoom_y: float = 1.0
    zoom_linked: bool = True
    opacity: float = 100.0
    anchor: str = "Center"
    shadow_enabled: bool = True
    shadow_color: str = "#000000"
    shadow_x: float = 3.0
    shadow_y: float = 3.0
    shadow_blur: float = 3.0
    shadow_opacity: float = 70.0
    background_enabled: bool = False
    background_color: str = "#000000"
    background_outline: str = "#000000"
    background_outline_width: float = 0.0
    background_radius: float = 0.01
    background_opacity: float = 50.0
    background_override: bool = False
    background_width: float = .9
    background_height: float = .15
    box_style: str = "standard"
    glow_enabled: bool = False
    glow_follow_color: bool = True
    glow_color: str = "#55ffff"
    glow_radius: float = 12.0
    glow_opacity: float = 55.0


@dataclass
class Caption:
    id: str
    start: float
    end: float
    text: str
    style: CaptionStyle = field(default_factory=CaptionStyle)
    is_hook: bool = False
    customize: bool = False
    word_timings: list[dict] = field(default_factory=list)
    highlighted_words: list[int] = field(default_factory=list)


@dataclass
class ProjectSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 60
    blur: float = 28.0
    background_brightness: float = 0.62
    background_contrast: float = 1.05
    normalize_audio: bool = False
    noise_reduction: bool = False
    auto_duck: bool = False
    duck_amount_db: float = -11.0


TRACKS = ("captions", "overlay", "facecam", "main", "background", "sfx", "music")


def default_video_tracks() -> list[str]:
    return ["video_1"]


def default_audio_tracks() -> list[str]:
    return ["audio_1"]


@dataclass
class Project:
    name: str = "Untitled Short"
    path: str = ""
    portable_media: bool = False
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    media: list[MediaItem] = field(default_factory=list)
    timeline: list[TimelineItem] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    subtitle_style: CaptionStyle = field(default_factory=CaptionStyle)
    extra_tracks: list[str] = field(default_factory=list)
    track_states: dict[str, dict[str, bool]] = field(default_factory=dict)
    video_tracks: list[str] = field(default_factory=default_video_tracks)
    audio_tracks: list[str] = field(default_factory=default_audio_tracks)
    track_names: dict[str, str] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    mark_in: float = 0.0
    mark_out: float = 0.0
    playhead: float = 0.0
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    def __post_init__(self):
        self.ensure_track_model()

    @property
    def duration(self) -> float:
        ends = [i.start + i.duration for i in self.timeline]
        ends.extend(c.end for c in self.captions)
        ends.extend(t.start + t.duration for t in self.transitions)
        return max(ends, default=0.0)

    def add_transition(self, transition: Transition) -> None:
        self.transitions = [t for t in self.transitions if t.id != transition.id]
        self.transitions.append(transition)
        self.touch()

    def remove_transition(self, transition_id: str) -> bool:
        before = len(self.transitions)
        self.transitions = [t for t in self.transitions if t.id != transition_id]
        if len(self.transitions) != before:
            self.touch()
            return True
        return False

    def transition_by_id(self, transition_id: str) -> Transition | None:
        return next((t for t in self.transitions if t.id == transition_id), None)

    def transitions_for_track(self, track: str) -> list[Transition]:
        return [t for t in self.transitions if t.track == track]

    def transitions_for_item(self, item_id: str) -> list[Transition]:
        return [t for t in self.transitions if t.left_item_id == item_id or t.right_item_id == item_id]

    def transition_at_time(self, track: str, t: float) -> Transition | None:
        return next((tr for tr in self.transitions if tr.track == track and tr.contains_time(t)), None)

    def media_by_id(self, media_id: str) -> MediaItem | None:
        return next((m for m in self.media if m.id == media_id), None)

    def item_by_id(self, item_id: str) -> TimelineItem | None:
        return next((i for i in self.timeline if i.id == item_id), None)

    def add_media(self, media: MediaItem) -> None:
        if not any(Path(m.path) == Path(media.path) for m in self.media):
            self.media.append(media)
            self.touch()

    def split(self, item_id: str, at: float) -> list[TimelineItem]:
        item = self.item_by_id(item_id)
        if not item or at <= item.start + 0.03 or at >= item.start + item.duration - 0.03:
            return []
        offset = at - item.start
        right = TimelineItem(**asdict(item))
        right.id = uid()
        right.start = at
        right.duration = item.duration - offset
        right.in_point = item.in_point + offset*item.speed
        right.crop = Crop(**right.crop)
        right.transform = Transform(**right.transform)
        from .keyframes import shift
        shift(right,offset)
        item.duration = offset
        self.timeline.append(right)
        self.touch()
        return [item, right]

    def linked_items(self, item: TimelineItem) -> list[TimelineItem]:
        key = item.group_id if item.link_id is None else item.link_id
        if not key:
            return [item]
        return [candidate for candidate in self.timeline
                if (candidate.group_id if candidate.link_id is None else candidate.link_id) == key]

    def link_selection(self, ids: Iterable[str], unlink=False) -> None:
        selected=set(ids); key="" if unlink else uid()
        for item in self.timeline:
            if item.id in selected:item.link_id=key
        self.touch()

    def split_selection(self, ids: Iterable[str], at: float, linked=True) -> list[str]:
        ids=set(ids); selected={i.id for i in self.timeline if i.id in ids}
        if linked:
            keys={i.group_id if i.link_id is None else i.link_id for i in self.timeline if i.id in selected}
            keys.discard(""); keys.discard(None)
            selected.update(i.id for i in self.timeline if (i.group_id if i.link_id is None else i.link_id) in keys)
        right_links={}; result=[]
        for item in list(self.timeline):
            if item.id not in selected:continue
            if self.track_states.get(item.track,{}).get("locked",False):continue
            key=item.group_id if item.link_id is None else item.link_id
            pair=self.split(item.id,at)
            if pair:
                pair[1].link_id=right_links.setdefault(key,uid()) if key and linked else ""
                pair[1].group_id=pair[1].link_id or uid()
                result.append(pair[1].id)
        return result

    def caption_style(self, caption: Caption) -> CaptionStyle:
        return caption.style if caption.customize or caption.is_hook else self.subtitle_style

    def trim_items(self, ids: Iterable[str], delta: float, edge: str) -> None:
        ids=set(ids); items=[i for i in self.timeline if i.id in ids and not self.track_states.get(i.track,{}).get("locked")]
        if not items:return
        low=-float("inf"); high=float("inf")
        for item in items:
            media=self.media_by_id(item.media_id); still=item.role in {"title", "graphic"} or bool(media and media.kind=="image")
            if edge=="left":
                low=max(low,-item.start if still else -min(item.start,item.in_point/item.speed)); high=min(high,item.duration-.05)
            else:
                low=max(low,.05-item.duration)
                high=min(high,36000-item.duration if still else max(0,(media.duration-item.in_point)/item.speed-item.duration) if media else 0)
        delta=max(low,min(high,delta))
        for item in items:
            if edge=="left":
                from .keyframes import shift
                shift(item,delta)
                item.start+=delta; item.duration-=delta
                media=self.media_by_id(item.media_id)
                if (item.role=='graphic' and item.graphic_type.lower() in ('motion','motion composition')) or (item.role not in {"title", "graphic"} and media and media.kind!="image"):
                    item.in_point=max(0,item.in_point+delta*item.speed)
            else:item.duration+=delta
            item.fade_in=min(item.fade_in,item.duration); item.fade_out=min(item.fade_out,item.duration)
        self.touch()

    def retime_items(self, ids: Iterable[str], speed: float, anchor="left") -> None:
        ids=set(ids); speed=max(.1,min(8.,speed))
        items=[i for i in self.timeline if i.id in ids and not self.track_states.get(i.track,{}).get("locked")]
        for item in items:
            end=item.start+item.duration; source_duration=item.source_duration
            duration=max(.05,source_duration/speed)
            if anchor=="right":duration=min(duration,end); item.start=end-duration
            ratio=duration/item.duration; item.duration=duration; item.speed=source_duration/duration
            from .keyframes import stretch
            stretch(item,ratio)
            item.fade_in=min(duration,item.fade_in*ratio); item.fade_out=min(duration,item.fade_out*ratio)
        self.touch()

    def overwrite(self, placed_ids: Iterable[str]) -> None:
        """Subtract placed intervals from other clips on their destination lanes."""
        placed=set(placed_ids); cutters=[i for i in self.timeline if i.id in placed]
        survivors=[]; fragments=[]
        for original in self.timeline:
            if original.id in placed or self.track_states.get(original.track,{}).get("locked"):
                survivors.append(original); continue
            spans=[(original.start,original.start+original.duration)]
            for cutter in cutters:
                if cutter.track!=original.track:continue
                lo,hi=cutter.start,cutter.start+cutter.duration; remaining=[]
                for a,b in spans:
                    if hi<=a+1e-7 or lo>=b-1e-7:remaining.append((a,b)); continue
                    if lo>a+1e-7:remaining.append((a,lo))
                    if hi<b-1e-7:remaining.append((hi,b))
                spans=remaining
            if spans==[(original.start,original.start+original.duration)]:survivors.append(original); continue
            key=original.group_id if original.link_id is None else original.link_id
            for n,(a,b) in enumerate(spans):
                if b-a<.0001:continue
                item=copy.deepcopy(original); item.id=original.id if n==0 else uid(); item.start=a; item.duration=b-a
                from .keyframes import shift
                shift(item,a-original.start)
                media=self.media_by_id(item.media_id)
                item.in_point=0 if media and media.kind=="image" else original.source_time(a)
                item.fade_in=min(item.duration,original.fade_in) if abs(a-original.start)<1e-7 else 0
                item.fade_out=min(item.duration,original.fade_out) if abs(b-original.start-original.duration)<1e-7 else 0
                item.link_id=""; survivors.append(item); fragments.append((item,key,round(a,6),round(b,6)))
        # Symmetric AV fragments remain paired; asymmetric overwrites unlink them.
        groups={}
        for item,key,a,b in fragments:
            if key:groups.setdefault((key,a,b),[]).append(item)
        for group in groups.values():
            if len(group)>1:
                link=uid()
                for item in group:item.link_id=link
        self.timeline=survivors; self.touch()

    def overwrite_captions(self,placed_ids,notify=True):
        """Subtract placed subtitle intervals while retaining unaffected tails."""
        if self.track_states.get('subtitle_1',{}).get('locked'):return
        placed=set(placed_ids); cutters=sorted((c for c in self.captions if c.id in placed),key=lambda c:c.start); survivors=[]
        priority={c.id:n for n,c in enumerate(cutters)}
        for original in self.captions:
            spans=[(original.start,original.end)]
            for cutter in cutters:
                if original.id in placed and priority[cutter.id]<=priority[original.id]:continue
                remaining=[]
                for a,b in spans:
                    if cutter.end<=a+1e-7 or cutter.start>=b-1e-7:remaining.append((a,b)); continue
                    if cutter.start>a+1e-7:remaining.append((a,cutter.start))
                    if cutter.end<b-1e-7:remaining.append((cutter.end,b))
                spans=remaining
            if spans==[(original.start,original.end)]:survivors.append(original); continue
            for n,(a,b) in enumerate(spans):
                if b-a<.0001:continue
                part=copy.deepcopy(original); part.id=original.id if n==0 else uid(); part.start=a; part.end=b; survivors.append(part)
                from .caption_words import shift_origin
                shift_origin(part,a-original.start)
        self.captions=survivors
        if notify:self.touch()

    def delete(self, item_ids: Iterable[str], ripple: bool = False, caption_ids: Iterable[str] = ()) -> None:
        ids = set(item_ids)
        removed = [i for i in self.timeline if i.id in ids and not self.track_states.get(i.track,{}).get("locked")]
        caption_ids=set(caption_ids) if not self.track_states.get("subtitle_1",{}).get("locked") else set()
        removed_captions=[c for c in self.captions if c.id in caption_ids]
        if not removed and not removed_captions:
            return
        first = min([i.start for i in removed]+[c.start for c in removed_captions])
        last = max([i.start + i.duration for i in removed]+[c.end for c in removed_captions])
        ids={i.id for i in removed}
        self.timeline = [i for i in self.timeline if i.id not in ids]
        self.captions = [c for c in self.captions if c.id not in caption_ids]
        if ripple:
            gap = last - first
            for item in self.timeline:
                if item.start >= last - 0.001 and not self.track_states.get(item.track,{}).get("locked"):
                    item.start = max(first, item.start - gap)
            for caption in self.captions:
                if caption.start >= last - 0.001 and not self.track_states.get("subtitle_1",{}).get("locked"):
                    caption.start -= gap
                    caption.end -= gap
        self.touch()

    def ripple_ranges(self, group_id: str, keep: list[tuple[float, float]], item_id=None) -> None:
        """Pack timeline-relative keep ranges, preserving each clip's source speed."""
        main=self.item_by_id(item_id) if item_id else None
        linked = self.linked_items(main) if main else [i for i in self.timeline if i.group_id == group_id]
        if main:linked=[i for i in linked if abs(i.start-main.start)<.001 and abs(i.duration-main.duration)<.001]
        if not linked or not keep:
            return
        base_start = min(i.start for i in linked)
        ids = {i.id for i in linked}
        self.timeline = [i for i in self.timeline if i.id not in ids]
        cursor = base_start
        for keep_start, keep_end in keep:
            length = keep_end - keep_start
            if length <= 0.025:
                continue
            new_group = uid()
            for original in linked:
                payload = asdict(original)
                payload.update(id=uid(), start=cursor,
                               duration=length,
                                 in_point=original.in_point + keep_start*original.speed,
                                 group_id=new_group,link_id=new_group)
                payload["crop"] = Crop(**payload["crop"])
                payload["transform"] = Transform(**payload["transform"])
                self.timeline.append(TimelineItem(**payload))
            cursor += length
        removed = max(i.duration for i in linked) - (cursor - base_start)
        original_end = base_start + max(i.duration for i in linked)
        for item in self.timeline:
            if item.start >= original_end - 0.001 and item.group_id not in {i.group_id for i in linked}:
                item.start = max(base_start, item.start - max(0, removed))
        self.touch()

    def touch(self) -> None:
        self.modified_at = time.time()

    def ensure_track_model(self) -> None:
        """Migrate older semantic-track projects to ordered generic NLE tracks."""
        legacy_map = {"background": ("video_1", "background"), "main": ("video_2", "content"),
                      "facecam": ("video_3", "facecam"), "overlay": ("video_4", "normal"),
                      "sfx": ("audio_1", "sfx"), "music": ("audio_2", "music")}
        for item in self.timeline:
            if item.track in legacy_map:
                item.track, migrated_role = legacy_map[item.track]
                if item.role == "normal": item.role = migrated_role
        used_video = {i.track for i in self.timeline if i.track.startswith("video_")}
        used_audio = {i.track for i in self.timeline if i.track.startswith("audio_")}
        for track in sorted(used_video, key=_track_number):
            if track not in self.video_tracks:self.video_tracks.append(track)
        for track in sorted(used_audio, key=_track_number):
            if track not in self.audio_tracks:self.audio_tracks.append(track)
        self.video_tracks = list(dict.fromkeys(self.video_tracks)) or ["video_1"]
        self.audio_tracks = list(dict.fromkeys(self.audio_tracks)) or ["audio_1"]
        for index, track in enumerate(self.video_tracks, 1):self.track_names.setdefault(track, f"Video {index}")
        for index, track in enumerate(self.audio_tracks, 1):self.track_names.setdefault(track, f"Audio {index}")
        for track in [*self.video_tracks, *self.audio_tracks]:
            self.track_states.setdefault(track, {"visible": True, "locked": False, "muted": False})
        for track in self.audio_tracks:
            state=self.track_states[track]
            if not state.get("visible",True):state["muted"]=True; state["visible"]=True

    def add_track(self, kind: str) -> str:
        tracks = self.video_tracks if kind == "video" else self.audio_tracks
        prefix = "video" if kind == "video" else "audio"
        number = max((_track_number(x) for x in tracks), default=0) + 1
        track = f"{prefix}_{number}"; tracks.append(track)
        self.track_names[track] = f"{'Video' if kind == 'video' else 'Audio'} {len(tracks)}"
        self.track_states[track] = {"visible": True, "locked": False, "muted": False}
        self.touch(); return track

    def move_track(self, track: str, direction: int) -> bool:
        tracks = self.video_tracks if track in self.video_tracks else self.audio_tracks if track in self.audio_tracks else []
        if not tracks:return False
        index=tracks.index(track); target=index+direction
        if target < 0 or target >= len(tracks):return False
        tracks[index],tracks[target]=tracks[target],tracks[index]; self.touch(); return True

    def duplicate_track(self, track: str) -> str:
        """Copy a lane above its source; never attach copies to original links."""
        if track not in self.video_tracks+self.audio_tracks:return ""
        video=track in self.video_tracks; tracks=self.video_tracks if video else self.audio_tracks
        at=tracks.index(track)+(1 if video else 0)
        target=self.add_track("video" if video else "audio"); tracks.remove(target); tracks.insert(at,target)
        self.track_names[target]=self.track_names.get(track,track)+" Copy"
        self.track_states[target]=copy.deepcopy(self.track_states.get(track,{})); self.track_states[target]["locked"]=False
        originals=[i for i in self.timeline if i.track==track]; groups={}
        for item in originals:
            clone=copy.deepcopy(item); clone.id=uid(); clone.track=target
            key=item.group_id if item.link_id is None else item.link_id
            members=[i for i in originals if (i.group_id if i.link_id is None else i.link_id)==key] if key else []
            clone.link_id=groups.setdefault(key,uid()) if len(members)>1 else ""
            clone.group_id=clone.link_id or uid()
            self.timeline.append(clone)
        self.touch(); return target

    def delete_track(self, track: str) -> bool:
        if track=='subtitle_1':
            self.captions=[]; self.track_states.pop(track,None); self.track_names.pop(track,None); self.touch(); return True
        tracks = self.video_tracks if track in self.video_tracks else self.audio_tracks if track in self.audio_tracks else []
        if len(tracks) <= 1:return False
        tracks.remove(track); self.timeline=[i for i in self.timeline if i.track != track]
        self.track_states.pop(track,None); self.track_names.pop(track,None); self.touch(); return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path or self.path)
        if not str(target):
            raise ValueError("A project path is required")
        target.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(target)
        self.touch()
        pending = target.with_suffix(target.suffix + ".tmp")
        document = self.to_dict()
        if self.portable_media:
            import os
            def relative_sources(body):
                for item in body.get('timeline',body.get('items',[])):
                    for effect in item.get('effects',[]):
                        if effect.get('name')=='Object Tracking' and effect.get('image'):
                            try:effect['image']=os.path.relpath(effect['image'],target.parent)
                            except ValueError:pass
                    for node in item.get('graphic_data',{}).get('scene',{}).get('nodes',[]):
                        if node.get('kind')=='image' and node.get('source'):
                            try:node['source']=os.path.relpath(node['source'],target.parent)
                            except ValueError:pass
                for media in body.get("media", []):
                    if media.get("compound"):
                        relative_sources(media["compound"])
                        media["path"] = ""  # disposable compound render cache
                    if media.get("timeline_preset"):
                        relative_sources(media["timeline_preset"])
                    if not media.get("compound") and media.get("path"):
                        try:media["path"] = os.path.relpath(media["path"], target.parent)
                        except ValueError:pass  # a Save As on another Windows volume
                    if media.get("thumbnail"):
                        try:media["thumbnail"] = os.path.relpath(media["thumbnail"], target.parent)
                        except ValueError:pass
            relative_sources(document)
        pending.write_text(json.dumps(document, indent=2), encoding="utf-8")
        pending.replace(target)
        return target

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("portable_media"):
            base = Path(path).resolve().parent
            def absolute_sources(body):
                for item in body.get('timeline',body.get('items',[])):
                    for effect in item.get('effects',[]):
                        if effect.get('name')=='Object Tracking' and effect.get('image') and not Path(effect['image']).is_absolute():effect['image']=str((base/effect['image']).resolve())
                    for node in item.get('graphic_data',{}).get('scene',{}).get('nodes',[]):
                        if node.get('kind')=='image' and node.get('source') and not Path(node['source']).is_absolute():node['source']=str((base/node['source']).resolve())
                for media in body.get("media", []):
                    if media.get("compound"):
                        absolute_sources(media["compound"])
                    if media.get("timeline_preset"):
                        absolute_sources(media["timeline_preset"])
                    if not media.get("compound") and media.get("path") and not Path(media["path"]).is_absolute():
                        media["path"] = str((base / media["path"]).resolve())
                    if media.get("thumbnail") and not Path(media["thumbnail"]).is_absolute():
                        media["thumbnail"] = str((base / media["thumbnail"]).resolve())
            absolute_sources(raw)
        project = cls.from_dict(raw)
        project.path = str(path)
        return project

    @classmethod
    def from_dict(cls, raw: dict) -> "Project":
        raw = copy.deepcopy(raw)
        raw["settings"] = ProjectSettings(**_known(ProjectSettings, raw.get("settings", {})))
        raw["subtitle_style"] = CaptionStyle(**_known(CaptionStyle,raw.get("subtitle_style",{})))
        raw["media"] = [MediaItem(**_known(MediaItem, x)) for x in raw.get("media", [])]
        items = []
        for x in raw.get("timeline", []):
            x = _known(TimelineItem, x)
            x["crop"] = Crop(**_known(Crop, x.get("crop", {})))
            x["transform"] = Transform(**_known(Transform, x.get("transform", {})))
            items.append(TimelineItem(**x))
        raw["timeline"] = items
        captions = []
        for x in raw.get("captions", []):
            x = _known(Caption, x)
            x.setdefault("customize",True)
            x["style"] = CaptionStyle(**_known(CaptionStyle, x.get("style", {})))
            captions.append(Caption(**x))
        raw["captions"] = captions
        transitions = []
        for x in raw.get("transitions", []):
            try:
                transitions.append(Transition.from_dict(x))
            except Exception:
                pass
        raw["transitions"] = transitions
        project = cls(**_known(cls, raw))
        project.ensure_track_model()
        return project


def _known(dataclass_type: type, values: dict[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in fields(dataclass_type)}
    return {k: v for k, v in values.items() if k in allowed}


def _track_number(track: str) -> int:
    try:return int(track.rsplit("_",1)[1])
    except (IndexError,ValueError):return 9999


def make_vertical_group(media: MediaItem, start: float = 0.0,
                        in_point: float = 0.0, duration: float | None = None,
                        video_tracks: list[str] | None = None, audio_track: str = "audio_1") -> list[TimelineItem]:
    duration = duration or max(0.1, media.duration - in_point)
    video_tracks=video_tracks or default_video_tracks()
    while len(video_tracks)<3:video_tracks.append(f"video_{len(video_tracks)+1}")
    group = uid()
    base = dict(media_id=media.id, start=start, duration=duration,
                in_point=in_point, group_id=group)
    return [
        TimelineItem(uid(), track=video_tracks[0], crop=Crop(), role="background",
                     transform=Transform(0.5, 0.5, 1.0), **base),
        TimelineItem(uid(), track=video_tracks[1], crop=Crop(), role="content",
                     transform=Transform(0.5, 0.67, 1.0), **base),
        TimelineItem(uid(), track=video_tracks[2], role="facecam", is_webcam=True,
                     crop=Crop(0.0, 0.0, 1.0, 0.48),
                     transform=Transform(0.5, 0.18, 1.0, shape="rectangle"), **base),
    ] + ([TimelineItem(uid(), track=audio_track, role="source_audio", transform=Transform(), **base)] if media.has_audio else [])
