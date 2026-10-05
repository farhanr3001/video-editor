import copy, math


def audio_filters(item):
    chain="aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS"
    tempo=item.speed
    if abs(tempo-1)>.00001:
        while tempo<.5:chain+=",atempo=0.5"; tempo/=.5
        while tempo>2:chain+=",atempo=2"; tempo/=2
        chain+=f",atempo={tempo:.6f}"
    factor=2**((item.pitch_semitones+item.pitch_cents/100)/12)
    if abs(factor-1)>.00001:
        chain+=f",asetrate={48000*factor:.4f},aresample=48000"
        tempo=1/factor
        while tempo<.5:chain+=",atempo=0.5"; tempo/=.5
        while tempo>2:chain+=",atempo=2"; tempo/=2
        chain+=f",atempo={tempo:.6f}"
    left=min(1.,1-item.pan); right=min(1.,1+item.pan)
    chain+=f",pan=stereo|c0={left:.6f}*c0|c1={right:.6f}*c1,volume={item.gain_db:.4f}dB"
    for effect in item.effects:
        if not effect.get("enabled",True):continue
        amount=max(0,min(100,float(effect.get("amount",50))))/100
        if effect.get("name")=="Noise Clean":chain+=",afftdn=nf=-25"
        elif effect.get("name")=="Voice Clarity" and amount>0:chain+=f",highpass=f=80,equalizer=f=3000:t=q:w=1:g={amount*6:.3f}"
        elif effect.get("name")=="Low Cut" and amount>0:chain+=f",highpass=f={60+180*amount:.2f}"
    if item.fade_in>0:chain+=f",afade=t=in:st=0:d={min(item.fade_in,item.duration):.6f}"
    if item.fade_out>0:chain+=f",afade=t=out:st={max(0,item.duration-item.fade_out):.6f}:d={min(item.fade_out,item.duration):.6f}"
    return chain


