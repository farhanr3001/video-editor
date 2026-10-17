import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QColor
from kinetic_cut.model import Project,MediaItem,TimelineItem,Crop
from kinetic_cut import enhance


class EnhanceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name)
        self.cache=patch('kinetic_cut.config.CACHE_DIR',self.root/'cache');self.cache.start()
        self.source=self.root/'source.mp4';self.source.write_bytes(b'source')
        self.media=MediaItem('m',str(self.source),'video','source',2,160,120);self.media.fps=10
        self.item=TimelineItem('i','m','video_1',0,2);self.item.effects=[enhance.default_effect()]
        self.project=Project(media=[self.media],timeline=[self.item])
    def tearDown(self):
        enhance._images.clear();self.cache.stop();self.folder.cleanup()
    def ready_frames(self):
        root=enhance.cache_path(self.project,self.media,self.item,0);(root/'frames').mkdir(parents=True)
        for n,color in enumerate(('#113355','#7799bb')):
            image=QImage(160,120,QImage.Format_RGB32);image.fill(QColor(color));image.save(str(root/'frames'/f'{n:08d}.png'))
        (root/'info.json').write_text(json.dumps(dict(key=root.name,family=enhance.signature(self.media,self.item,0,10,False),source_start=self.item.in_point,frames=2,fps=10,backend='test')))
        return root
    def test_parameters_are_bounded_and_zero_bypasses(self):
        effect=enhance.default_effect();effect.update(denoise=float('nan'),mix=-10,detail_recovery=500,upscale=8,quality_mode='invalid')
        values=enhance.parameters(effect);self.assertEqual(values['denoise'],35);self.assertEqual(values['mix'],0);self.assertEqual(values['detail_recovery'],100);self.assertEqual(values['upscale'],1);self.assertEqual(values['quality_mode'],'Balanced')
        self.item.effects=[effect];self.assertFalse(enhance.active(self.item))
    def test_signature_preserves_transform_but_invalidates_crop_source_and_order(self):
        key=lambda:enhance.cache_path(self.project,self.media,self.item,len(self.item.effects)-1)
        original=key();self.item.start=20;self.item.transform.scale=3;self.item.transform.rotation=43;self.item.opacity=30
        self.assertEqual(original,key())
        self.item.effects[0]['denoise']=71;self.assertEqual(original,key())
        self.item.crop=Crop(0,0,.5,.5);self.assertNotEqual(original,key());self.item.crop=Crop()
        self.item.effects.insert(0,dict(name='Gaussian Blur',horizontal=8,vertical=8));self.assertNotEqual(original,key())
        self.item.effects.pop(0);self.item.effects[0]['denoise']=90;self.assertNotEqual(original,key())
        self.item.effects[0]['denoise']=71;self.source.write_bytes(b'new source');self.assertNotEqual(original,key())
    def test_exact_cached_frame_and_missing_frame_are_not_stale(self):
        self.item.duration=.2;root=self.ready_frames();self.assertEqual(enhance.status(self.project,self.item),'')
        first=enhance.cached_frame(self.project,self.media,self.item,0,0);last=enhance.cached_frame(self.project,self.media,self.item,0,.1)
        self.assertEqual(first.pixelColor(5,5),QColor('#113355'));self.assertEqual(last.pixelColor(5,5),QColor('#7799bb'))
        (root/'frames/00000001.png').unlink();self.assertTrue(enhance.cached_frame(self.project,self.media,self.item,0,.1).isNull());self.assertTrue(enhance.status(self.project,self.item))
    def test_preview_uses_baked_pixels_once_and_preserves_source(self):
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        self.ready_frames();source=QImage(160,120,QImage.Format_RGB32);source.fill(QColor('red'))
        self.item.effects.append(dict(name='Channel Swap',enabled=True,amount=100))
        result=enhance.render_frame(self.project,self.item,source,0)
        self.assertEqual(result.pixelColor(5,5),QColor('#553311'));self.assertEqual(source.pixelColor(5,5),QColor('red'))
        output=prepare_layer_image(RasterContext(self.project,False,1),self.item,source,QRectF(0,0,160,120),QRectF(0,0,1080,1920))
        self.assertEqual(output.pixelColor(5,5),result.pixelColor(5,5))

    def test_ai_only_is_rendered_by_the_actual_canvas(self):
        from kinetic_cut.widgets import PreviewCanvas
        from PySide6.QtGui import QPainter
        self.ready_frames();canvas=PreviewCanvas();canvas.set_project(self.project)
        source=QImage(160,120,QImage.Format_RGB32);source.fill(QColor('red'))
        output=QImage(160,120,QImage.Format_RGB32);output.fill(QColor('black'));painter=QPainter(output)
        rect=QRectF(0,0,160,120)
        canvas._draw_layer_item(painter,self.item,source,rect,rect);painter.end()
        self.assertEqual(output.pixelColor(80,60),QColor('#113355'))
        canvas.composition_cache.close();canvas.close();canvas.deleteLater()

    def test_legacy_prepared_ranges_remain_visible_and_fast_ranges_take_precedence(self):
        root=self.ready_frames();record=json.loads((root/'info.json').read_text())
        key=enhance.signature(self.media,self.item,0,10,schema=4);legacy=root.with_name(key);root.rename(legacy)
        record.update(key=key,family=enhance.signature(self.media,self.item,0,10,False,schema=4))
        (legacy/'info.json').write_text(json.dumps(record));enhance._range_indexes.clear()
        self.assertEqual(enhance.cached_frame(self.project,self.media,self.item,0,0).pixelColor(5,5),QColor('#113355'))
        fast=self.ready_frames();record=json.loads((fast/'info.json').read_text());record['engine']='compact-v1'
        (fast/'info.json').write_text(json.dumps(record));enhance._range_indexes.clear()
        self.assertEqual(enhance.range_at(self.project,self.media,self.item,0,0)['root'],str(fast))
    def test_missing_cache_never_downloads_and_strict_export_rejects_it(self):
        source=QImage(160,120,QImage.Format_RGB32);source.fill(QColor('red'))
        with patch('kinetic_cut.enhance_component.install') as install:
            self.assertEqual(enhance.render_frame(self.project,self.item,source,0),source)
            with self.assertRaisesRegex(RuntimeError,'missing'):enhance.render_frame(self.project,self.item,source,0,strict=True)
            install.assert_not_called()
    def test_disabled_and_mix_zero_retain_existing_preview_path(self):
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        source=QImage(160,120,QImage.Format_RGB32);source.fill(QColor('red'))
        for change in ({'enabled':False},{'mix':0},{'enhancement_strength':0}):
            self.item.effects=[dict(enhance.default_effect(),**change)]
            result=prepare_layer_image(RasterContext(self.project,False,1),self.item,source,QRectF(0,0,160,120),QRectF(0,0,1080,1920))
            self.assertEqual(result,source)

    def test_enhance_plus_blur_pan_reuses_pixels_but_edits_and_cache_removal_invalidate(self):
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        self.ready_frames();self.item.effects.append(dict(name='Gaussian Blur',horizontal=12,vertical=12))
        source=QImage(160,120,QImage.Format_RGB32);source.fill(QColor('red'))
        context=RasterContext(self.project,False,1);rect=QRectF(0,0,160,120)
        with patch('kinetic_cut.enhance.render_frame',wraps=enhance.render_frame) as render:
            first=prepare_layer_image(context,self.item,source,rect,rect)
            for n in range(8):
                moved=rect.translated(n*3.125+.1,n*1.75+.3)
                self.assertEqual(prepare_layer_image(context,self.item,source,moved,moved),first)
            self.assertEqual(render.call_count,1)
            self.item.effects[-1]['horizontal']=19
            prepare_layer_image(context,self.item,source,rect,rect);self.assertEqual(render.call_count,2)
            record=enhance.range_at(self.project,self.media,self.item,0,0)
            (Path(record['root'])/'info.json').unlink()
            prepare_layer_image(context,self.item,source,rect,rect);self.assertEqual(render.call_count,3)
    def test_extend_and_retrim_reuse_prepared_frames_without_clamping_tail(self):
        self.item.in_point=1.;self.item.duration=.2;self.ready_frames()
        self.item.in_point=.9;self.item.duration=.5
        original=QImage(160,120,QImage.Format_RGB32);original.fill(QColor('red'))
        self.assertEqual(enhance.render_frame(self.project,self.item,original,1.1).pixelColor(5,5),QColor('#7799bb'))
        for at in (.9,1.3):
            self.assertTrue(enhance.cached_frame(self.project,self.media,self.item,0,at).isNull())
            self.assertEqual(enhance.render_frame(self.project,self.item,original,at,strict=True),original)
        self.assertIn('Newly exposed',enhance.status(self.project,self.item))
        self.item.in_point=1.1;self.item.duration=.1
        self.assertIsNotNone(enhance.info(self.project,self.media,self.item,0))
        self.assertEqual(enhance.status(self.project,self.item),'')
    def test_mix_and_strength_update_without_another_neural_pass(self):
        self.item.duration=.2;root=self.ready_frames();(root/'original').mkdir()
        raw=QImage(160,120,QImage.Format_RGB32);raw.fill(QColor('black'))
        for n in (0,1):raw.save(str(root/'original'/f'{n:08d}.png'))
        metadata=json.loads((root/'info.json').read_text());metadata['original_frames']=True;(root/'info.json').write_text(json.dumps(metadata));enhance._range_indexes.clear()
        key=enhance.cache_path(self.project,self.media,self.item,0)
        self.item.effects[0].update(mix=50,enhancement_strength=100)
        self.assertEqual(enhance.cache_path(self.project,self.media,self.item,0),key)
        image=enhance.cached_frame(self.project,self.media,self.item,0,0)
        self.assertEqual(image.pixelColor(0,0).red(),8);self.assertEqual(image.pixelColor(0,0).green(),26)
        self.item.effects[0].update(mix=100,enhancement_strength=100)
        self.assertEqual(enhance.cached_frame(self.project,self.media,self.item,0,0).pixelColor(0,0),QColor('#113355'))
    def test_effect_catalog_compatibility_and_save_roundtrip(self):
        from kinetic_cut.effects import CATALOG,compatible
        from kinetic_cut.feature_packs import effect_component
        self.assertIn(enhance.NAME,CATALOG['Quality Enhancer']);self.assertEqual(effect_component(enhance.NAME),'enhance')
        self.assertTrue(compatible(enhance.NAME,self.item,self.project));self.project.track_states['video_1']={'locked':True};self.assertFalse(compatible(enhance.NAME,self.item,self.project))
        self.project.track_states.clear();self.media.kind='image';self.assertFalse(compatible(enhance.NAME,self.item,self.project));self.media.kind='video'
        self.item.effects.append(copy.deepcopy(self.item.effects[0]));path=self.root/'saved.kcut';self.project.save(path);loaded=Project.load(path)
        self.assertEqual(loaded.timeline[0].effects,self.item.effects)
    def test_export_requires_prepared_enhancement_and_skips_double_effects(self):
        from kinetic_cut.exporter import build_command,PRESETS
        preset=next(iter(PRESETS.values()))
        self.item.effects.append(dict(name='Gaussian Blur',enabled=True,horizontal=4,vertical=4));self.item.grayscale=True
        with self.assertRaisesRegex(ValueError,'AI Enhance'):build_command(self.project,'out.mp4',preset)
        command=build_command(self.project,'out.mp4',preset,prepared={self.item.id:'enhanced.mkv'})
        graph=command[command.index('-filter_complex')+1]
        self.assertNotIn('gblur=',graph);self.assertNotIn('hue=s=0',graph);self.assertIn('enhanced.mkv',command)


class EnhanceUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from kinetic_cut.ui import MainWindow
        cls.app=QApplication.instance() or QApplication([]);cls.w=MainWindow();cls.w.autosave_timer.stop()
    @classmethod
    def tearDownClass(cls):
        from PySide6.QtCore import QEvent
        from PySide6.QtTest import QTest
        import time
        deadline=time.monotonic()+10
        while cls.w._workers and time.monotonic()<deadline:QTest.qWait(10)
        cls.w.close();cls.w.deleteLater();cls.app.sendPostedEvents(None,QEvent.DeferredDelete);cls.app.processEvents()
    def test_multiselect_apply_properties_undo_and_remove(self):
        from kinetic_cut.enhance_ui import apply
        media=MediaItem('m','fixture.mp4','video','fixture',2,160,120)
        a=TimelineItem('a','m','video_1',0,1);b=TimelineItem('b','m','video_1',1,1)
        a.crop=Crop(.1,.2,.5,.5);a.transform.scale=2;b.transform.rotation=24
        self.w.set_project(Project(media=[media],timeline=[a,b]));self.w.timeline.select_ids({'a','b'},'a')
        before=copy.deepcopy(self.w.project.to_dict()['timeline'])
        with patch('kinetic_cut.enhance_component.ready',return_value=True),patch('kinetic_cut.enhance_ui.confirm_space',return_value=True),patch('kinetic_cut.enhance_ui.begin') as begin:
            apply(self.w);self.assertEqual(len(begin.call_args.args[1]),2)
        for item,old in zip(self.w.project.timeline,before):
            now=copy.deepcopy(vars(item));self.assertEqual(item.effects[0]['name'],enhance.NAME)
            self.assertEqual(vars(item.crop),old['crop']);self.assertEqual(vars(item.transform),old['transform']);self.assertEqual(item.start,old['start'])
        panel=self.w.inspector.enhance_panel;panel.edit('denoise',72)
        self.assertTrue(all(i.effects[0]['denoise']==72 for i in self.w.project.timeline))
        self.w.undo();self.assertTrue(all(i.effects[0]['denoise']==71 for i in self.w.project.timeline))
        self.w.redo();self.assertTrue(all(i.effects[0]['denoise']==72 for i in self.w.project.timeline))
        self.w.inspector.remove_effect();self.assertTrue(all(not i.effects for i in self.w.project.timeline))
    def test_storage_cancel_never_mutates_or_downloads(self):
        from kinetic_cut.enhance_ui import apply
        media=MediaItem('m','fixture.mp4','video','fixture',2,160,120)
        self.w.set_project(Project(media=[media],timeline=[TimelineItem('a','m','video_1',0,1)]))
        self.w.timeline.select_ids({'a'},'a');before=copy.deepcopy(self.w.project.to_dict());history=len(self.w._history)
        with patch('kinetic_cut.enhance_ui.confirm_space',return_value=False),patch('kinetic_cut.enhance_component.ready') as ready,patch('kinetic_cut.enhance_ui.begin') as begin:
            apply(self.w);ready.assert_not_called();begin.assert_not_called()
        self.assertEqual(before,self.w.project.to_dict());self.assertEqual(history,len(self.w._history))
    def test_storage_confirmation_offline_source_is_safe(self):
        from kinetic_cut.enhance_ui import confirm_space
        from PySide6.QtWidgets import QMessageBox
        with patch('kinetic_cut.enhance.estimate_space',side_effect=FileNotFoundError()),patch.object(QMessageBox,'warning') as warning:
            self.assertFalse(confirm_space(self.w,[object()],True));warning.assert_called_once()
    def test_storage_confirmation_includes_budget_reminder_and_insufficient_space(self):
        from kinetic_cut.enhance_ui import confirm_space
        from PySide6.QtWidgets import QMessageBox
        plan=dict(cache_bytes=1024**3,peak_bytes=2*1024**3,details=[])
        boxes=[]
        def inspect(box):boxes.append((box.text(),box.informativeText(),box.standardButtons()));return QMessageBox.Ok
        with patch('kinetic_cut.enhance.estimate_space',return_value=plan),patch('shutil.disk_usage',return_value=type('Disk',(),dict(free=3*1024**3))()),patch.object(QMessageBox,'exec',inspect):
            self.assertTrue(confirm_space(self.w,[object()],True))
        self.assertIn('1.00 GiB',boxes[-1][1]);self.assertIn('After your final render',boxes[-1][1])
        with patch('kinetic_cut.enhance.estimate_space',return_value=plan),patch('shutil.disk_usage',return_value=type('Disk',(),dict(free=1))()),patch.object(QMessageBox,'exec',inspect):
            self.assertFalse(confirm_space(self.w,[object()],True))
        self.assertIn('Not enough space',boxes[-1][0]);self.assertEqual(boxes[-1][2],QMessageBox.Cancel)
    def test_download_backend_choice_never_starts_without_confirmation(self):
        from kinetic_cut.component_ui import InstallComponentDialog
        from PySide6.QtWidgets import QLabel
        with patch('kinetic_cut.enhance_component.default_acceleration',return_value='CUDA'),patch('kinetic_cut.enhance_component.install') as install:
            dialog=InstallComponentDialog(self.w,'enhance');self.assertTrue(dialog.cuda.isChecked())
            self.assertTrue(any('2.5 GB' in label.text() for label in dialog.findChildren(QLabel)))
            dialog.cuda.setChecked(False);self.assertTrue(any('350-450' in label.text() for label in dialog.findChildren(QLabel)))
            dialog.reject();install.assert_not_called()
    def test_difference_wipe_playback_seek_and_escape_leave_timeline_unchanged(self):
        import time
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        from kinetic_cut.enhance_compare import DifferenceDialog
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.config.CACHE_DIR',Path(directory)/'cache'):
            source=Path(directory)/'source.png';original=QImage(160,120,QImage.Format_RGB32);original.fill(QColor('red'));original.save(str(source))
            media=MediaItem('m',str(source),'video','fixture',.2,160,120);media.fps=10
            item=TimelineItem('a','m','video_1',0,.2);item.effects=[enhance.default_effect()];project=Project(media=[media],timeline=[item])
            root=enhance.cache_path(project,media,item,0);(root/'frames').mkdir(parents=True);(root/'original').mkdir()
            enhanced=QImage(160,120,QImage.Format_RGB32);enhanced.fill(QColor('blue'))
            for n in (0,1):original.save(str(root/'original'/f'{n:08d}.png'));enhanced.save(str(root/'frames'/f'{n:08d}.png'))
            (root/'info.json').write_text(json.dumps(dict(key=root.name,family=enhance.signature(media,item,0,10,False),frames=2,fps=10,source_start=0)))
            self.w.set_project(project);before=copy.deepcopy(project.to_dict()['timeline']);at=project.playhead
            dialog=DifferenceDialog(self.w,item,0);dialog.open()
            deadline=time.monotonic()+3
            while dialog.worker is not None and time.monotonic()<deadline:QTest.qWait(10)
            self.assertFalse(dialog.canvas.before.isNull());self.assertFalse(dialog.canvas.after.isNull())
            rect=dialog.canvas.image_rect();QTest.mousePress(dialog.canvas,Qt.LeftButton,pos=rect.center().toPoint());point=rect.topLeft()+__import__('PySide6.QtCore',fromlist=['QPointF']).QPointF(rect.width()*.85,rect.height()*.5)
            QTest.mouseMove(dialog.canvas,point.toPoint());QTest.mouseRelease(dialog.canvas,Qt.LeftButton,pos=point.toPoint());self.assertGreater(dialog.canvas.split,.8)
            dialog.seek.setValue(1);deadline=time.monotonic()+3
            while dialog.presented_index!=1 and time.monotonic()<deadline:QTest.qWait(10)
            self.assertEqual(dialog.presented_index,1)
            dialog.toggle();QTest.qWait(150);self.assertTrue(dialog.playing)
            QTest.keyClick(dialog,Qt.Key_Escape);self.assertTrue(dialog._closed);self.assertFalse(dialog.timer.isActive());QTest.qWait(50)
            self.assertEqual(project.playhead,at);self.assertEqual(project.to_dict()['timeline'],before)
            # This fixture temporarily replaces the global cache directory.
            # Retire its asynchronous ownership observer before removing that
            # directory, just as the real editor waits for it during close.
            storage=getattr(self.w,'_enhance_storage',None)
            if storage:
                storage.finishing=True;storage.timer.stop();deadline=time.monotonic()+10
                while storage.job is not None and time.monotonic()<deadline:QTest.qWait(10)
                self.assertIsNone(storage.job);storage.deleteLater();del self.w._enhance_storage

