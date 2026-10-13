"""A timeline clock owns playback; decoder callbacks never seek or pause it."""
import time
import copy
import hashlib
from .process import run as run_process
from .audio_levels import channel_peaks
from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot, Qt, QMetaObject
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink, QAudioBufferOutput


class TimelineTransport(QObject):
    changed = Signal(float)
    stateChanged = Signal(bool)
    levelsChanged = Signal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window=window; self.playing=False; self.rate=1.; self.position=0.; self.loop=False
        self.monitor_gain=1.
        self._meter_tracks={}; self._meter_peaks={}; self._meter_last={}; self._meter_display={}; self._meter_clip=set(); self._meter_published_clips=set()
        self._meter_timer=QTimer(self); self._meter_timer.setInterval(50); self._meter_timer.timeout.connect(self.publish_levels)
        self.origin=0.; self.started=0.; self.decoders={}; self.closed=False
        self.audio_cache={}; self.audio_pending=set(); self.audio_failed=set()
        self.warm_keys=set(); self.previous_video={}; self.boundary_holds={}; self._project=None
        self._seek_holds={}; self._scrub_decoder_targets={}; self._video_seek_started={}
        self._required_video_keys=set(); self._protected_warm_video_keys=set()
        self._pending_video_seeks={}; self._video_seek_floor={}; self._loading_video_seeks={}
        self._frame_epochs={}; self._frame_jobs=[]; self._frame_executor=None
        self._frame_sequence=0; self._published_sequences={}; self._cpu_frame_fallback=set(); self._frame_epoch=0; self._frame_cursor=0
        self.scrubbing=False; self._last_scrub_sync=0.; self._scrub_pending_pos=None
        self._scrub_timer=QTimer(self); self._scrub_timer.setSingleShot(True); self._scrub_timer.timeout.connect(self._flush_scrub)
        self._scrub_retry_timer=QTimer(self); self._scrub_retry_timer.setSingleShot(True); self._scrub_retry_timer.timeout.connect(self._retry_scrub)
        self.timer=QTimer(self); self.timer.setInterval(20); self.timer.timeout.connect(self.tick)
        self.frame_timer=QTimer(self); self.frame_timer.setInterval(17); self.frame_timer.timeout.connect(self.poll_frames)
        self.result_timer=QTimer(self); self.result_timer.setInterval(4); self.result_timer.setTimerType(Qt.PreciseTimer)
        self.result_timer.timeout.connect(self.publish_frames)

    def set_monitor_gain(self,gain):
        self.monitor_gain=max(0.,min(1.,float(gain)))
        for _,output,_ in self.decoders.values():
            base=output.property('monitor_base_gain')
            if base is not None:output.setVolume(float(base)*self.monitor_gain)

    def seek(self, position):
        self._scrub_timer.stop(); self.scrubbing=False; self._scrub_pending_pos=None
        self._scrub_decoder_targets.clear(); self._scrub_retry_timer.stop()
        if self.playing and position>=self.window.project.duration:self.pause()
        self.position=max(0.,position); self.origin=self.position; self.started=time.monotonic()
        self.sync(True); self.changed.emit(self.position)

    def scrub(self, position):
        if self.playing:self.pause()
        self.scrubbing=True
        self.position=max(0.,position); self.origin=self.position; self.started=time.monotonic()
        now=time.monotonic()
        # A cut/gap cannot wait for the native-seek throttle: painting the new
        # playhead with the previous clip-ID map otherwise produces a black flash.
        p=self.window.project
        mapped=self.window.preview.active_frames
        changed_lanes=any((item is None or not item.start<=self.position<item.start+item.duration)
                          for item in (p.item_by_id(id) for id in mapped))
        if not mapped:
            changed_lanes=any(item.track in p.video_tracks and item.start<=self.position<item.start+item.duration
                              and not item.muted for item in p.timeline)
        if changed_lanes or now-self._last_scrub_sync>=0.025:
            self._scrub_timer.stop(); self._last_scrub_sync=now; self._scrub_pending_pos=None
            self.sync(True)
        else:
            self._scrub_pending_pos=self.position
            remaining=max(1,round((0.025-(now-self._last_scrub_sync))*1000))
            if not self._scrub_timer.isActive():
                self._scrub_timer.start(remaining)
        self.changed.emit(self.position)

    def _flush_scrub(self):
        if not self.scrubbing or self.closed:return
        self._last_scrub_sync=time.monotonic()
        self._scrub_pending_pos=None
        self.sync(True)

    def finish_scrub(self):
        self._scrub_timer.stop()
        self.scrubbing=False
        self._scrub_pending_pos=None
        self.seek(self.position)

    def _retry_scrub(self):
        if self.scrubbing and not self.closed and self._scrub_decoder_targets:self._flush_scrub()

    def play(self):
        if self.position>=self.window.project.duration:self.position=0.
        self.origin=self.position; self.started=time.monotonic(); self.playing=True
        # A paused decoder is already at the timeline position. Forcing another
        # seek here flushes its queued frames and decodes from a keyframe again.
        # sync still positions newly created/out-of-sync players; explicit seeks
        # retain their force flag, source trim gates and loading behavior.
        self.sync(); self.timer.start(); self._meter_timer.start(); self.stateChanged.emit(True)

    def pause(self):
        if self.playing:self.tick()
        self.playing=False; self.timer.stop(); self._meter_timer.stop()
        for player,_,_ in self.decoders.values():player.pause()
        self._meter_display={}; self.levelsChanged.emit(self._idle_levels())
        self.stateChanged.emit(False)

    def _idle_levels(self):
        return {track:(0.,0.,True) for track in self._meter_clip}

    def tick(self):
        self.position=self.origin+(time.monotonic()-self.started)*self.rate
        duration=self.window.project.duration
        if self.loop and self.playing and duration>0 and (self.position>=duration or self.position<0):
            self.position%=duration; self.origin=self.position; self.started=time.monotonic(); self.sync(True); self.changed.emit(self.position); return
        if self.position<0:
            self.position=0.; self.playing=False; self.timer.stop(); self._meter_timer.stop(); self._meter_display={}; self.levelsChanged.emit(self._idle_levels()); self.stateChanged.emit(False)
        if self.position>=self.window.project.duration:
            self.position=self.window.project.duration; self.playing=False; self.timer.stop(); self._meter_timer.stop(); self._meter_display={}; self.levelsChanged.emit(self._idle_levels())
            self.stateChanged.emit(False)
        self.sync(); self.changed.emit(self.position)

    def sync(self, force=False):
        if self.closed:return
        from .missing_media import unavailable
        p=self.window.project; t=self.position; active=set(); preview=self.window.preview
        sources={m.id:m.path for m in p.media}
        previous=getattr(self,'_media_source_paths',{})
        changed={id for id,path in sources.items() if id in previous and previous[id]!=path}
        for key in list(self.decoders):
            if key[0] in changed:self.retire_decoder(key)
        if changed:
            self.previous_video.clear(); self.boundary_holds.clear()
            for id in changed:
                self.window.proxies.pop(id,None)
                if hasattr(self.window,'preview_quality'):self.window.preview_quality.ready.pop(id,None)
        self._media_source_paths=sources
        caption_focus=getattr(preview,'caption_focus',False)
        is_different_project = (self._project is None or 
                                getattr(self._project, 'created_at', None) != getattr(p, 'created_at', None))
        if is_different_project:
            for key in list(self.decoders):self.retire_decoder(key)
            self._meter_peaks.clear(); self._meter_last.clear(); self._meter_display.clear(); self._meter_clip.clear(); self._meter_published_clips.clear()
            self.previous_video={}; self.boundary_holds={}; self._seek_holds.clear(); self._scrub_decoder_targets.clear(); self._project=p
        else:
            self._project=p
        old_video=self.previous_video; current_video={}; preview.active_frames={}; preview.fallback_frames={}
        now=time.monotonic(); controlled=set()
        # An inactive player can serve another source-time clock of the same
        # media without reopening the file. Protect every simultaneous active
        # clock and the already-warmed neighbours before choosing a candidate.
        self._required_video_keys=set(); self._protected_warm_video_keys=set()
        transition_items={item_id for trans in (() if caption_focus else p.transitions) if trans.contains_time(t)
                          for item_id in (trans.left_item_id,trans.right_item_id) if item_id}
        if not caption_focus:
            for item in p.timeline:
                if item.track not in p.video_tracks or item.muted:continue
                state=p.track_states.get(item.track,{})
                if not state.get('visible',True) or state.get('muted',False):continue
                media=p.media_by_id(item.media_id)
                if not media or media.kind!='video' or unavailable(media,item):continue
                key=(media.id,round(item.in_point-item.start*item.speed,4),item.speed,'video')
                if item.start<=t<item.start+item.duration or item.id in transition_items:
                    self._required_video_keys.add(key)
                elif key in self.warm_keys and (t<item.start<=t+.75 or t-.75<=item.start+item.duration<=t):
                    self._protected_warm_video_keys.add(key)
        for item in p.timeline:
            if caption_focus and item.track not in p.audio_tracks:continue
            if item.muted or not item.start<=t<item.start+item.duration:continue
            state=p.track_states.get(item.track,{})
            if not state.get("visible",True) or state.get("muted",False):continue
            media=p.media_by_id(item.media_id)
            if not media or media.kind=="image" or unavailable(media,item):continue
            if media.compound:
                from pathlib import Path
                if not Path(media.path).is_file():continue
            video=item.track in p.video_tracks
            if not video and not (media.has_audio or media.kind=="audio"):continue
            quality=getattr(self.window,'preview_quality',None)
            if video and quality and quality.needs_compatible(media):
                # Qt can play AV1 audio while yielding no video frames on some
                # Windows drivers. Show its FFmpeg thumbnail until the H.264
                # preview is prepared instead of opening a failing decoder.
                if media.thumbnail:
                    image=preview.still_cache.load(media.thumbnail)
                    if not image.isNull():preview.fallback_frames[item.id]=image
                continue
            # Layout duplicates share one video decoder, not three.
            audio_path=self.processed_audio(item,media) if not video else ""
            key=(media.id,round(item.in_point-item.start*item.speed,4),item.speed,"video" if video else "audio:"+item.track+audio_path)
            active.add(key); desired=round(((t-item.start) if audio_path else item.source_time(t))*1000)
            created=key not in self.decoders; reused=False
            if created:
                if not video:self._meter_tracks[key]=item.track
                reused=bool(self.create_decoder(key,media,video,audio_path))
            player,output,_=self.decoders[key]
            # A native seek can legitimately take longer than the drift threshold.
            # Re-seeking it on every clock tick prevents long-GOP decoding from
            # ever catching up. Explicit user seeks still supersede immediately.
            position_needed=force or created or (key not in self._pending_video_seeks and abs(player.position()-desired)>350)
            if video:
                preview.active_frames[item.id]=key; output.setVolume(0.)
                previous=old_video.get(item.track)
                image=preview.frames.get(key)
                adjacent=previous and ((abs(previous['end']-item.start)<1e-6 and abs(t-item.start)<.5) or (abs(previous['start']-item.start-item.duration)<1e-6 and abs(t-item.start-item.duration)<.5))
                if image is None and previous and previous['id']!=item.id and adjacent:
                    held=previous.get('image')
                    if held is not None:self.boundary_holds[key]=(held,now+.5)
                hold=self.boundary_holds.get(key)
                if image is None and hold and now<hold[1]:preview.fallback_frames[item.id]=hold[0]
                else:self.boundary_holds.pop(key,None)
                # A valid seek can change the source-time key before its first
                # frame is ready. Keep only the preceding lane image while that
                # incoming decoder is pending; gaps/hidden/offline lanes never
                # enter this branch and their holds are retired below.
                hold_key=(key,item.track)
                if image is None and previous and previous.get('key')!=key and position_needed:
                    held=previous.get('image')
                    if held is not None:self._seek_holds.setdefault(hold_key,(held,now+2.))
                seek_hold=self._seek_holds.get(hold_key)
                if seek_hold and now>=seek_hold[1]:
                    self._seek_holds.pop(hold_key,None); seek_hold=None
                if self.scrubbing and force and image is None and seek_hold is not None:
                    seek_hold=(seek_hold[0],now+2.); self._seek_holds[hold_key]=seek_hold
                if image is None and seek_hold is not None and (position_needed or key in self._pending_video_seeks):
                    preview.fallback_frames[item.id]=seek_hold[0]
                current_video[item.track]=dict(id=item.id,start=item.start,end=item.start+item.duration,key=key,
                                              image=image if image is not None else preview.fallback_frames.get(item.id))
            else:
                elapsed=t-item.start; fade=min(1.,elapsed/item.fade_in) if item.fade_in else 1.
                if item.fade_out:fade*=min(1.,max(0.,item.duration-elapsed)/item.fade_out)
                duck=10**(p.settings.duck_amount_db/20) if item.role=="music" and p.settings.auto_duck and any(i.role=="source_audio" and not i.muted and i.start<=t<i.start+i.duration for i in p.timeline) else 1.
                output.setProperty('monitor_base_gain',0. if self.scrubbing else min(1.,10**(item.gain_db/20))*fade*duck)
                output.setVolume(output.property('monitor_base_gain')*self.monitor_gain)
            # Aligned layout copies share a decoder. Native controls must share
            # it too: three layers must not flush the same seek three times.
            if key in controlled:continue
            controlled.add(key)
            player.setPlaybackRate(self.rate*(1 if audio_path else item.speed))
            if position_needed:self._position_requested(key,desired)
            if self.playing and key not in self._loading_video_seeks and player.playbackState()!=QMediaPlayer.PlayingState:player.play()
            elif created and video and not reused and key not in self._loading_video_seeks:
                # A new paused decoder otherwise never produces its first frame.
                # Prime only muted video; frame() pauses it without starting the clock.
                player.play()
            elif not self.playing and key not in self._pending_video_seeks and player.playbackState()==QMediaPlayer.PlayingState:player.pause()
        # Keep decoders primed for clips in active transitions
        for trans in (() if caption_focus else getattr(p, "transitions", [])):
            if trans.contains_time(t):
                for item_id, is_outgoing in ((trans.left_item_id, True), (trans.right_item_id, False)):
                    item = p.item_by_id(item_id)
                    if not item or item.muted or item.id in preview.active_frames:
                        continue
                    state = p.track_states.get(item.track, {})
                    if not state.get("visible", True) or state.get("muted", False):
                        continue
                    media = p.media_by_id(item.media_id)
                    if not media or media.kind == "image" or unavailable(media,item):
                        continue
                    if media.compound:
                        from pathlib import Path
                        if not Path(media.path).is_file():
                            continue
                    video = item.track in p.video_tracks
                    if not video:
                        continue
                    quality=getattr(self.window,'preview_quality',None)
                    if quality and quality.needs_compatible(media):continue
                    key = (media.id, round(item.in_point - item.start * item.speed, 4), item.speed, "video")
                    active.add(key)
                    if is_outgoing:
                        desired_t = min(item.start + item.duration - 0.001, max(item.start, t))
                    else:
                        desired_t = max(item.start, min(item.start + item.duration - 0.001, t))
                    desired = round(item.source_time(desired_t) * 1000)
                    created = key not in self.decoders
                    if created:
                        self.create_decoder(key, media, video, "")
                    player, output, _ = self.decoders[key]
                    preview.active_frames[item.id] = key
                    output.setVolume(0.)
                    if key in controlled:continue
                    controlled.add(key)
                    if force or created or abs(player.position() - desired) > 350:
                        self._position_requested(key, desired)
                    if created and key not in self._loading_video_seeks:
                        player.play()
                    elif not self.playing and key not in self._pending_video_seeks and player.playbackState() == QMediaPlayer.PlayingState:
                        player.pause()
        self.previous_video=current_video
        # Prepare both sides of nearby cuts, including backwards scrubbing.
        # Keep at most one neighbour per direction/lane and eight extra decoders.
        warm=set()
        if not self.scrubbing:
            lanes=set(); candidates=[]
            for item in p.timeline:
                if caption_focus and item.track not in p.audio_tracks:continue
                if t<item.start<=t+.75:candidates.append((item.start-t,1,item,item.in_point))
                elif t-.75<=item.start+item.duration<=t:candidates.append((t-item.start-item.duration,-1,item,item.source_time(item.start+item.duration)-item.speed/max(1,p.settings.fps)))
            for _,direction,item,source in sorted(candidates,key=lambda value:value[0]):
                lane=(item.track,direction)
                if lane in lanes:continue
                state=p.track_states.get(item.track,{})
                if item.muted or not state.get('visible',True) or state.get('muted',False):continue
                media=p.media_by_id(item.media_id)
                video=item.track in p.video_tracks
                if not media or unavailable(media,item) or (media.kind!='video' if video else not (media.has_audio or media.kind=='audio')):continue
                quality=getattr(self.window,'preview_quality',None)
                if video and quality and quality.needs_compatible(media):continue
                if media.compound:
                    from pathlib import Path
                    if not Path(media.path).is_file():continue
                audio_path=self.processed_audio(item,media) if not video else ''
                lanes.add(lane); key=(media.id,round(item.in_point-item.start*item.speed,4),item.speed,'video' if video else 'audio:'+item.track+audio_path)
                if key in active or key in warm:continue
                if len(warm)>=8:break
                warm.add(key)
                created=key not in self.decoders
                if created:
                    if not video:self._meter_tracks[key]=item.track
                    self.create_decoder(key,media,video,audio_path)
                if created or key not in self.warm_keys:
                    player,output,_=self.decoders[key]
                    output.setVolume(0.)
                    desired=(0 if direction>0 else max(0,item.duration-1/max(1,p.settings.fps))) if audio_path else max(item.in_point,source)
                    self.position_decoder(key,round(desired*1000))
                    if video and key not in self._loading_video_seeks:player.play()
                    elif not video:player.pause()
        self.warm_keys=warm
        self._seek_holds={hold_key:value for hold_key,value in self._seek_holds.items()
                          if hold_key[1] in current_video and current_video[hold_key[1]]['key']==hold_key[0]}
        for key in list(self.decoders):
            if key not in active|warm:self.retire_decoder(key)
        if any(sink for _,_,sink in self.decoders.values()):
            interval=max(8,round(1000/max(1,p.settings.fps)))
            # setInterval restarts an active QTimer, even when unchanged. The
            # timeline clock must not continually postpone the frame sampler.
            if self.frame_timer.interval()!=interval:self.frame_timer.setInterval(interval)
            if not self.frame_timer.isActive():self.frame_timer.start()
        else:self.frame_timer.stop()
        self.window.preview.update()

    def create_decoder(self,key,media,video,audio_path):
        if video and not self.playing and self._reuse_video_decoder(key):return True
        player=QMediaPlayer(self); output=QAudioOutput(player); player.setAudioOutput(output)
        if not video:
            buffer_output=QAudioBufferOutput(player)
            player.setAudioBufferOutput(buffer_output)
            buffer_output.audioBufferReceived.connect(lambda buffer,k=key:self.receive_audio_buffer(k,buffer),Qt.QueuedConnection)
        sink=QVideoSink(player) if video else None
        if sink:player.setVideoSink(sink); sink._frame_stamp=None
        self.decoders[key]=(player,output,sink)
        player._transport_key=key
        player.mediaStatusChanged.connect(lambda status,p=player:self.decoder_loaded(p._transport_key,p,status))
        from .media_source import set_media_source
        set_media_source(player,QUrl.fromLocalFile(self.window.proxies.get(media.id,media.path) if video else audio_path or media.path))

    def _reuse_video_decoder(self,key):
        for previous,decoder in tuple(self.decoders.items()):
            if (len(previous)<4 or previous[3]!='video' or previous[0]!=key[0] or previous[2]!=key[2]
                    or previous in self._required_video_keys or previous in self._protected_warm_video_keys):continue
            player,_,sink=decoder
            if sink is None:continue
            self.decoders.pop(previous); self.decoders[key]=decoder; player._transport_key=key
            sink._frame_stamp=None
            self._frame_epochs.pop(previous,None); self._published_sequences.pop(previous,None)
            self._cpu_frame_fallback.discard(previous); self._pending_video_seeks.pop(previous,None)
            self._video_seek_floor.pop(previous,None); self._video_seek_started.pop(previous,None); self._loading_video_seeks.pop(previous,None)
            self._scrub_decoder_targets.pop(previous,None); self.warm_keys.discard(previous)
            self.boundary_holds.pop(previous,None)
            self._seek_holds={hold_key:value for hold_key,value in self._seek_holds.items() if hold_key[0]!=previous}
            self.window.preview.frames.pop(previous,None)
            if not self._scrub_decoder_targets:self._scrub_retry_timer.stop()
            return True
        return False

    def receive_audio_buffer(self,key,buffer):
        if not self.playing or key not in self.decoders or key not in self._meter_tracks:return
        left,right=channel_peaks(buffer)
        base=self.decoders[key][1].property('monitor_base_gain')
        gain=float(base) if base is not None else 0.
        self._meter_peaks[key]=(left*gain,right*gain)
        self._meter_last[key]=time.monotonic()

    def publish_levels(self):
        if not self.playing:return
        now=time.monotonic(); levels={}
        for key,track in self._meter_tracks.items():
            if key not in self.decoders or now-self._meter_last.get(key,-100)>.20:continue
            left,right=self._meter_peaks.get(key,(0.,0.))
            prev=levels.get(track,(0.,0.))
            levels[track]=(max(prev[0],left),max(prev[1],right))
        for track in set(levels)|set(self._meter_display):
            old=self._meter_display.get(track,(0.,0.)); peak=levels.get(track,(0.,0.))
            levels[track]=(max(peak[0],old[0]*.72),max(peak[1],old[1]*.72))
            if max(peak)>=.999:self._meter_clip.add(track)
        changed=levels!=self._meter_display or self._meter_clip!=self._meter_published_clips
        self._meter_display=levels
        if changed:
            self._meter_published_clips=set(self._meter_clip)
            self.levelsChanged.emit({track:(*value,track in self._meter_clip) for track,value in levels.items()})

    def reset_meter_clips(self):
        self._meter_clip.clear()
        self._meter_published_clips.clear()
        self.levelsChanged.emit({track:(*value,False) for track,value in self._meter_display.items()})

    def position_decoder(self,key,milliseconds):
        player,_,sink=self.decoders[key]
        if sink:
            self._frame_epoch+=1; self._frame_epochs[key]=self._frame_epoch
            sink._frame_stamp=None
            # setPosition during LoadingMedia may be ignored by Qt. Do not
            # publish (or pause on) the source's initial frame while it loads.
            self._pending_video_seeks[key]=milliseconds
            if player.mediaStatus()==QMediaPlayer.LoadingMedia or key in self._loading_video_seeks:
                self._loading_video_seeks[key]=milliseconds
            self._video_seek_floor[key]=milliseconds*1000
            self._video_seek_started[key]=time.monotonic()
        player.setPosition(milliseconds)

    def _position_requested(self,key,milliseconds):
        # While dragging, let one requested frame finish instead of continually
        # resetting its seek gate. Only the latest cursor target is retained.
        # Explicit seek/release uses position_decoder directly through this
        # helper with scrubbing=False, so older frames remain rejected there.
        if self.scrubbing and self.decoders[key][2] is not None:
            pending=self._pending_video_seeks.get(key)
            if pending is not None:
                if milliseconds!=pending:
                    remaining=2.-(time.monotonic()-self._video_seek_started.get(key,time.monotonic()))
                    if remaining>0:
                        self._scrub_decoder_targets[key]=milliseconds
                        delay=max(1,round(remaining*1000))
                        if not self._scrub_retry_timer.isActive() or delay<self._scrub_retry_timer.remainingTime():
                            self._scrub_retry_timer.start(delay)
                        return
                else:
                    self._scrub_decoder_targets.pop(key,None)
                    if not self._scrub_decoder_targets:self._scrub_retry_timer.stop()
                    return
        self._scrub_decoder_targets.pop(key,None)
        if not self._scrub_decoder_targets:self._scrub_retry_timer.stop()
        self.position_decoder(key,milliseconds)

    def _seek_frame_ready(self,key):
        self._pending_video_seeks.pop(key,None); self._loading_video_seeks.pop(key,None)
        self._video_seek_started.pop(key,None)
        if self.scrubbing and key in self._scrub_decoder_targets:
            # Dispatch after the current publication callback returns. Never
            # recurse into sync/decoder teardown from frame completion.
            self._scrub_timer.start(0)

    def decoder_loaded(self,key,player,status):
        if self.closed or status!=QMediaPlayer.LoadedMedia:return
        decoder=self.decoders.get(key)
        if not decoder or decoder[0] is not player:return
        if decoder[2] is None:
            player.setActiveVideoTrack(-1); return
        # LoadedMedia is also emitted during ordinary seeks. Replay only a
        # request that actually waited for source loading, once; replaying every
        # buffered seek flushes it again and starts paused players unnecessarily.
        target=self._loading_video_seeks.pop(key,None)
        if target is not None:
            player.setPosition(target)
            player.play()  # Muted priming; pause only after the sought frame.

    @Slot()
    def poll_frames(self):
        # Read only the latest frame per decoder on the GUI thread. Per-frame
        # Python callbacks can deadlock decoder teardown; queued QVideoFrames
        # also accumulate native buffers when multiple 60 fps lanes outpace the
        # compositor. This bounded sampler has neither cross-thread Python calls
        # nor an unbounded frame-delivery queue.
        if self.closed:return
        self.publish_frames()
        decoders=list(self.decoders.items())
        if decoders:
            offset=self._frame_cursor%len(decoders)
            decoders=decoders[offset:]+decoders[:offset]; self._frame_cursor+=1
        for key,(player,_,sink) in decoders:
            if not sink:continue
            frame=sink.videoFrame()
            if not frame.isValid():continue
            stamp=(frame.startTime(),frame.endTime())
            if stamp==sink._frame_stamp:continue
            floor=self._video_seek_floor.get(key)
            if floor is not None and (self.rate>=0 or key in self._pending_video_seeks):
                # End-time comparison admits a frame containing the requested
                # sub-frame timestamp, but never trimmed-out startup frames.
                if stamp[0]<0 or stamp[1]<floor-2000:continue
                ceiling=floor
                if self.playing and key not in self.warm_keys:
                    ceiling=max(floor,round((self.position*key[2]+key[1])*1_000_000))
                if key in self._pending_video_seeks and stamp[0]>ceiling+350000:continue
            # Backpressure precedes readback: no unbounded queue or wasted GPU
            # downloads while pixel processing is still busy. Native frames
            # remain entirely on their owning thread (including conversion).
            if len(self._frame_jobs)>=2:continue
            # Stop muted priming as soon as its valid frame arrives, before
            # readback/filter work. Otherwise a paused/warm player runs ahead
            # while pixels are prepared and must seek again when resumed.
            if (not self.playing or key in self.warm_keys) and player.playbackState()==QMediaPlayer.PlayingState:
                player.pause()
            image=frame.toImage().copy()
            if image.isNull():continue
            self._frame_sequence+=1; sequence=self._frame_sequence
            prepare=getattr(self.window.preview,'frame_work',None)
            work=prepare(key,image) if prepare and key not in self._cpu_frame_fallback else None
            if work:
                from .preview_raster import prepare_frame
                if self._frame_executor is None:
                    from concurrent.futures import ThreadPoolExecutor
                    self._frame_executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='preview-pixels')
                future=self._frame_executor.submit(prepare_frame,image,*work)
                future._kinetic_interactive=bool(getattr(work[0],'interactive',self.playing or self.scrubbing))
                self._frame_jobs.append((key,self._frame_epochs.get(key,0),sequence,future))
                sink._frame_stamp=stamp
                if not self.result_timer.isActive():self.result_timer.start()
                continue
            self._seek_frame_ready(key)
            self._published_sequences[key]=sequence
            sink._frame_stamp=stamp; self.frame(key,image)

    @Slot()
    def publish_frames(self):
        if self.closed:return
        remaining=[]
        for key,epoch,sequence,future in self._frame_jobs:
            if not future.done():remaining.append((key,epoch,sequence,future)); continue
            if key not in self.decoders or epoch!=self._frame_epochs.get(key,0):continue
            if sequence<=self._published_sequences.get(key,-1):continue
            if getattr(future,'_kinetic_interactive',bool(self.playing or self.scrubbing))!=bool(self.playing or self.scrubbing):
                self.decoders[key][2]._frame_stamp=None
                continue
            try:image,cache=future.result()
            except Exception:
                self._cpu_frame_fallback.add(key); self.decoders[key][2]._frame_stamp=None
                continue
            self._published_sequences[key]=sequence; self._seek_frame_ready(key)
            self.window.preview.effect_cache.update(cache)
            while len(self.window.preview.effect_cache)>16:
                self.window.preview.effect_cache.pop(next(iter(self.window.preview.effect_cache)))
            self.frame(key,image)
        self._frame_jobs=remaining
        if not remaining:self.result_timer.stop()

    def retire_decoder(self,key):
        self._meter_tracks.pop(key,None); self._meter_peaks.pop(key,None); self._meter_last.pop(key,None)
        self._frame_epochs.pop(key,None)
        self._published_sequences.pop(key,None); self._cpu_frame_fallback.discard(key)
        self._pending_video_seeks.pop(key,None); self._video_seek_floor.pop(key,None); self._loading_video_seeks.pop(key,None)
        self._video_seek_started.pop(key,None)
        self._scrub_decoder_targets.pop(key,None)
        if not self._scrub_decoder_targets:self._scrub_retry_timer.stop()
        self._seek_holds={hold_key:value for hold_key,value in self._seek_holds.items() if hold_key[0]!=key}
        decoder=self.decoders.pop(key,None)
        self.window.preview.frames.pop(key,None)
        if not decoder:return
        player,output,sink=decoder
        # Unpublish before stopping: backend notifications may arrive in cleanup.
        output.setMuted(True)
        # Invoke the C++ slots from Qt's event loop, outside the Python edit
        # callback/GIL. stop() joins decoder threads; doing that inside a Python
        # callback can stall other players' frame notifications indefinitely.
        # Output and sink are player-owned, so they outlive that queued stop.
        QMetaObject.invokeMethod(player,"stop",Qt.QueuedConnection)
        QMetaObject.invokeMethod(player,"deleteLater",Qt.QueuedConnection)

    def processed_audio(self,item,media):
        from .voice_effects import PROCESSED_NAMES
        effects=[e for e in item.effects if e.get("enabled",True) and e.get("name") in PROCESSED_NAMES]
        if item.pan==0 and item.pitch_semitones==0 and item.pitch_cents==0 and item.gain_db<=0 and item.speed==1 and not effects:return ""
        from .config import CACHE_DIR
        from .ui import Worker
        from .waveforms import source_key
        source=media.path; ffmpeg=self.window.settings.get('ffmpeg','ffmpeg')
        if not hasattr(self,'_audio_source_signatures'):self._audio_source_signatures={}
        cached=self._audio_source_signatures.get(media.id)
        if not cached or cached[:2]!=(id(media),source):
            cached=(id(media),source,source_key(source)); self._audio_source_signatures[media.id]=cached
        signature=repr((cached[2],item.in_point,item.duration,item.speed,item.pan,item.pitch_semitones,item.pitch_cents,max(0,item.gain_db),effects))
        key=hashlib.sha1(signature.encode()).hexdigest(); target=CACHE_DIR/("audio-preview-"+key+".wav")
        if target.exists():return str(target)
        if key in self.audio_pending or key in self.audio_failed or len(self.audio_pending)>=2:return ""
        self.audio_pending.add(key); snapshot=copy.deepcopy(item); snapshot.gain_db=max(0,item.gain_db); snapshot.fade_in=snapshot.fade_out=0
        def prepare():
            from .rendergraph import audio_filters
            pending=target.with_suffix(".pending.wav")
            run_process([ffmpeg,"-hide_banner","-loglevel","error","-y","-ss",str(snapshot.in_point),"-t",str(snapshot.source_duration),"-i",source,"-vn","-af",audio_filters(snapshot),"-c:a","pcm_s16le",str(pending)],check=True,capture_output=True)
            pending.replace(target); return key
        def failed(detail):
            self.audio_pending.discard(key); self.audio_failed.add(key)
            self.window.statusBar().showMessage("Audio effect preview could not be prepared; export still applies the effect. Check FFmpeg settings.",7000)
        worker=Worker(prepare); worker.signals.result.connect(lambda _:self.audio_ready(key)); worker.signals.error.connect(failed); self.window.start_worker(worker)
        return ""

    def audio_ready(self,key):
        self.audio_pending.discard(key)
        # Only the newly prepared audio decoder needs positioning. Seeking every
        # active player here interrupts otherwise continuous video/audio cuts.
        if not self.closed:self.sync()

    def frame(self,key,image):
        if key not in self.decoders or image.isNull():return
        self.window.preview.frames[key]=image
        if key not in self.warm_keys:
            self.window.preview.set_frame(image); self.boundary_holds.pop(key,None)
            self._seek_holds={hold_key:value for hold_key,value in self._seek_holds.items() if hold_key[0]!=key}
            for item_id,active_key in self.window.preview.active_frames.items():
                if active_key==key:self.window.preview.fallback_frames.pop(item_id,None)
            for value in self.previous_video.values():
                if value['key']==key:value['image']=image
        if (not self.playing or key in self.warm_keys) and key in self.decoders:self.decoders[key][0].pause()

    def shutdown(self):
        self._scrub_timer.stop()
        self._scrub_retry_timer.stop()
        self._meter_timer.stop()
        self.result_timer.stop()
        for *_,future in self._frame_jobs:future.cancel()
        self._frame_jobs.clear()
        if self._frame_executor:
            self._frame_executor.shutdown(wait=False,cancel_futures=True); self._frame_executor=None
        self.closed=True; self.timer.stop(); self.frame_timer.stop(); self.playing=False
        self._scrub_decoder_targets.clear(); self._seek_holds.clear()
        self.warm_keys.clear(); self.previous_video.clear(); self.boundary_holds.clear(); self.window.preview.fallback_frames={}
        for key in list(self.decoders):self.retire_decoder(key)
