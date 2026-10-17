"""Single-flight, disposable timeline raster helper; no project or media writes."""
from .preview_process import RendererProcess,pack,unpack


def child(connection,scale):
    import os
    # Keep the native Windows font database in desktop runs. The offscreen
    # plugin cannot resolve system fonts there and renders missing-glyph boxes.
    os.environ.setdefault('QT_QPA_PLATFORM','windows' if os.name=='nt' else 'offscreen')
    os.environ['QT_SCALE_FACTOR']=str(scale)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont,QPixmap
    from PySide6.QtWidgets import QApplication
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Caption
    from .timeline import TimelineWidget
    from .transitions import Transition
    app=QApplication([])
    timeline=TimelineWidget();timeline.setAttribute(Qt.WA_DontShowOnScreen);version=None
    try:
        while True:
            try:payload=connection.recv()
            except EOFError:break
            try:
                source,state=payload
                if source is not None:
                    project=Project(settings=ProjectSettings(**source['settings']),
                        video_tracks=source['video_tracks'],audio_tracks=source['audio_tracks'],
                        track_states=source['track_states'],track_names=source['track_names'],
                        media=[MediaItem(**m) for m in source['media']],
                        timeline=[TimelineItem(**i) for i in source['timeline']],
                        captions=[Caption(**c) for c in source['captions']],
                        transitions=[Transition(**t) for t in source['transitions']])
                    timeline.set_project(project); timeline.waveforms=source['waveforms']
                    timeline.thumbnails={k:QPixmap.fromImage(unpack(v)) for k,v in source['thumbnails'].items()}
                    timeline.setStyleSheet(source['stylesheet'])
                    app.setStyleSheet(source['application_stylesheet'])
                    font=QFont();font.fromString(source['font']);timeline.setFont(font)
                    version=source['version']
                assert version==state['version'],'Timeline source revision changed'
                app.setProperty('kineticTheme',state['palette']['id'])
                timeline._palette=lambda:state['palette']
                timeline.resize(*state['size']);timeline.show();app.processEvents()
                wanted=state['viewport']
                # Styles affect the scroll-area frame, not the requested raster.
                for _ in range(2):
                    delta=(wanted[0]-timeline.viewport().width(),wanted[1]-timeline.viewport().height())
                    if delta==(0,0):break
                    timeline.resize(timeline.width()+delta[0],timeline.height()+delta[1]);app.processEvents()
                timeline.section_track_heights=state['section_track_heights']
                for name in ('track_height','video_track_height','audio_track_height','subtitle_height','audio_extent','subtitle_extent'):
                    setattr(timeline,name,state[name])
                timeline.selected_ids=set(state['selected_ids']);timeline.selected_id=state['selected_id']
                timeline.selected_caption_ids=set(state['selected_caption_ids']);timeline.selected_caption=state['selected_caption']
                timeline.selected_transition_id=state['selected_transition_id'];timeline.retime_ids=set(state['retime_ids'])
                timeline.read_only=state['read_only'];timeline.hover_id=state['hover_id'];timeline.tool=state['tool']
                timeline.waveform_pending=set(state['waveform_pending']);timeline.waveform_failures=set(state['waveform_failures'])
                timeline.pixels_per_second=state['zoom'];timeline._navigation_end=state['navigation_end'];timeline._range()
                for section in ('video','audio','subtitle'):getattr(timeline,section+'_scroll').setValue(state[section+'_scroll'])
                timeline.horizontalScrollBar().setValue(state['offset'])
                timeline._navigation_pending=True;timeline._timeline_backing=None;timeline._view_rasters.clear()
                timeline.viewport().repaint()
                # Overscanned bases exclude dynamic clocks/meters and FX badges.
                assert timeline._view_rasters,'Timeline helper could not render navigation raster'
                image=next(reversed(timeline._view_rasters.values())).toImage()
                connection.send(('ok',pack(image)))
            except Exception:
                import traceback
                connection.send(('error',traceback.format_exc()))
    finally:
        timeline.close();connection.close();app.quit()


class TimelineRenderer(RendererProcess):
    def __init__(self):
        super().__init__();self.shared=None;self.version=None
    def render_timeline(self,source,state):
        with self.lock:
            if self.closed:raise InterruptedError('Timeline renderer closed')
            if self.process is None:
                import multiprocessing
                from .process import install_desktop_process_policy
                install_desktop_process_policy()
                context=multiprocessing.get_context('spawn');parent,remote=context.Pipe()
                self.connection=parent;self.process=context.Process(target=child,args=(remote,state['scale']),daemon=True,name='KineticCut-timeline')
                self.process.start();remote.close()
            if self.closed:
                if self.process.is_alive():self.process.terminate()
                self.process.join(2);raise InterruptedError('Timeline renderer closed')
            self.connection.send((source if self.version!=state['version'] else None,state))
            if not self.connection.poll(8):raise TimeoutError('Timeline raster helper did not respond')
            result=self.connection.recv()
            if result[0]!='ok':raise RuntimeError(result[1])
            self.version=state['version'];return unpack(result[1])


def snapshot(timeline):
    """Copy only timeline display data. Crop/transform/export graphs are irrelevant."""
    import copy
    from dataclasses import asdict
    from PySide6.QtWidgets import QApplication
    project=timeline.project
    fields=('id','media_id','track','start','duration','in_point','speed','role','graphic_type','title_text',
            'gain_db','fade_in','fade_out','group_id','link_id','effects','source_mismatch','source_requirement','muted')
    return dict(version=timeline._paint_generation,settings=asdict(project.settings),
        video_tracks=list(project.video_tracks),audio_tracks=list(project.audio_tracks),
        track_states=copy.deepcopy(project.track_states),track_names=dict(project.track_names),
        media=[asdict(m) for m in project.media],
        timeline=[{k:copy.deepcopy(getattr(i,k)) for k in fields} for i in project.timeline],
        captions=[dict(id=c.id,start=c.start,end=c.end,text=c.text) for c in project.captions],
        transitions=[asdict(t) for t in project.transitions],waveforms=dict(timeline.waveforms),
        thumbnails={k:pack(v.toImage()) for k,v in timeline.thumbnails.items()},
        stylesheet=timeline.window().styleSheet(),application_stylesheet=QApplication.instance().styleSheet(),
        font=timeline.font().toString())
