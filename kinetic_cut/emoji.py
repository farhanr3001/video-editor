"""Offline Unicode 17 picker and Google Noto colour emoji rendering."""
import io
import threading
from functools import lru_cache
from PySide6.QtCore import Qt,QPointF,QRectF,QSize,QTimer,Signal,QEvent
from PySide6.QtGui import QImage,QPixmap,QIcon,QPainterPath,QFontMetricsF,QPainter,QColor,QPen,QFont,QFontDatabase,QGuiApplication,QSyntaxHighlighter,QTextCharFormat,QTextCursor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLineEdit,QComboBox,QListWidget,QListWidgetItem,QPlainTextEdit,QToolButton,QStyledItemDelegate,QLabel
from .icons import resource_path,lucide_icon

_lock=threading.RLock()


@lru_cache(maxsize=1)
def catalogue():
    entries=[]; aliases={}; group=""
    for line in resource_path("assets","emoji","emoji-test.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("# group:"):group=line.split(":",1)[1].strip()
        if not line or line.startswith("#") or ";" not in line:continue
        code,status=line.split(";",1); status,comment=status.split("#",1); status=status.strip()
        sequence="".join(chr(int(value,16)) for value in code.split()); details=comment.strip().split(" ",2)
        name=details[-1]; aliases[sequence]=sequence
        if status in {"fully-qualified","component"}:entries.append((sequence,name,group))
    return entries,aliases


@lru_cache(maxsize=1)
def trie():
    root={}
    for sequence in catalogue()[1]:
        node=root
        for char in sequence:node=node.setdefault(char,{})
        node[None]=sequence
    return root


@lru_cache(maxsize=512)
def segments(text):
    result=[]; plain=""; index=0; root=trie()
    while index<len(text):
        node=root; end=index; match=None
        while end<len(text) and text[end] in node:
            node=node[text[end]]; end+=1
            if None in node:match=end
        if match is not None:
            if plain:result.append((plain,False)); plain=""
            result.append((text[index:match],True)); index=match
        else:plain+=text[index]; index+=1
    if plain:result.append((plain,False))
    return result


def contains_emoji(text):return any(is_emoji for _,is_emoji in segments(text))


@lru_cache(maxsize=1)
def fonts():
    import uharfbuzz as hb
    from fontTools.ttLib import TTFont
    path=resource_path("assets","emoji","NotoColorEmoji.ttf")
    return hb.Font(hb.Face(path.read_bytes())),TTFont(path)


@lru_cache(maxsize=512)
def bitmap(sequence):
    import uharfbuzz as hb
    from PIL import Image
    with _lock:
        font,tt=fonts(); buffer=hb.Buffer(); buffer.add_str(sequence); buffer.guess_segment_properties(); hb.shape(font,buffer)
        glyphs=[tt.getGlyphName(info.codepoint) for info in buffer.glyph_infos if info.codepoint]
        images=[]
        for glyph in glyphs:
            data=tt["CBDT"].strikeData[0].get(glyph)
            if data and hasattr(data,"imageData"):images.append(Image.open(io.BytesIO(data.imageData)).convert("RGBA"))
        if not images:raise ValueError("No emoji artwork for "+repr(sequence))
        canvas=Image.new("RGBA",(sum(image.width for image in images),max(image.height for image in images)))
        x=0
        for image in images:canvas.alpha_composite(image,(x,0)); x+=image.width
        # A bounded palette keeps vector subtitle exports compact. The same
        # pixels are used by the picker, preview and export.
        canvas.thumbnail((128,128),Image.Resampling.LANCZOS)
        return canvas.quantize(colors=128,method=Image.Quantize.FASTOCTREE).convert("RGBA")


@lru_cache(maxsize=512)
def image(sequence):
    pixels=bitmap(sequence); return QImage(pixels.tobytes(),pixels.width,pixels.height,QImage.Format_RGBA8888).copy()


def measure(text,font):
    metrics=QFontMetricsF(font); size=font.pixelSize()
    return sum(size if emoji else metrics.horizontalAdvance(value) for value,emoji in segments(text))


def text_path(text,font,baseline):
    path=QPainterPath(); emojis=[]; x=baseline.x(); size=font.pixelSize(); metrics=QFontMetricsF(font)
    for value,is_emoji in segments(text):
        if is_emoji:emojis.append((value,QRectF(x,baseline.y()-size*.85,size,size))); x+=size
        else:path.addText(QPointF(x,baseline.y()),font,value); x+=metrics.horizontalAdvance(value)
    return path,emojis


def draw(painter,emojis):
    painter.save(); painter.setRenderHint(QPainter.SmoothPixmapTransform)
    for sequence,rect in emojis:painter.drawImage(rect,image(sequence))
    painter.restore()


@lru_cache(maxsize=256)
def vector_art(sequence):
    """Merge identical pixel runs vertically into compact coloured ASS shapes."""
    pixels=bitmap(sequence); w,h=pixels.size; data=pixels.load(); completed=[]; active={}
    for y in range(h):
        runs={}; x=0
        while x<w:
            color=data[x,y]; start=x; x+=1
            while x<w and data[x,y]==color:x+=1
            if color[3]:runs[(start,x,color)]=True
        for key,start_y in list(active.items()):
            if key not in runs:completed.append((key,start_y,y)); del active[key]
        for key in runs:active.setdefault(key,y)
    completed.extend((key,start_y,h) for key,start_y in active.items())
    groups={}
    for (left,right,color),top,bottom in completed:
        path=groups.setdefault(color,QPainterPath()); path.setFillRule(Qt.WindingFill); path.addRect(QRectF(left/w,top/h,(right-left)/w,(bottom-top)/h))
    return groups


def ass_events(emojis,start,end,style_name,opacity=100,animation="none",layer=3,origin=None):
    from .exporter import _ass_color,_ass_time
    from .headline import ass_path
    from PySide6.QtGui import QTransform
    result=[]
    for sequence,rect in emojis:
        for color,path in vector_art(sequence).items():
            transform=QTransform(); transform.scale(rect.width(),rect.height()); shape=transform.map(path)
            bounds=shape.boundingRect(); shape.translate(-bounds.left(),-bounds.top())
            alpha=round(255-color[3]*opacity/100); rgb="#%02x%02x%02x"%color[:3]
            left=rect.left()+bounds.left(); top=rect.top()+bounds.top()
            common=f"\\an7\\p1\\bord0\\shad0\\1c{_ass_color(rgb)}\\alpha&H{alpha:02X}&"
            phases=[(0,end-start,1.,1.)]
            if animation=="pop":phases=[(0,min(.13,end-start),.72,1.08),(.13,min(.22,end-start),1.08,1.),(.22,end-start,1.,1.)]
            if animation=="punch":phases=[(0,min(.10,end-start),.55,1.15),(.10,min(.22,end-start),1.15,1.),(.22,end-start,1.,1.)]
            for a,b,first,last in phases:
                if b<=a:continue
                ox,oy=origin or (rect.center().x(),rect.center().y())
                x1=ox+(left-ox)*first; y1=oy+(top-oy)*first; x2=ox+(left-ox)*last; y2=oy+(top-oy)*last
                tags=common+f"\\fscx{first*100:g}\\fscy{first*100:g}"
                if first==last:tags+=f"\\pos({x1:.3f},{y1:.3f})"
                else:tags+=f"\\move({x1:.3f},{y1:.3f},{x2:.3f},{y2:.3f},0,{round((b-a)*1000)})\\t(0,{round((b-a)*1000)},\\fscx{last*100:g}\\fscy{last*100:g})"
                if animation=="fade":tags+=r"\fad(100,100)"
                result.append(f"Dialogue: {layer},{_ass_time(start+a)},{_ass_time(start+b)},{style_name},,0,0,0,,{{{tags}}}{ass_path(shape)}")
    return result


class EmojiDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return QSize(44,44)
    def paint(self,painter,option,index):
        from PySide6.QtWidgets import QStyle
        painter.save()
        if option.state&(QStyle.State_MouseOver|QStyle.State_Selected):painter.fillRect(option.rect,QColor("#465467"))
        sequence=index.data(Qt.UserRole); rect=QRectF(option.rect).adjusted(6,6,-6,-6)
        painter.setRenderHint(QPainter.SmoothPixmapTransform); painter.drawImage(rect,image(sequence)); painter.restore()


class EmojiPicker(QDialog):
    chosen=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("Emoji · Google Noto"); self.resize(430,460)
        root=QVBoxLayout(self); self.search=QLineEdit(); self.search.setPlaceholderText("Search all emoji, including skin tones…"); root.addWidget(self.search)
        self.categories=QComboBox(); self.categories.addItems(["All emoji"]+list(dict.fromkeys(group for _,_,group in catalogue()[0]))); root.addWidget(self.categories)
        self.grid=QListWidget(); self.grid.setViewMode(QListWidget.IconMode); self.grid.setResizeMode(QListWidget.Adjust); self.grid.setMovement(QListWidget.Static); self.grid.setGridSize(QSize(44,44)); self.grid.setMouseTracking(True); self.grid.setItemDelegate(EmojiDelegate(self.grid)); root.addWidget(self.grid)
        self.status=QLabel(); root.addWidget(self.status); self.search.textChanged.connect(self.refresh); self.categories.currentTextChanged.connect(self.refresh)
        self.grid.itemClicked.connect(self.choose); self.grid.itemActivated.connect(self.choose); self.refresh()
    def refresh(self):
        query=self.search.text().casefold().split(); category=self.categories.currentText(); self.grid.clear()
        for sequence,name,group in catalogue()[0]:
            if category!="All emoji" and category!=group:continue
            if not all(word in (name+" "+group+" "+sequence).casefold() for word in query):continue
            item=QListWidgetItem(); item.setData(Qt.UserRole,sequence); item.setToolTip(name); item.setData(Qt.AccessibleTextRole,name); self.grid.addItem(item)
        self.status.setText(f"{self.grid.count():,} emoji · Includes skin tones and joined sequences")
    def choose(self,item):self.chosen.emit(item.data(Qt.UserRole)); self.accept()


def editor_emoji_family():
    app=QGuiApplication.instance(); family=app.property("kineticEmojiFamily")
    if family is None:
        identifier=QFontDatabase.addApplicationFont(str(resource_path("assets","emoji","NotoColorEmoji.ttf")))
        families=QFontDatabase.applicationFontFamilies(identifier)
        family=families[0] if families else "Segoe UI Emoji"; app.setProperty("kineticEmojiFamily",family)
    return family


class EmojiHighlighter(QSyntaxHighlighter):
    """Colour glyph formatting without replacing the editable Unicode text."""
    def __init__(self,editor):
        self.editor=editor; self.family=editor_emoji_family(); super().__init__(editor.document())
    def highlightBlock(self,text):
        base=self.editor.font(); size=base.pixelSize() if base.pixelSize()>0 else round(base.pointSizeF()*self.editor.logicalDpiY()/72)
        font=QFont(self.family); font.setPixelSize(max(4,size)); metrics=QFontMetricsF(font); offset=0
        for value,is_emoji in segments(text):
            length=len(value.encode("utf-16-le"))//2
            if is_emoji:
                fmt=QTextCharFormat(); fmt.setFont(font)
                # Qt's Windows CBDT backend paints Noto but reports zero advance.
                # Absolute spacing supplies one advance per shaped grapheme,
                # including skin-tone and ZWJ sequences, without changing text.
                if metrics.horizontalAdvance(value)<=0:
                    fmt.setFontLetterSpacingType(QFont.AbsoluteSpacing); fmt.setFontLetterSpacing(size)
                self.setFormat(offset,length,fmt)
            offset+=length


class EmojiTextEdit(QPlainTextEdit):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.emoji_button=QToolButton(self); self.emoji_button.setIcon(lucide_icon("smile")); self.emoji_button.setToolTip("Insert emoji"); self.emoji_button.setAccessibleName("Insert emoji"); self.emoji_button.setFixedSize(26,26); self.emoji_button.clicked.connect(self.pick_emoji); self.setViewportMargins(0,0,0,28)
        self._emoji_highlighter=EmojiHighlighter(self)
        self.case_button=QToolButton(self); self.case_button.setText("Aa"); self.case_button.setFixedSize(26,26)
        self.case_button.setToolTip("Toggle all text UPPERCASE / lowercase"); self.case_button.setAccessibleName("Toggle text case")
        self.case_button.clicked.connect(self.toggle_case)
        self._suggestion=""
        self.cursorPositionChanged.connect(self._update_suggestion)
        self.textChanged.connect(self._update_suggestion)

    def _update_suggestion(self):
        if self.isReadOnly():
            if self._suggestion:self._suggestion=""; self.viewport().update()
            return
        cursor=self.textCursor()
        if cursor.hasSelection():
            if self._suggestion:self._suggestion=""; self.viewport().update()
            return
        pos=cursor.position(); text=self.toPlainText()
        if pos<len(text) and text[pos].isalnum():
            if self._suggestion:self._suggestion=""; self.viewport().update()
            return
        import re
        match=re.search(r'([A-Za-z]{2,})$',text[:pos])
        if not match:
            if self._suggestion:self._suggestion=""; self.viewport().update()
            return
        prefix=match.group(1)
        from .word_list import get_completion
        doc_words=[w for w in re.findall(r'[A-Za-z]{3,}',text) if w.lower()!=prefix.lower()]
        sug=get_completion(prefix,doc_words)
        if sug!=self._suggestion:
            self._suggestion=sug; self.viewport().update()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Tab and self._suggestion:
            cursor=self.textCursor(); cursor.insertText(self._suggestion); self.setTextCursor(cursor)
            self._suggestion=""; self.viewport().update(); event.accept(); return
        if event.key()==Qt.Key_Escape and self._suggestion:
            self._suggestion=""; self.viewport().update(); event.accept(); return
        super().keyPressEvent(event)
        self._update_suggestion()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self._suggestion and self.hasFocus():
            cursor=self.textCursor(); rect=self.cursorRect(cursor)
            p=QPainter(self.viewport()); p.setFont(self.font())
            p.setPen(QColor(140,148,160,180))  # Muted grey ghost text
            fm=p.fontMetrics(); baseline=rect.bottom()-fm.descent()
            p.drawText(rect.right(),baseline,self._suggestion); p.end()

    def focusOutEvent(self,event):
        super().focusOutEvent(event)
        if self._suggestion:self._suggestion=""; self.viewport().update()

    def toggle_case(self):
        if self.isReadOnly():return
        value=self.toPlainText(); cursor=self.textCursor(); cursor.beginEditBlock(); cursor.select(QTextCursor.Document)
        cursor.insertText(value.lower() if value.isupper() else value.upper()); cursor.endEditBlock(); self.setTextCursor(cursor); self.setFocus()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.ApplicationFontChange,QEvent.StyleChange) and hasattr(self,"_emoji_highlighter"):self._emoji_highlighter.rehighlight()
    def resizeEvent(self,event):
        super().resizeEvent(event); self.emoji_button.move(self.width()-self.emoji_button.width()-5,self.height()-self.emoji_button.height()-3)
        self.case_button.move(self.width()-57,self.height()-29)
    def pick_emoji(self):
        cursor=self.textCursor(); picker=EmojiPicker(self); self._picker=picker
        def insert(sequence):self.setTextCursor(cursor); self.insertPlainText(sequence); self.setFocus()
        picker.chosen.connect(insert); picker.open(); picker.search.setFocus()
