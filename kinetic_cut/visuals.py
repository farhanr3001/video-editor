"""CPU preview effects and subtitle layout at viewer resolution."""
import copy
from PIL import Image,ImageFilter,ImageChops
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QColor,QFont,QFontMetricsF,QPainterPath,QPen,QTransform


def blur_image(image,rx,ry,blend=1.,border="Replicate", *, preview_fast=False):
    if max(rx,ry)<.05 or blend<=0:return image
    if preview_fast:
        # Large Gaussian kernels remove high frequencies themselves. Filter a
        # mip level with at least a 3px sigma, then reconstruct; unlike a global
        # low-resolution preview this does not soften unblurred foregrounds.
        # Keep both axes' radii and the original blend (including its sharp part).
        factor=min(8.,max(1.,min(rx,ry)/3.))
        if factor>=2.:
            small=image.scaled(max(1,round(image.width()/factor)),max(1,round(image.height()/factor)),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            blurred=blur_image(small,rx*small.width()/image.width(),ry*small.height()/image.height(),1.,border)
            result=blurred.scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            if blend>=1:return result
            # Pixel interpolation, not SourceOver: alpha and transparent edges
            # must retain the same semantics as the full-quality filter.
            original=image.convertToFormat(QImage.Format_RGBA8888)
            result=result.convertToFormat(QImage.Format_RGBA8888)
            a=Image.frombytes('RGBA',(original.width(),original.height()),bytes(original.constBits()))
            b=Image.frombytes('RGBA',(result.width(),result.height()),bytes(result.constBits()))
            data=Image.blend(a,b,max(0.,min(1.,blend))).tobytes()
            return QImage(data,image.width(),image.height(),QImage.Format_RGBA8888).copy()
    converted=image.convertToFormat(QImage.Format_RGBA8888)
    pil=Image.frombytes("RGBA",(converted.width(),converted.height()),bytes(converted.constBits()))
    import numpy as np
    padding=max(2,min(128,round(max(rx,ry)*2)))
    padded=Image.fromarray(np.pad(np.asarray(pil),((padding,padding),(padding,padding),(0,0)),mode="reflect" if border=="Reflect" else "edge"))
    r=max(.1,min(rx,ry)); size=(max(4,round(padded.width*r/max(.1,rx))),max(4,round(padded.height*r/max(.1,ry))))
    blurred=padded.resize(size,Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(r)).resize(padded.size,Image.Resampling.BILINEAR).crop((padding,padding,padding+pil.width,padding+pil.height))
    if blend<1:blurred=Image.blend(pil,blurred,max(0,blend))
    data=blurred.tobytes(); return QImage(data,blurred.width,blurred.height,QImage.Format_RGBA8888).copy()


def soften_edges(image,rx,ry):
    import numpy as np
    converted=image.convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(converted.constBits(),dtype=np.uint8).reshape(converted.height(),converted.width(),4).copy()
    h,w=pixels.shape[:2]; x=np.arange(w); y=np.arange(h)
    mask=np.minimum(np.minimum(x,w-x)[None,:]/max(.1,rx),np.minimum(y,h-y)[:,None]/max(.1,ry)).clip(0,1)
    pixels[:,:,3]=(pixels[:,:,3]*mask).astype(np.uint8)
    return QImage(pixels.data,w,h,QImage.Format_RGBA8888).copy()


def grade_image(image,grayscale=False,brightness=0.,contrast=1.,saturation=1.,sharpen=0.):
    """Compact CPU approximation of the export colour pipeline."""
    if not grayscale and abs(brightness)<.001 and abs(contrast-1)<.001 and abs(saturation-1)<.001 and sharpen<.001:return image
    converted=image.convertToFormat(QImage.Format_RGBA8888)
    pil=Image.frombytes("RGBA",(converted.width(),converted.height()),bytes(converted.constBits()))
    from PIL import ImageEnhance
    if grayscale:pil=Image.merge("RGBA",(pil.convert("L"),pil.convert("L"),pil.convert("L"),pil.getchannel("A")))
    if abs(brightness)>.001:pil=ImageEnhance.Brightness(pil).enhance(max(0,1+brightness))
    if abs(contrast-1)>.001:pil=ImageEnhance.Contrast(pil).enhance(max(0,contrast))
    if abs(saturation-1)>.001:pil=ImageEnhance.Color(pil).enhance(max(0,saturation))
    if sharpen>.001:pil=ImageEnhance.Sharpness(pil).enhance(1+sharpen*2)
    data=pil.tobytes(); return QImage(data,pil.width,pil.height,QImage.Format_RGBA8888).copy()


def caption_geometry(project,caption,frame):
    from .caption_fonts import load_fonts
    load_fonts()
    style=project.caption_style(caption); scale=frame.width()/project.settings.width
    from .emoji import measure,text_path
    # Shape once in output coordinates, then scale paths. Small hinted fonts can
    # change word advances independently and produce zoom-dependent italic gaps.
    font=QFont(style.font); font.setPixelSize(max(4,round(style.size))); font.setBold("Bold" in style.font_face); font.setItalic("Italic" in style.font_face)
    font.setLetterSpacing(QFont.AbsoluteSpacing,style.kerning); metrics=QFontMetricsF(font)
    text=caption.text.upper() if style.uppercase else caption.text; max_width=project.settings.width*.9/max(.1,style.zoom_x)
    lines=[]
    for paragraph in text.split("\n"):
        line=""
        for word in paragraph.split():
            candidate=(line+" "+word).strip()
            if line and measure(candidate,font)>max_width:lines.append(line); line=word
            else:line=candidate
        lines.append(line)
    path=QPainterPath(); emojis=[]; word_boxes=[]; raw_word_glyphs=[]; line_height=max(1,metrics.height()+style.line_spacing)
    import re
    for n,line in enumerate(lines):
        width=measure(line,font)
        x=0 if style.alignment=="Left" else -width if style.alignment=="Right" else -width/2
        glyphs,runs=text_path(line,font,QPointF(x,n*line_height)); path.addPath(glyphs); emojis.extend(runs)
        for word in re.finditer(r'\S+',line):
            w_text=word.group()
            w_x=x+measure(line[:word.start()],font)
            w_path,w_emojis=text_path(w_text,font,QPointF(w_x,n*line_height))
            raw_word_glyphs.append((w_path,w_emojis))
            word_boxes.append(QRectF(w_x,n*line_height-metrics.ascent(),measure(w_text,font),metrics.height()))
    transform=QTransform(); transform.scale(style.zoom_x*scale,style.zoom_y*scale); path=transform.map(path)
    emojis=[(sequence,transform.mapRect(rect)) for sequence,rect in emojis]
    bounds=path.boundingRect(); x=frame.left()+style.position_x*frame.width(); y=frame.top()+style.position_y*frame.height()
    for _,rect in emojis:bounds=bounds.united(rect)
    if caption.is_hook:x=frame.center().x(); y=frame.top()+frame.height()*.09
    offset_y=-bounds.top() if style.anchor=="Top" else -bounds.bottom() if style.anchor=="Bottom" else -bounds.center().y()
    path.translate(x,y+offset_y); emojis=[(sequence,rect.translated(x,y+offset_y)) for sequence,rect in emojis]; bounds=bounds.translated(x,y+offset_y).adjusted(-8*scale,-5*scale,8*scale,5*scale)
    word_boxes=[transform.mapRect(rect).translated(x,y+offset_y).adjusted(-6*scale,-2*scale,6*scale,2*scale) for rect in word_boxes]
    word_glyphs=[]
    for w_path,w_emojis in raw_word_glyphs:
        mapped_path=transform.map(w_path); mapped_path.translate(x,y+offset_y)
        mapped_emojis=[(seq,transform.mapRect(r).translated(x,y+offset_y)) for seq,r in w_emojis]
        word_glyphs.append((mapped_path,mapped_emojis))
    return path,emojis,bounds,word_boxes,word_glyphs,x,y


def caption_emoji_rect(bounds,word_box,scale=1.):
    size=max(24.*scale,word_box.height()*1.15)
    center=QPointF(bounds.center().x(),bounds.top()-size*.55-6*scale)
    return QRectF(center.x()-size/2,center.y()-size/2,size,size)


def draw_caption(painter,project,caption,frame):
    if project.caption_style(caption).box_style=="headline":
        from .headline import draw
        return draw(painter,project,caption,frame)
    style=project.caption_style(caption); scale=frame.width()/project.settings.width
    from .emoji import measure,text_path,draw as draw_emoji
    path,emojis,bounds,word_boxes,word_glyphs,x,y=caption_geometry(project,caption,frame)
    inherited_opacity=painter.opacity(); painter.save(); painter.setClipRect(frame); painter.setOpacity(inherited_opacity*style.opacity/100)
    elapsed=project.playhead-caption.start
    if style.animation=="fade":painter.setOpacity(inherited_opacity*style.opacity/100*min(1,max(0,elapsed/.1))*min(1,max(0,(caption.end-project.playhead)/.1)))
    if style.animation in ('pop','punch') and elapsed<.22:
        factor=.72+min(1,elapsed/.13)*.36 if elapsed<.13 else 1.08-(elapsed-.13)/.09*.08
        if style.animation=='punch':factor=.55+min(1,max(0,elapsed)/.10)*.6 if elapsed<.10 else 1.15-min(1,(elapsed-.10)/.12)*.15
        painter.translate(x,y); painter.scale(factor,factor); painter.translate(-x,-y)
    elif style.animation=='bounce' and elapsed<.28:
        factor=.40+(elapsed/.12)*.85 if elapsed<.12 else 1.25-((elapsed-.12)/.08)*.30 if elapsed<.20 else .95+((elapsed-.20)/.08)*.05
        painter.translate(x,y); painter.scale(factor,factor); painter.translate(-x,-y)
    if caption.is_hook or style.background_enabled:
        if style.background_override:bounds=QRectF(x-frame.width()*style.background_width/2,y-frame.height()*style.background_height/2,frame.width()*style.background_width,frame.height()*style.background_height)
        color=QColor("#f8f8f6" if caption.is_hook else style.background_color); color.setAlphaF(1. if caption.is_hook else style.background_opacity/100)
        painter.setBrush(color); painter.setPen(QPen(QColor(style.background_outline),style.background_outline_width*scale) if style.background_outline_width else Qt.NoPen)
        radius=max(0,style.background_radius*frame.width()); painter.drawRoundedRect(bounds,radius,radius)
    from .caption_words import active_word,timings
    if style.animation in ('word highlight','word highlight 2') and (len(word_boxes)>1 or style.animation=='word highlight 2'):
        active=active_word(caption,project.playhead)
        indices=[active] if style.animation=='word highlight' and active is not None else caption.highlighted_words if style.animation=='word highlight 2' else []
        for index in indices:
            if 0<=index<len(word_boxes):
                painter.setPen(Qt.NoPen); painter.setBrush(QColor(style.highlight)); painter.drawRoundedRect(word_boxes[index],5*scale,5*scale)
    if style.animation in ('fade every word','word reveal'):
        for index,(shape,runs) in enumerate(word_glyphs):
            onset=timings(caption)[index][0]; painter.save()
            opacity=max(0,min(1,(project.playhead-onset)/.12))*max(0,min(1,(caption.end-project.playhead)/.1)) if style.animation=='fade every word' else float(project.playhead>=onset)
            painter.setOpacity(painter.opacity()*opacity)
            draw_caption_glyphs(painter,shape,runs,style,scale); painter.restore()
    elif style.animation in ('karaoke','emoji pop','double emoji'):
        from .caption_emphasis import single_word_emphasized
        single=len(word_glyphs)==1
        active=(0 if single_word_emphasized(project,caption) else None) if single else active_word(caption,project.playhead)
        times=timings(caption)
        for index,(shape,runs) in enumerate(word_glyphs):
            word_style=style
            if index==active:
                word_style=copy.copy(style)
                word_style.color=style.highlight
                word_style.glow_enabled=True
                word_style.glow_color=style.highlight
            draw_caption_glyphs(painter,shape,runs,word_style,scale)
        if style.animation in ('emoji pop','double emoji') and word_boxes:
            from .caption_emojis import emojis_for_caption
            max_e = 2 if style.animation == 'double emoji' else 1
            emoji_active=0 if single else active_word(caption,project.playhead)
            caption_emojis = [(index,emoji) for index,emoji in emojis_for_caption(project,caption,max_e) if index==emoji_active]
            if caption_emojis:
                target_idx = caption_emojis[0][0]
                target_idx = min(max(0, target_idx), len(word_boxes) - 1)
                box = word_boxes[target_idx]
                onset = times[target_idx][0] if not single and target_idx < len(times) else caption.start
                elapsed_word = project.playhead - onset
                if elapsed_word >= 0:
                    pop_factor = 0.2 + (elapsed_word / 0.12) * 1.1 if elapsed_word < 0.12 else 1.30 - ((elapsed_word - 0.12) / 0.08) * 0.30 if elapsed_word < 0.20 else 1.0
                    emoji_rect=caption_emoji_rect(bounds,box,scale)
                    emoji_size=emoji_rect.width(); center_x=emoji_rect.center().x(); center_y=emoji_rect.center().y()
                    e_list = [e for _, e in caption_emojis]
                    if len(e_list) == 2:
                        e_runs = [
                            (e_list[0], QRectF(center_x - emoji_size - 2 * scale, center_y - emoji_size / 2, emoji_size, emoji_size)),
                            (e_list[1], QRectF(center_x + 2 * scale, center_y - emoji_size / 2, emoji_size, emoji_size))
                        ]
                    else:
                        e_runs = [
                            (e_list[0], QRectF(center_x - emoji_size / 2, center_y - emoji_size / 2, emoji_size, emoji_size))
                        ]
                    painter.save()
                    painter.translate(center_x, center_y)
                    painter.scale(pop_factor, pop_factor)
                    painter.translate(-center_x, -center_y)
                    draw_emoji(painter, e_runs)
                    painter.restore()
    else:draw_caption_glyphs(painter,path,emojis,style,scale)
    painter.restore(); return bounds


def word_shapes(path,emojis,boxes):
    for rect in boxes:
        clip=QPainterPath(); clip.addRect(rect)
        yield path.intersected(clip),[(text,box) for text,box in emojis if rect.contains(box.center())]


from .image_cache import ImageCache

_glow_cache=ImageCache(64*1024*1024, max_entries=64)
def draw_caption_glyphs(painter,path,emojis,style,scale):
    from .emoji import draw as draw_emoji
    if style.glow_enabled and not path.isEmpty():
        from PySide6.QtGui import QPainter
        radius=max(.1,style.glow_radius*scale); margin=radius*3+style.outline_width*scale
        bounds=path.boundingRect().adjusted(-margin,-margin,margin,margin)
        shape=QPainterPath(path); shape.translate(-bounds.topLeft())
        color=style.color if style.glow_follow_color else style.glow_color
        key=(color,round(radius,3),style.glow_opacity,tuple((round(shape.elementAt(i).x,3),round(shape.elementAt(i).y,3),shape.elementAt(i).type.value) for i in range(shape.elementCount())))
        layer=_glow_cache.get(key)
        if layer is None:
            layer=QImage(max(1,round(bounds.width())),max(1,round(bounds.height())),QImage.Format_RGBA8888); layer.fill(Qt.transparent)
            glow=QPainter(layer); glow.setRenderHint(QPainter.Antialiasing); glow.setPen(Qt.NoPen); glow.setBrush(QColor(color)); glow.drawPath(shape); glow.end()
            pixels=Image.frombytes('RGBA',(layer.width(),layer.height()),bytes(layer.constBits()))
            alpha=pixels.getchannel('A').filter(ImageFilter.GaussianBlur(radius))
            pixels=Image.new('RGBA',pixels.size,color); pixels.putalpha(alpha); data=pixels.tobytes()
            layer=QImage(data,pixels.width,pixels.height,QImage.Format_RGBA8888).copy()
            _glow_cache.put(key,layer)
        painter.save(); painter.setOpacity(painter.opacity()*style.glow_opacity/100); painter.drawImage(bounds.topLeft(),layer); painter.restore()
    if style.shadow_enabled:
        shadow=QPainterPath(path); shadow.translate(style.shadow_x*scale,style.shadow_y*scale)
        color=QColor(style.shadow_color); color.setAlphaF(style.shadow_opacity/100)
        if style.shadow_blur*scale>.5:
            from PySide6.QtGui import QPainter
            margin=style.shadow_blur*scale*3; r=shadow.boundingRect().adjusted(-margin,-margin,margin,margin)
            layer=QImage(max(1,round(r.width())),max(1,round(r.height())),QImage.Format_RGBA8888); layer.fill(Qt.transparent)
            sp=QPainter(layer); sp.setRenderHint(QPainter.Antialiasing); sp.translate(-r.topLeft()); sp.setPen(Qt.NoPen); sp.setBrush(color); sp.drawPath(shadow); sp.end()
            painter.drawImage(r.topLeft(),blur_image(layer,style.shadow_blur*scale,style.shadow_blur*scale))
        else:painter.setPen(Qt.NoPen); painter.setBrush(color); painter.drawPath(shadow)
    if style.outline_width:painter.strokePath(path,QPen(QColor(style.outline),style.outline_width*scale*2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    # Fill after the outline, otherwise the centred pen covers small glyphs.
    painter.fillPath(path,QColor(style.color)); draw_emoji(painter,emojis)
