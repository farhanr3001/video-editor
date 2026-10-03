"""ASS generation for track/custom caption typography, shadows and rounded cards."""
from pathlib import Path


def write(project,path,burn_captions=True):
    from .caption_fonts import load_fonts
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance():load_fonts()
    from .exporter import _ass_color,_ass_time
    from .model import Caption
    from PIL import ImageFont
    w,h=project.settings.width,project.settings.height
    entries=list(project.captions) if burn_captions and project.track_states.get("subtitle_1",{}).get("visible",True) else []
    titles={}
    for item in project.timeline:
        if item.role=="title" and not item.muted and item.track in project.video_tracks and project.track_states.get(item.track,{}).get("visible",True):
            titles[f'C{len(entries)}']=item
            entries.append(Caption(item.id,item.start,item.start+item.duration,item.title_text,item.title_style,False,True))
    lines=["[Script Info]","ScriptType: v4.00+",f"PlayResX: {w}",f"PlayResY: {h}","WrapStyle: 2","ScaledBorderAndShadow: yes","","[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding"]
    for n,cap in enumerate(entries):
        s=project.caption_style(cap)
        lines.append(f"Style: C{n},{s.font},{s.size},{_ass_color(s.color)},{_ass_color(s.highlight)},{_ass_color(s.outline)},{_ass_color(s.shadow_color)},{-1 if 'Bold' in s.font_face else 0},{-1 if 'Italic' in s.font_face else 0},0,0,{s.zoom_x*100},{s.zoom_y*100},{s.kerning},0,1,{s.outline_width},0,5,0,0,0,1")
    lines += ["","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    def alpha(opacity):return f"&H{max(0,min(255,round(255*(1-opacity/100)))):02X}&"
    def escape(text):return text.replace("\\",r"\\").replace("{",r"\{").replace("}",r"\}")
    for n,cap in enumerate(entries):
        s=project.caption_style(cap); raw=cap.text.upper() if s.uppercase else cap.text
        if (s.animation in ('word highlight','word highlight 2','fade every word','word reveal','punch','bounce','karaoke','emoji pop','double emoji') or s.glow_enabled or s.font in ('Geometos','TikTok Sans','Montserrat','Poppins','Anton','Archivo Black','Bebas Neue','Bangers')) and s.box_style!="headline":
            from .word_highlight import events
            lines.extend(events(project,cap,f"C{n}")); continue
        if s.box_style=="headline":
            from .headline import paths,ass_path,emoji_positions
            letters,backing=paths(cap.text,s,w,h)
            for layer,shape,color in ((0,backing,"#FFFFFF"),(2,letters,s.color)):
                if shape.isEmpty():continue
                # Move paths into a zero-origin drawing. ASS aligns the drawing's
                # bounding box, not its absolute coordinates, to the pos tag.
                bounds=shape.boundingRect(); shape.translate(-bounds.left(),-bounds.top())
                tags=f"\\an7\\pos({bounds.left():.3f},{bounds.top():.3f})\\fscx100\\fscy100\\p1\\bord0\\shad0\\1c{_ass_color(color)}\\alpha{alpha(s.opacity)}"
                lines.append(f"Dialogue: {layer},{_ass_time(cap.start)},{_ass_time(cap.end)},C{n},,0,0,0,,{{{tags}}}{ass_path(shape)}")
            from .emoji import ass_events
            lines.extend(ass_events(emoji_positions(cap.text,s,w,h),cap.start,cap.end,f"C{n}",s.opacity))
            continue
        try:
            from PySide6.QtGui import QFont,QFontMetricsF,QGuiApplication
            if not QGuiApplication.instance():raise RuntimeError()
            font=QFont(s.font); font.setPixelSize(round(s.size)); font.setBold("Bold" in s.font_face); font.setItalic("Italic" in s.font_face); metrics=QFontMetricsF(font)
            from .emoji import measure as emoji_measure
            font.setLetterSpacing(QFont.AbsoluteSpacing,s.kerning)
            measure=lambda text:emoji_measure(text,font)
            lineheight=metrics.height()
        except Exception:
            try:font=ImageFont.truetype("arialbd.ttf" if "Bold" in s.font_face else "arial.ttf",round(s.size))
            except OSError:font=ImageFont.load_default()
            measure=lambda text:font.getlength(text)+max(0,len(text)-1)*s.kerning
            lineheight=s.size*1.2
        textlines=[]
        for paragraph in raw.split("\n"):
            line=""
            for word in paragraph.split():
                candidate=(line+" "+word).strip()
                if line and measure(candidate)*s.zoom_x>w*.9:textlines.append(line); line=word
                else:line=candidate
            textlines.append(line)
        x=w*s.position_x; y=h*s.position_y
        if cap.is_hook:x=w*.5; y=h*.09
        line_step=max(1,(lineheight+s.line_spacing)*s.zoom_y); total_height=lineheight*s.zoom_y+line_step*(len(textlines)-1)
        top=y if s.anchor=="Top" else y-total_height if s.anchor=="Bottom" else y-total_height/2
        widths=[max(1,measure(text)*s.zoom_x) for text in textlines]; box_width=max(widths,default=1)+24; box_height=total_height+16
        def event(layer,tags,text):
            lines.append(f"Dialogue: {layer},{_ass_time(cap.start)},{_ass_time(cap.end)},C{n},,0,0,0,,{{{tags}}}{text}")
        anim=""
        if s.animation=="fade":anim=r"\fad(100,100)"
        elif s.animation=="pop":anim=f"\\fscx{s.zoom_x*72:g}\\fscy{s.zoom_y*72:g}\\t(0,130,\\fscx{s.zoom_x*108:g}\\fscy{s.zoom_y*108:g})\\t(130,220,\\fscx{s.zoom_x*100:g}\\fscy{s.zoom_y*100:g})"
        elif s.animation=='punch':anim=f"\\fscx{s.zoom_x*55:g}\\fscy{s.zoom_y*55:g}\\t(0,100,\\fscx{s.zoom_x*115:g}\\fscy{s.zoom_y*115:g})\\t(100,220,\\fscx{s.zoom_x*100:g}\\fscy{s.zoom_y*100:g})"
        elif s.animation=='bounce':anim=f"\\fscx{s.zoom_x*40:g}\\fscy{s.zoom_y*40:g}\\t(0,120,\\fscx{s.zoom_x*125:g}\\fscy{s.zoom_y*125:g})\\t(120,200,\\fscx{s.zoom_x*95:g}\\fscy{s.zoom_y*95:g})\\t(200,280,\\fscx{s.zoom_x*100:g}\\fscy{s.zoom_y*100:g})"
        if cap.is_hook or s.background_enabled:
            if s.background_override:box_width=w*s.background_width; box_height=h*s.background_height
            left=x-box_width/2; by=top-8
            if s.alignment=="Left":left=x-12
            elif s.alignment=="Right":left=x-box_width+12
            radius=min(box_width/2,box_height/2,s.background_radius*w); r=radius; bw=box_width; bh=box_height
            vector=f"m {r:.2f} 0 l {bw-r:.2f} 0 b {bw:.2f} 0 {bw:.2f} 0 {bw:.2f} {r:.2f} l {bw:.2f} {bh-r:.2f} b {bw:.2f} {bh:.2f} {bw:.2f} {bh:.2f} {bw-r:.2f} {bh:.2f} l {r:.2f} {bh:.2f} b 0 {bh:.2f} 0 {bh:.2f} 0 {bh-r:.2f} l 0 {r:.2f} b 0 0 0 0 {r:.2f} 0"
            tags=f"\\an7\\pos({left:.3f},{by:.3f})\\fscx100\\fscy100\\p1\\bord{s.background_outline_width}\\shad0\\1c{_ass_color('#F8F8F6' if cap.is_hook else s.background_color)}\\3c{_ass_color(s.background_outline)}\\alpha{alpha(s.opacity*(1 if cap.is_hook else s.background_opacity/100))}"
            event(0,tags,vector)
        elapsed_words=0; total_words=max(1,len(raw.split())); word_cs=max(1,round((cap.end-cap.start)*100/total_words))
        for row,text in enumerate(textlines):
            cy=top+lineheight*s.zoom_y/2+row*line_step
            align={"Left":4,"Center":5,"Right":6,"Justify":5}.get(s.alignment,5)
            base=f"\\an{align}\\pos({x:.3f},{cy:.3f})"
            if s.glow_enabled:
                event(1,base+f"\\bord0\\shad0\\blur{s.glow_radius}\\1c{_ass_color(s.color if s.glow_follow_color else s.glow_color)}\\alpha{alpha(s.opacity*s.glow_opacity/100)}"+anim,escape(text))
            from .emoji import contains_emoji,segments,ass_events
            if contains_emoji(text):
                from PySide6.QtCore import QRectF
                left=x if s.alignment=="Left" else x-widths[row] if s.alignment=="Right" else x-widths[row]/2
                for value,is_emoji in segments(text):
                    if is_emoji:
                        rect=QRectF(left,cy-s.size*s.zoom_y*.5,s.size*s.zoom_x,s.size*s.zoom_y)
                        onset=cap.start+elapsed_words*word_cs/100 if s.animation=="word reveal" else cap.start
                        lines.extend(ass_events([(value,rect)],onset,cap.end,f"C{n}",s.opacity,s.animation,origin=(x,y))); left+=s.size*s.zoom_x; elapsed_words+=1
                    else:
                        if s.shadow_enabled:
                            event(1,f"\\an4\\pos({left+s.shadow_x:.3f},{cy+s.shadow_y:.3f})\\bord0\\shad0\\blur{s.shadow_blur}\\1c{_ass_color(s.shadow_color)}\\alpha{alpha(s.opacity*s.shadow_opacity/100)}"+anim,escape(value))
                        rendered=escape(value)
                        if s.animation=="word reveal":rendered=f"{{\\k{elapsed_words*word_cs}}}"+" ".join(f"{{\\k{word_cs}}}"+escape(word) for word in value.split())
                        event(2,f"\\an4\\pos({left:.3f},{cy:.3f})\\alpha{alpha(s.opacity)}"+anim,rendered); left+=measure(value)*s.zoom_x; elapsed_words+=len(value.split())
                continue
            if s.shadow_enabled and not cap.is_hook:
                tags=f"\\an{align}\\pos({x+s.shadow_x:.3f},{cy+s.shadow_y:.3f})\\bord0\\shad0\\blur{s.shadow_blur}\\1c{_ass_color(s.shadow_color)}\\alpha{alpha(s.opacity*s.shadow_opacity/100)}"+anim
                event(1,tags,escape(text))
            rendered=escape(text)
            if s.animation=="word reveal":rendered=f"{{\\k{elapsed_words*word_cs}}}"+" ".join(f"{{\\k{word_cs}}}"+escape(word) for word in text.split())
            elapsed_words+=len(text.split())
            event(2,base+f"\\alpha{alpha(s.opacity)}"+anim,rendered)
    from .graphics import graphic_to_ass_events
    for item in project.timeline:
        if item.role=="graphic" and not item.muted and item.track in project.video_tracks and project.track_states.get(item.track,{}).get("visible",True):
            lines.extend(graphic_to_ass_events(project,item))
    from .title_fades import apply_ass
    Path(path).write_text("\n".join(apply_ass(lines,titles,project.settings.fps)),encoding="utf-8-sig")
