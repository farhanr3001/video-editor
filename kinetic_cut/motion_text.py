"""Stable text anchors, Unicode typewriter reveals and editable numeric counters."""
import math
from functools import lru_cache
from PySide6.QtCore import QPointF,QRectF,Qt,QTextBoundaryFinder
from PySide6.QtGui import QFont,QFontMetricsF,QPainterPath

@lru_cache(maxsize=64)
def graphemes(text):
    # Qt boundaries are UTF-16 offsets, not Python code-point indices.
    encoded=text.encode('utf-16-le'); finder=QTextBoundaryFinder(QTextBoundaryFinder.Grapheme,text)
    result=[]; previous=0
    while True:
        end=finder.toNextBoundary()
        if end<0:break
        result.append(encoded[previous*2:end*2].decode('utf-16-le')); previous=end
    return tuple(result)

def revealed_text(node,t):
    from .motion import curve
    letters=graphemes(node.get('text','')); local=max(0,t-node.get('start',0))
    if 'reveal' in node or node.get('keyframes',{}).get('reveal'):
        amount=max(0,min(1,curve(node,'reveal',t))); count=min(len(letters),math.floor(amount*len(letters)+1e-7))
    else:count=min(len(letters),math.floor(local/max(.001,node.get('stagger',.06))+1e-7))
    return ''.join(letters[:count])

def counter_text(node,t):
    from .motion import curve
    number=curve(node,'number',t); places=int(node.get('number_decimals',0))
    # Avoid '-0' during an eased transition across zero.
    if abs(number)<.5*10**(-places):number=0
    body=format(number,(',' if node.get('number_grouping',True) else '')+'.'+str(places)+'f')
    if places and node.get('number_trim_zeros',False):body=body.rstrip('0').rstrip('.')
    return node.get('number_prefix','')+body+node.get('number_suffix','')

@lru_cache(maxsize=32)
def _rolling_layout(text,font_name,size,bold,tracking,alignment):
    font=QFont(font_name); font.setPixelSize(max(1,round(size))); font.setBold(bold); font.setLetterSpacing(QFont.AbsoluteSpacing,tracking)
    metrics=QFontMetricsF(font); lines=text.split('\n'); height=metrics.height(); baseline=metrics.ascent()-len(lines)*height/2
    fixed=QPainterPath(); cells=[]; digits=[]
    for digit in range(10):
        path=QPainterPath(); path.addText(QPointF(0,0),font,str(digit)); digits.append(path)
    for row,line in enumerate(lines):
        width=metrics.horizontalAdvance(line); left=0 if alignment=='left' else -width if alignment=='right' else -width/2
        for index,char in enumerate(line):
            x=left+metrics.horizontalAdvance(line[:index]); y=baseline+row*height
            if char.isascii() and char.isdigit():cells.append((int(char),x,y,metrics.horizontalAdvance(char)))
            else:fixed.addText(QPointF(x,y),font,char)
    return fixed,tuple(cells),tuple(digits),height,metrics.ascent()

def draw_rolling(painter,node,t):
    """Two glyphs per digit, rather than dozens of scene layers per reel."""
    from .motion import curve,text_parts
    from .easing import ease
    text=node.get('text',''); size=curve(node,'font_size',t)
    local=max(0,t-node.get('start',0)); duration=max(.001,node.get('entry_duration',.9))
    if local>=duration:
        for path in text_parts(text,node.get('font','Arial'),size,bool(node.get('bold',True)),'none',curve(node,'tracking',t),node.get('text_align','center')):painter.drawPath(path)
        return
    fixed,cells,digits,height,ascent=_rolling_layout(text,node.get('font','Arial'),size,bool(node.get('bold',True)),curve(node,'tracking',t),node.get('text_align','center'))
    painter.drawPath(fixed)
    progress=ease(min(1,local/duration),node.get('entry_easing','Ease Out'),node.get('entry_bezier'))
    for digit,x,y,width in cells:
        travel=(10+digit)*progress; current=math.floor(travel); fraction=travel-current
        painter.save(); painter.setClipRect(QRectF(x-1,y-ascent,width+2,height),Qt.IntersectClip)
        painter.translate(x,y-fraction*height); painter.drawPath(digits[current%10]); painter.translate(0,height); painter.drawPath(digits[(current+1)%10]); painter.restore()

def draw_typewriter(painter,node,t):
    from .motion import curve
    size=curve(node,'font_size',t); font=QFont(node.get('font','Arial')); font.setPixelSize(max(1,round(size))); font.setBold(bool(node.get('bold',True))); font.setLetterSpacing(QFont.AbsoluteSpacing,curve(node,'tracking',t))
    metrics=QFontMetricsF(font); complete=node.get('text','').split('\n'); visible=revealed_text(node,t).split('\n')
    baseline=metrics.ascent()-len(complete)*metrics.height()/2; alignment=node.get('text_align','center'); caret=QPointF()
    for row,line in enumerate(visible):
        width=metrics.horizontalAdvance(complete[row]); x=0 if alignment=='left' else -width if alignment=='right' else -width/2
        y=baseline+row*metrics.height(); path=QPainterPath(); path.addText(QPointF(x,y),font,line); painter.drawPath(path)
        caret=QPointF(x+metrics.horizontalAdvance(line)+max(2,size*.05),y)
    local=max(0,t-node.get('start',0)); period=node.get('caret_period',.8)
    if node.get('caret',False) and local%period<period*.5:
        path=QPainterPath(); path.addRect(caret.x(),caret.y()-metrics.ascent()*.9,max(1,size*.045),metrics.ascent())
        painter.drawPath(path)
