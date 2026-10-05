"""Stable text anchors, Unicode typewriter reveals and editable numeric counters."""
import math
from functools import lru_cache
from PySide6.QtCore import QPointF,QTextBoundaryFinder
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
    return node.get('number_prefix','')+body+node.get('number_suffix','')

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
