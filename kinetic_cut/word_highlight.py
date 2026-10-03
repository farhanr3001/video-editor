"""Active-word cards share glyph geometry with the preview compositor."""
from PySide6.QtCore import QRectF,QPointF
from PySide6.QtGui import QPainterPath,QGuiApplication

_application=None

def events(project,caption,style_name):
    global _application
    if QGuiApplication.instance() is None:_application=QGuiApplication([])
    from .visuals import caption_geometry
    from .headline import ass_path
    from .emoji import ass_events
    from .exporter import _ass_color,_ass_time
    style=project.caption_style(caption); width=project.settings.width; height=project.settings.height
    letters,emojis,bounds,words,word_glyphs,x,y=caption_geometry(project,caption,QRectF(0,0,width,height)); result=[]
    def event(shape,color,layer,start=None,end=None,opacity=None,extra=""):
        if shape.isEmpty():return
        shape=QPainterPath(shape); rect=shape.boundingRect(); shape.translate(-rect.topLeft())
        alpha=round(255*(1-(style.opacity if opacity is None else opacity)/100))
        begin=caption.start if start is None else start; finish=caption.end if end is None else end
        phases=[(0,finish-begin,1.,1.)]
        if style.animation=='pop':phases=[(0,.13,.72,1.08),(.13,.22,1.08,1.),(.22,finish-begin,1.,1.)]
        if style.animation=='punch':phases=[(0,.10,.55,1.15),(.10,.22,1.15,1.),(.22,finish-begin,1.,1.)]
        if style.animation=='bounce':phases=[(0,.12,.40,1.25),(.12,.20,1.25,.95),(.20,.28,.95,1.),(.28,finish-begin,1.,1.)]
        for a,b,first,last in phases:
            b=min(b,finish-begin)
            if b<=a:continue
            x1=x+(rect.left()-x)*first; y1=y+(rect.top()-y)*first; x2=x+(rect.left()-x)*last; y2=y+(rect.top()-y)*last
            position=f"\\pos({x1:.3f},{y1:.3f})" if first==last else f"\\move({x1:.3f},{y1:.3f},{x2:.3f},{y2:.3f},0,{round((b-a)*1000)})"
            anim='' if first==last else f"\\t(0,{round((b-a)*1000)},\\fscx{last*100:g}\\fscy{last*100:g})"
            if style.animation=='fade':anim+=r'\fad(100,100)'
            tags=f"\\an7{position}\\p1\\fscx{first*100:g}\\fscy{first*100:g}\\bord0\\shad0\\1c{_ass_color(color)}\\alpha&H{alpha:02X}&"+extra+anim
            result.append(f"Dialogue: {layer},{_ass_time(begin+a)},{_ass_time(begin+b)},{style_name},,0,0,0,,{{{tags}}}{ass_path(shape)}")
    if style.background_enabled or caption.is_hook:
        if style.background_override:bounds=QRectF(x-width*style.background_width/2,y-height*style.background_height/2,width*style.background_width,height*style.background_height)
        path=QPainterPath(); path.addRoundedRect(bounds,style.background_radius*width,style.background_radius*width)
        event(path,'#f8f8f6' if caption.is_hook else style.background_color,0,opacity=style.opacity if caption.is_hook else style.opacity*style.background_opacity/100,extra=f"\\bord{style.background_outline_width}\\3c{_ass_color(style.background_outline)}")
    from .caption_words import timings
    times=timings(caption)
    if (len(words)>1 or style.animation=='word highlight 2') and style.animation in ('word highlight','word highlight 2'):
        for n,rect in enumerate(words):
            if style.animation=='word highlight 2' and n not in caption.highlighted_words:continue
            path=QPainterPath(); path.addRoundedRect(rect,5,5)
            a,b=times[n] if style.animation=='word highlight' else (caption.start,caption.end)
            if min(b,caption.end)>max(a,caption.start):event(path,style.highlight,1,max(a,caption.start),min(b,caption.end))
    pieces=word_glyphs if style.animation in ('fade every word','word reveal','karaoke','emoji pop','double emoji') else [(letters,emojis)]
    for n,(shape,runs) in enumerate(pieces):
        start=max(caption.start,times[n][0]) if style.animation in ('fade every word','word reveal') else caption.start
        if start>=caption.end:continue
        if style.animation in ('karaoke','emoji pop','double emoji') and len(times)>n:
            w_start,w_end=times[n]
            single=len(pieces)==1
            from .caption_emphasis import single_word_emphasized
            emphasized=not single or single_word_emphasized(project,caption)
            active_color=style.highlight if emphasized else style.color
            if single:w_start,w_end=caption.start,caption.end
            if w_start>caption.start:
                event(shape,style.color,3,caption.start,w_start,extra=f"\\bord{style.outline_width}\\3c{_ass_color(style.outline)}")
            if w_end>w_start:
                if style.glow_enabled:
                    event(shape,active_color,2,w_start,w_end,opacity=style.opacity,extra=f"\\blur{style.glow_radius}")
                event(shape,active_color,3,w_start,w_end,extra=f"\\bord{style.outline_width}\\3c{_ass_color(style.outline)}")
            if caption.end>w_end:
                event(shape,style.color,3,w_end,caption.end,extra=f"\\bord{style.outline_width}\\3c{_ass_color(style.outline)}")
            result.extend(ass_events(runs,caption.start,caption.end,style_name,style.opacity,style.animation,layer=4,origin=(x,y)))
            if style.animation in ('emoji pop','double emoji') and len(words)>n:
                from .caption_emojis import emojis_for_caption
                max_e = 2 if style.animation=='double emoji' else 1
                cap_emojis = emojis_for_caption(project,caption,max_e)
                active_e = [e for idx, e in cap_emojis if idx == n]
                if active_e:
                    box = words[n]
                    from .visuals import caption_emoji_rect
                    e_runs = [(active_e[0],caption_emoji_rect(bounds,box))]
                    center=e_runs[0][1].center()
                    result.extend(ass_events(e_runs, w_start, w_end, style_name, style.opacity, 'pop', layer=5, origin=(center.x(),center.y())))
            continue
        anim=r'\fad(120,100)' if style.animation=='fade every word' else ''
        if style.glow_enabled:event(shape,style.color if style.glow_follow_color else style.glow_color,2,start,opacity=style.opacity*style.glow_opacity/100,extra=f"\\blur{style.glow_radius}"+anim)
        if style.shadow_enabled:
            shadow=QPainterPath(shape); shadow.translate(style.shadow_x,style.shadow_y)
            event(shadow,style.shadow_color,2,start,opacity=style.opacity*style.shadow_opacity/100,extra=f"\\blur{style.shadow_blur}"+anim)
        event(shape,style.color,3,start,extra=f"\\bord{style.outline_width}\\3c{_ass_color(style.outline)}"+anim)
        result.extend(ass_events(runs,start,caption.end,style_name,style.opacity,'fade' if anim else style.animation,layer=4,origin=(x,y)))
    return result
