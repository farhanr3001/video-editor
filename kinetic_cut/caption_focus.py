"""Session-only caption review: audio transport, no video compositor/decoders."""
from .theme_widgets import set_ui_style
import copy
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtWidgets import QToolButton
from .icons import lucide_icon


class CaptionFocus(QObject):
    def __init__(self,window,button):
        super().__init__(window); self.w=window; self.button=button; self.active=False
        button.setCheckable(True); button.toggled.connect(self.set_active)
        self.buttons=[]
        for icon,label,callback in [('chevron-left','Previous caption',lambda:self.navigate(-1)),('chevron-right','Next caption',lambda:self.navigate(1)),('trash-2','Delete selected caption',self.delete)]:
            control=QToolButton(window.preview); control.setIcon(lucide_icon(icon)); control.setToolTip(label); control.setFixedSize(36,36); control.clicked.connect(callback); control.hide(); self.buttons.append(control)
            if control.icon().isNull():control.setText('‹' if icon=='chevron-left' else '›')
        window.preview.installEventFilter(self)
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Resize:self.layout()
        return super().eventFilter(watched,event)
    def layout(self):
        v=self.w.preview; r=v.composition_rect(); y=round(r.center().y()-18)
        self.buttons[0].move(max(2,round(r.left()-48)),max(2,y))
        self.buttons[1].move(min(v.width()-38,round(r.right()+12)),max(2,y))
        self.buttons[2].move(min(v.width()-38,round(r.right()+12)),max(2,min(v.height()-38,round(r.bottom()-48))))
    def set_active(self,enabled):
        enabled=bool(enabled) and getattr(self.w,'current_page',0)==0
        if self.active==enabled:return
        self.active=enabled; v=self.w.preview; v.caption_focus=enabled
        self.button.setText('Return to Video' if enabled else 'Caption Focus')
        self.button.setToolTip('Caption Focus is on — click to restore video playback' if enabled else 'Edit captions with audio only')
        set_ui_style(self.button, 'QPushButton { border-bottom: 2px solid @accent; color: @danger; }' if enabled else '')
        for name in ('preview_quality','compounds'):
            controller=getattr(self.w,name,None)
            if controller:
                if enabled:controller.cancel()
                elif name=='compounds':controller.request_caches()
                else:controller.request()
        if enabled:
            self.saved_view=(v.view_zoom,copy.copy(v.view_pan)); v.reset_view()
        elif hasattr(self,'saved_view'):v.view_zoom,v.view_pan=self.saved_view
        for control in self.buttons:control.setVisible(enabled)
        self.layout()
        if hasattr(self.w,'transport'):
            self.w.transport.sync()
            if enabled and self.w.timeline.selected_caption:self.selected(self.w.timeline.selected_caption)
        v.update()
    def selected(self,id):
        if not self.active:return
        caption=next((c for c in self.w.project.captions if c.id==id),None)
        if caption:self.w.seek(caption.start)
    def navigate(self,direction):
        captions=sorted(self.w.project.captions,key=lambda c:(c.start,c.end,c.id))
        if not captions:return
        index=next((n for n,c in enumerate(captions) if c.id==self.w.timeline.selected_caption),-1 if direction>0 else 0)
        caption=captions[(index+direction)%len(captions)]
        self.w.timeline.select_captions({caption.id},caption.id)
    def delete(self):
        if not self.active or not self.w.timeline.selected_caption:return
        id=self.w.timeline.selected_caption
        self.w.timeline.select_captions({id},id); self.w.timeline.delete_caption()


def paint(view,painter,frame_rect):
    """Early compositor exit: never enumerate media, load images or run effects."""
    from .visuals import draw_caption
    project=view.project; view.text_rects={}
    if not project or not project.track_states.get('subtitle_1',{}).get('visible',True):return
    owner=view.window(); playing=bool(getattr(getattr(owner,'transport',None),'playing',False))
    selected=next((c for c in project.captions if c.id==view.selected_caption_id),None)
    captions=[selected] if selected and not playing else [c for c in project.captions if c.start<=project.playhead<c.end]
    for caption in captions:
        shown=caption
        if not playing:
            shown=copy.copy(caption); shown.style=copy.copy(project.caption_style(caption)); shown.customize=True
            # Paused review shows complete text even at a fade/reveal's onset.
            if shown.style.animation!='word highlight 2':shown.style.animation='none'
        painter.save(); painter.setClipRect(frame_rect,Qt.IntersectClip)
        bounds=draw_caption(painter,project,shown,frame_rect); painter.restore()
        view.text_rects[('caption',caption.id)]=bounds
        if not playing and view.transform_controls_visible and caption.id==view.selected_caption_id:view._draw_text_box(painter,bounds)
