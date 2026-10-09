"""Fitted social headline geometry shared by the viewer and ASS export."""
from functools import lru_cache
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPainterPath, QTransform, QColor, QGuiApplication

_font_application=None


def headline_style():
    from .model import CaptionStyle
    return CaptionStyle(name="Headline",box_style="headline",font="Arial",font_face="Bold",size=72,
                        color="#000000",outline_width=0,shadow_enabled=False,animation="none",
                        position_y=.5,uppercase=False,background_enabled=True,
                        background_color="#FFFFFF",background_opacity=100)


def wrap_lines(text,measure,max_width):
    """Respect hard breaks, including empty lines, and wrap unbroken long words."""
    lines=[]
    for paragraph in text.split("\n"):
        line=""
        for word in paragraph.split():
            candidate=(line+" "+word).strip()
            if line and measure(candidate)>max_width:lines.append(line); line=""
            while measure(word)>max_width and len(word)>1:
                split=1
                while split<len(word) and measure(word[:split+1])<=max_width:split+=1
                if line:lines.append(line); line=""
                lines.append(word[:split]); word=word[split:]
            line=(line+" "+word).strip()
        lines.append(line)
    return lines


@lru_cache(maxsize=128)
def layout(text,width,font_name,size,bold=True):
    global _font_application
    # CLI exports also need a font database, but never a visible window.
    if QGuiApplication.instance() is None:_font_application=QGuiApplication([])
    font=QFont(font_name); font.setPixelSize(max(8,round(size))); font.setBold(bold)
    metrics=QFontMetricsF(font); padding=size*.28; line_height=metrics.height()
    from .emoji import measure,text_path
    rows=wrap_lines(text,lambda value:measure(value,font),max(1,width*.9-padding*2))
    letters=QPainterPath(); backing=QPainterPath()
    emojis=[]
    if not text.strip():return letters,backing,emojis
    top=-len(rows)*line_height/2; radius=size*.11
    for n,row in enumerate(rows):
        advance=max(1,measure(row,font)); y=top+n*line_height
        glyphs,runs=text_path(row,font,QPointF(-advance/2,y+metrics.ascent())); letters.addPath(glyphs); emojis.extend(runs)
        rectangle=QPainterPath(); rectangle.addRoundedRect(QRectF(-advance/2-padding,y-size*.06,advance+padding*2,line_height+size*.12),radius,radius)
        backing=backing.united(rectangle)
    return letters,backing,emojis


def geometry(text,width,font_name,size,bold=True):return layout(text,width,font_name,size,bold)[:2]


def emoji_positions(text,style,width,height):
    transform=QTransform(); transform.translate(width*style.position_x,height*style.position_y); transform.scale(style.zoom_x,style.zoom_x)
    return [(sequence,transform.mapRect(rect)) for sequence,rect in layout(text,width,style.font,style.size,'Bold' in style.font_face)[2]]


def paths(text,style,width,height):
    letters,backing=geometry(text,width,style.font,style.size,'Bold' in style.font_face)
    transform=QTransform(); transform.translate(width*style.position_x,height*style.position_y)
    # A single uniform scale intentionally leaves wrapping unchanged.
    transform.scale(style.zoom_x,style.zoom_x)
    return transform.map(letters),transform.map(backing)


def draw(painter,project,caption,frame):
    style=project.caption_style(caption); w=project.settings.width; h=project.settings.height
    letters,backing=paths(caption.text,style,w,h)
    transform=QTransform(); transform.translate(frame.left(),frame.top()); transform.scale(frame.width()/w,frame.height()/h)
    letters=transform.map(letters); backing=transform.map(backing)
    inherited_opacity=painter.opacity(); painter.save(); painter.setClipRect(frame,Qt.IntersectClip); painter.setOpacity(inherited_opacity*style.opacity/100)
    painter.fillPath(backing,QColor("#FFFFFF")); painter.fillPath(letters,QColor(style.color))
    from .emoji import draw as draw_emoji
    draw_emoji(painter,[(sequence,transform.mapRect(rect)) for sequence,rect in emoji_positions(caption.text,style,w,h)]); painter.restore()
    return backing.boundingRect()


def ass_path(path):
    """ASS vector drawing supports the same move/line/cubic primitives as Qt."""
    parts=[]; index=0
    while index<path.elementCount():
        element=path.elementAt(index)
        if element.isMoveTo():parts.append(f"m {element.x:.3f} {element.y:.3f}")
        elif element.isLineTo():parts.append(f"l {element.x:.3f} {element.y:.3f}")
        elif element.isCurveTo():
            b=path.elementAt(index+1); c=path.elementAt(index+2)
            parts.append(f"b {element.x:.3f} {element.y:.3f} {b.x:.3f} {b.y:.3f} {c.x:.3f} {c.y:.3f}"); index+=2
        index+=1
    return " ".join(parts)