def command(project,output,preset,burn_captions=True,hardware="Auto",ffmpeg="ffmpeg",ass_path=None,export_audio=True,prepared=None,window=None,transparent=False):
    from .exporter import _crop_filter,_target_size,_flip_filter,_encoder,_escape_ass_path
    project.ensure_track_model(); width=project.settings.width; height=project.settings.height; fps=project.settings.fps; duration=project.duration
    origin=0.
    if window:
        if export_audio or ass_path:raise ValueError('Windowed passes are video-only; audio and captions use the final continuous pass.')
        origin,stop=window; duration=stop-origin
    if duration<=0:raise ValueError("The timeline is empty.")
    args=[ffmpeg,"-hide_banner","-y"]; filters=[]; index=0
    filters.append(f"color=c={'black@0' if transparent else 'black'}:s={width}x{height}:r={fps}:d={duration:.6f},format=rgba[base]")
    current="base"; order={t:n for n,t in enumerate(project.video_tracks)}
    videos=sorted((i for i in project.timeline if i.track in order and not i.muted and project.track_states.get(i.track,{}).get("visible",True)),key=lambda i:(order[i.track],i.start))
    # Cropped webcam/gameplay/background copies often use precisely the same
    # source interval. Decode once and split decoded frames into their transforms.
    from collections import Counter
    def input_key(item):
        media=project.media_by_id(item.media_id)
        if not media or media.kind!='video' or (prepared or {}).get(item.id):return None
        if window and (item.start>=stop or item.start+item.duration<=origin):return None
        elapsed=max(0.,origin-item.start) if window else 0.
        length=(min(item.start+item.duration,stop)-max(item.start,origin))*item.speed if window else item.source_duration
        return (media.path,f'{item.in_point+elapsed*item.speed:.6f}',f'{length:.6f}')
    source_counts=Counter(input_key(i) for i in videos); shared_sources={}
    for n,item in enumerate(videos):
        if window and (item.start>=stop or item.start+item.duration<=origin):continue
        elapsed=max(0.,origin-item.start) if window else 0.
        source_duration=(min(item.start+item.duration,stop)-max(item.start,origin))*item.speed if window else item.source_duration
        media=project.media_by_id(item.media_id)
        if not media or media.kind not in {"video","image"}:continue
        from .visual_fx import visual_fx_synthetic_keyframes, VISUAL_FX_SET
        has_vfx=any((e.get("category")=="Visual FX" or e.get("name") in VISUAL_FX_SET) and e.get("enabled",True) for e in item.effects)
        vfx_item=item
        if has_vfx:
            synth=visual_fx_synthetic_keyframes(item)
            if synth:
                vfx_item=copy.copy(item)
                vfx_item.keyframes={**synth,**(item.keyframes or {})}
        animated=bool(vfx_item.keyframes)
        from .keyframes import expression
        def curve(name,clock='t'):return expression(vfx_item,name,clock)
        def rotation_filter(base_w,base_h):
            from .keyframes import base
            def largest(name):
                from .keyframes import maximum
                return maximum(vfx_item,name)
            side=math.ceil(math.hypot(min(8192,max(32,base_w*largest('scale'))),min(8192,max(32,base_h*largest('scale_y'))))/2)*2
            return f",rotate='({curve('rotation')})*PI/180':ow={side}:oh={side}:c=none"
        def stable_canvas(base_w,base_h):
            from .keyframes import base
            def maximum(name,dimension):
                from .keyframes import maximum as curve_maximum
                return math.ceil(min(8192,max(32,dimension*curve_maximum(vfx_item,name)))/2)*2+2
            return f",pad={maximum('scale',base_w)}:{maximum('scale_y',base_h)}:(ow-iw)/2:(oh-ih)/2:color=black@0:eval=frame"
        from .vision_effects import active as vision_active
        processed=(prepared or {}).get(item.id)
        if vision_active(item) and not processed:raise ValueError('Face/background effects must be prepared before building the render command.')
        from .chroma import NAMES
        opaque=(media.kind=='video' and item.composite_mode=='Normal' and item.opacity==100 and item.fade_in==0 and item.fade_out==0 and item.crop_softness==0 and item.transform.shape!='circle' and abs(item.transform.rotation)<.01 and abs(item.transform.pitch)<.01 and abs(item.transform.yaw)<.01 and not any(e.get('enabled',True) and e.get('name') in NAMES for e in item.effects))
        opaque=opaque and not processed and not animated and not media.has_alpha and not media.compound
        pixel_format='yuv420p' if opaque else 'rgba'
        shared=input_key(item)
        if shared is not None and shared in shared_sources:
            source=shared_sources[shared].pop(0)
        else:
            if processed:args += ['-ss',f'{elapsed*item.speed:.6f}','-t',f'{source_duration:.6f}','-threads','2','-i',processed]
            elif media.kind=="image":args += ["-framerate",str(fps),"-loop","1","-t",f"{source_duration+1.0:.6f}","-threads","2","-i",media.path]
            else:args += ["-ss",f"{item.in_point+elapsed*item.speed:.6f}","-t",f"{source_duration:.6f}","-threads","2","-i",media.path]
            source=f'{index}:v'; index+=1
            if shared is not None and source_counts[shared]>1:
                names=[f'shared{n}_{k}' for k in range(source_counts[shared])]
                filters.append(f'[{source}]split={len(names)}'+''.join(f'[{name}]' for name in names))
                source=names.pop(0); shared_sources[shared]=names
        if item.role=="background":
            chain=f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma={max(.01,project.settings.blur):.3f},eq=brightness={project.settings.background_brightness-1:.3f}:contrast={project.settings.background_contrast:.3f},format=rgba"
            if animated:
                chain=f'setpts=(PTS-STARTPTS)/{item.speed:.8f}+{elapsed:.8f}/TB,'+chain
                chain+=f",scale=w='max(32,min(8192,round({width}*({curve('scale')})/2)*2))':h='max(32,min(8192,round({height}*({curve('scale_y')})/2)*2))':eval=frame"
                chain+=stable_canvas(width,height)
                if 'rotation' in vfx_item.keyframes or abs(item.transform.rotation)>.01:chain+=rotation_filter(width,height)
            ox=width/2; oy=height/2
        else:
            lw,lh=_target_size(item,media,width,.92 if item.role=="facecam" else 1.,height)
            # Clamp per-layer intermediate dimensions to avoid pathological memory use.
            lw=min(8192,lw); lh=min(8192,lh)
            chain=f"{'null' if processed else _crop_filter(item)},scale={lw}:{lh}{_flip_filter(item)},format={pixel_format}"
            if animated:
                crop=item.crop.clamped(); factor=max(width/max(1,media.width),height/max(1,media.height))*(.92 if item.role=='facecam' else 1.)
                sx=f'max(32,min(8192,round({media.width*crop.width*factor:.10g}*({curve("scale")})/2)*2))'
                sy=f'max(32,min(8192,round({media.height*crop.height*factor:.10g}*({curve("scale_y")})/2)*2))'
                chain=f'setpts=(PTS-STARTPTS)/{item.speed:.8f}+{elapsed:.8f}/TB,'+('null' if processed else _crop_filter(item))+f",scale=w='{sx}':h='{sy}':eval=frame{_flip_filter(item)},format=rgba"
                chain+=stable_canvas(media.width*crop.width*factor,media.height*crop.height*factor)
            if animated:
                aw=f'{media.width*crop.width*factor:.10g}*({curve("scale","T")})'; ah=f'{media.height*crop.height*factor:.10g}*({curve("scale_y","T")})'
            else:aw='W'; ah='H'
            if item.transform.shape=="circle":chain+=f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow((X-W/2)/(({aw})/2),2)+pow((Y-H/2)/(({ah})/2),2),1),alpha(X,Y),0)'"
            if item.crop_softness>0:
                feather=max(1,item.crop_softness); chain+=f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*max(0,min(1,min(({aw})/2-abs(X-W/2),({ah})/2-abs(Y-H/2))/{feather:.3f}))'"
            if abs(item.transform.pitch)>.01 or abs(item.transform.yaw)>.01:
                px=abs(math.sin(math.radians(item.transform.pitch)))*lh*.3; py=abs(math.sin(math.radians(item.transform.yaw)))*lw*.3
                chain+=f",perspective=x0={py:.3f}:y0={px:.3f}:x1=W-{py:.3f}:y1=0:x2=0:y2=H:x3=W:y3=H-{px:.3f}:sense=destination"
            if animated and ('rotation' in vfx_item.keyframes or abs(item.transform.rotation)>.01):
                chain+=rotation_filter(media.width*crop.width*factor,media.height*crop.height*factor)
            elif abs(item.transform.rotation)>.01:chain+=f",rotate={math.radians(item.transform.rotation):.8f}:ow=rotw(iw):oh=roth(ih):c=none"
            ox=item.transform.x*width-item.transform.anchor_x*(item.transform.scale-1); oy=item.transform.y*height-item.transform.anchor_y*(item.transform.effective_scale_y-1)
            if abs(item.transform.rotation)>.01 and (item.transform.anchor_x or item.transform.anchor_y):
                # FFmpeg rotates the expanded layer about its centre. Shift that
                # centre so it lands where a true off-centre pivot does in the viewer.
                radians=math.radians(item.transform.rotation); ax=item.transform.anchor_x; ay=item.transform.anchor_y
                rotated_x=math.cos(radians)*ax-math.sin(radians)*ay
                rotated_y=math.sin(radians)*ax+math.cos(radians)*ay
                ox+=ax-rotated_x; oy+=ay-rotated_y
            if item.retain_image_position:
                crop=item.crop.clamped(); ox+=(crop.x+crop.width/2-.5)*lw/crop.width; oy+=(crop.y+crop.height/2-.5)*lh/crop.height
        from .chroma import NAMES,filter_string
        keys=[filter_string(effect) for effect in item.effects if effect.get("enabled",True) and effect.get("name") in NAMES]
        if keys:chain=",".join(keys)+","+chain
        if item.grayscale:chain+=",hue=s=0"
        if abs(item.brightness)>.0001 or abs(item.contrast-1)>.0001 or abs(item.saturation-1)>.0001:chain+=f",eq=brightness={item.brightness:.5f}:contrast={item.contrast:.5f}:saturation={item.saturation:.5f}"
        if item.sharpen>.0001:
            amount=min(5,max(0,item.sharpen*2)); chain+=f",unsharp=5:5:{amount:.4f}:5:5:0"
        if not animated:
            chain+=f",setpts=(PTS-STARTPTS)/{item.speed:.8f}"
            if elapsed:chain+=f",setpts=PTS+{elapsed:.6f}/TB"
        if item.fade_in>0:chain+=f",fade=t=in:st=0:d={min(item.duration,item.fade_in):.6f}:alpha=1"
        if item.fade_out>0:chain+=f",fade=t=out:st={max(0,item.duration-item.fade_out):.6f}:d={min(item.duration,item.fade_out):.6f}:alpha=1"
        trans_list = project.transitions_for_item(item.id) if getattr(project, "transitions_for_item", None) else []
        for trans in trans_list:
            t_dur = min(item.duration, trans.duration)
            if trans.right_item_id == item.id and item.fade_in <= 0:
                t_st = max(0.0, trans.start - item.start)
                col = ":color=white" if ("White" in trans.name or "Flash" in trans.name) else ""
                chain += f",fade=t=in:st={t_st:.6f}:d={t_dur:.6f}{col}:alpha=1"
            elif trans.left_item_id == item.id and item.fade_out <= 0:
                t_st = max(0.0, trans.start - item.start)
                col = ":color=white" if ("White" in trans.name or "Flash" in trans.name) else ""
                chain += f",fade=t=out:st={t_st:.6f}:d={t_dur:.6f}{col}:alpha=1"
        if 'opacity' in item.keyframes:chain+=f",geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({curve('opacity','T')})/100'"
        elif not opaque:chain+=f",colorchannelmixer=aa={max(0,min(1,item.opacity/100)):.6f}"
        chain+=f",setpts=PTS+{item.start-origin:.6f}/TB"
        label=f"layer{n}"; filters.append(f"[{source}]{chain}[{label}]")
        for en,effect in enumerate(item.effects):
            if not effect.get("enabled",True):continue
            from .effects import MATRICES, color_filter
            if effect.get("name") in MATRICES:
                out=f"fx{n}_{en}"; filters.append(f"[{label}]{color_filter(effect)}[{out}]"); label=out; continue
            if effect.get("name")!="Gaussian Blur":continue
            blurx=max(.01,effect.get("horizontal",12)); blury=max(.01,effect.get("vertical",12)); blend=effect.get("blend",100)/100
            out=f"fx{n}_{en}"
            border="reflect" if effect.get("border","Reflect")=="Reflect" else "smear"
            padding=max(2,min(64,round(max(blurx,blury)*2)))
            # Broad Gaussian kernels contain little high-frequency detail. Work
            # at a reduced resolution, then reconstruct; keep small kernels exact.
            factor=min(4,max(1,int(min(blurx,blury)/12)))
            if abs(item.transform.rotation)>.01 or animated:factor=1
            blur=f"pad=iw+{padding*2}:ih+{padding*2}:{padding}:{padding},fillborders=left={padding}:right={padding}:top={padding}:bottom={padding}:mode={border}"
            if factor>1:
                # Both dimensions are known before rotation. A split feeding
                # scale2ref can deadlock at EOF when its blur branch buffers
                # frames. A single-input chain has no cyclic framesync wait.
                padded_w=(width if item.role=='background' else lw)+padding*2
                padded_h=(height if item.role=='background' else lh)+padding*2
                blur+=f",scale={max(2,padded_w//factor)}:{max(2,padded_h//factor)}:flags=area,gblur=sigma={blurx/factor:.4f}:sigmaV={blury/factor:.4f},scale={padded_w}:{padded_h}:flags=bilinear,"
            else:blur+=f",gblur=sigma={blurx:.4f}:sigmaV={blury:.4f},"
            blur+=f"crop=iw-{padding*2}:ih-{padding*2}:{padding}:{padding}"
            if blend>=.999:filters.append(f"[{label}]{blur}[{out}]")
            else:
                filters.append(f"[{label}]split[fxorig{n}_{en}][fxin{n}_{en}]"); filters.append(f"[fxin{n}_{en}]{blur}[fxblur{n}_{en}]")
                filters.append(f"[fxorig{n}_{en}][fxblur{n}_{en}]blend=all_expr='A*(1-{blend:.4f})+B*{blend:.4f}'[{out}]")
            label=out
        out=f"video{n}"
        start_enable = item.start
        end_enable = item.start + item.duration
        for trans in trans_list:
            if trans.right_item_id == item.id:
                start_enable = min(start_enable, trans.start)
            if trans.left_item_id == item.id:
                end_enable = max(end_enable, trans.start + trans.duration)
        enable=f"gte(t,{start_enable-origin:.6f})*lt(t,{end_enable-origin:.6f})"
        repeatlast="1" if media.kind=="image" else "0"
        xpos=f'{ox:.4f}'; ypos=f'{oy:.4f}'
        if animated:
            clock=f'(t+{origin-item.start:.12g})'; sx=curve('scale',clock); sy=curve('scale_y',clock); rotation=f'({curve("rotation",clock)})*PI/180'
            ax=item.transform.anchor_x; ay=item.transform.anchor_y
            xpos=f'({curve("x",clock)})*{width}-{ax}*(({sx})-1)+{ax}-cos({rotation})*{ax}+sin({rotation})*{ay}'
            ypos=f'({curve("y",clock)})*{height}-{ay}*(({sy})-1)+{ay}-sin({rotation})*{ax}-cos({rotation})*{ay}'
            if item.retain_image_position and item.role!='background':
                crop=item.crop.clamped(); factor=max(width/max(1,media.width),height/max(1,media.height))*(.92 if item.role=='facecam' else 1.)
                xpos+=f'+{(crop.x+crop.width/2-.5)*media.width*factor}*({sx})'
                ypos+=f'+{(crop.y+crop.height/2-.5)*media.height*factor}*({sy})'
        if item.composite_mode=="Normal":filters.append(f"[{current}][{label}]overlay=x='{xpos}-w/2':y='{ypos}-h/2':enable='{enable}':{'format=auto:' if transparent else ''}eof_action=pass:repeatlast={repeatlast}[{out}]")
        else:
            mode={"Add":"addition","Multiply":"multiply","Screen":"screen"}.get(item.composite_mode,"normal")
            filters.append(f"color=c=black@0:s={width}x{height}:r={fps}:d={duration:.6f},format=rgba[transparent{n}]")
            filters.append(f"[transparent{n}][{label}]overlay=x='{xpos}-w/2':y='{ypos}-h/2':enable='{enable}':format=auto:eof_action=pass:repeatlast={repeatlast},split[full{n}][maskin{n}]")
            filters.append(f"[maskin{n}]alphaextract[mask{n}]"); filters.append(f"[{current}]split[orig{n}][blendin{n}]")
            filters.append(f"[blendin{n}][full{n}]blend=all_mode={mode}[blended{n}]"); filters.append(f"[orig{n}][blended{n}][mask{n}]maskedmerge[{out}]")
        current=out
    if ((burn_captions and project.captions) or any(item.role in {"title","graphic"} for item in project.timeline)) and ass_path:
        from .icons import resource_path
        fonts=_escape_ass_path(str(resource_path('assets','fonts')))
        filters.append(f"[{current}]ass='{_escape_ass_path(ass_path)}':fontsdir='{fonts}'{':alpha=1' if transparent else ''}[captions]"); current="captions"
    filters.append(f"[{current}]fps={fps},format={'rgba' if transparent else 'yuv420p'}[vout]")
    labels=[]
    if export_audio:
        for n,item in enumerate(i for i in project.timeline if i.track in project.audio_tracks and not i.muted and project.track_states.get(i.track,{}).get("visible",True) and not project.track_states.get(i.track,{}).get("muted",False)):
            media=project.media_by_id(item.media_id)
            if not media or not (media.has_audio or media.kind=="audio"):continue
            args += ["-ss",f"{item.in_point:.6f}","-t",f"{item.source_duration:.6f}","-i",media.path]
            chain=audio_filters(item)
            if project.settings.noise_reduction:chain+=",afftdn=nf=-25"
            chain+=f",adelay={round(item.start*1000)}:all=1"; label=f"audio{n}"; filters.append(f"[{index}:a]{chain}[{label}]"); index+=1; labels.append((label,item.role))
        filters.append(f"anullsrc=r=48000:cl=stereo:d={duration:.6f}[silence]")
        speech=[label for label,role in labels if role!="music"]; music=[label for label,role in labels if role=="music"]
        filters.append("[silence]"+"".join(f"[{label}]" for label in speech)+f"amix=inputs={len(speech)+1}:duration=first:normalize=0[speechmix]")
        if music:
            filters.append("".join(f"[{label}]" for label in music)+f"amix=inputs={len(music)}:duration=longest:normalize=0[musicmix]")
            if project.settings.auto_duck and speech:
                filters.append("[speechmix]asplit[speechmain][sidechain]"); filters.append("[musicmix][sidechain]sidechaincompress=threshold=0.045:ratio=6:attack=15:release=280[ducked]")
                filters.append("[speechmain][ducked]amix=inputs=2:duration=first:normalize=0[audiomix]")
            else:filters.append("[speechmix][musicmix]amix=inputs=2:duration=first:normalize=0[audiomix]")
        else:filters.append("[speechmix]anull[audiomix]")
        final="audiomix"
        if project.settings.normalize_audio:filters.append("[audiomix]loudnorm=I=-14:TP=-1.5:LRA=11[normalized]"); final="normalized"
    args += ["-filter_complex_threads","2","-filter_complex",";".join(filters),"-map","[vout]"]
    if export_audio:args += ["-map",f"[{final}]","-c:a","aac","-b:a",f"{preset.audio_kbps}k"]
    encoder,_=_encoder(preset.codec,"CPU" if hardware=="Auto" else hardware)
    args += encoder+["-b:v",f"{preset.bitrate_mbps:g}M","-maxrate",f"{preset.bitrate_mbps*1.3:g}M","-bufsize",f"{preset.bitrate_mbps*2:g}M","-movflags","+faststart","-t",f"{duration:.6f}","-progress","pipe:1","-nostats",output]
    return args
