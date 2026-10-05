import copy
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage

from kinetic_cut.model import Crop, MediaItem, Project, TimelineItem, Transform
from kinetic_cut import tracking_effect as tracking
from kinetic_cut.object_tracking import fingerprint


def fixture(root, duration=4., width=256, height=144):
    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(QColor('#dce5ec'))
    for y in range(height):
        for x in range(width):
            image.setPixelColor(x, y, QColor(90 + x % 140, 70 + y % 170, 180))
    path = Path(root) / 'source.png'; image.save(str(path))
    media = MediaItem('source', str(path), 'image', 'Original', duration, width, height)
    item = TimelineItem('clip', media.id, 'video_1', 0, duration, transform=Transform(.5, .5))
    effect = tracking.default_effect(); effect.update(padding=0., radius=0.)
    effect['analysis'] = dict(version=1, source=fingerprint(media), source_start=0., source_end=duration,
                              sample_fps=15., reference_time=0., frames=[
                                  dict(time=0., box=[.1, .3, .15, .3], confidence=1., status='manual'),
                                  dict(time=duration / 2, box=[.4, .3, .15, .3], confidence=.9, status='tracked'),
                                  dict(time=duration, box=[.7, .3, .15, .3], confidence=.9, status='tracked')])
    item.effects = [effect]
    return media, item, effect, image


class TrackingEffectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    def tearDown(self):
        tracking._images.clear(); self.temp.cleanup()

    def test_full_source_boxes_follow_crop_and_source_clock_after_split_retime(self):
        media, item, effect, image = fixture(self.root)
        item.crop = Crop(.25, 0, .5, 1)
        result = tracking.apply(image.copy(64, 0, 128, 144), item, media, 2)
        self.assertEqual(result.pixelColor(58, 60), QColor('black'))
        self.assertNotEqual(result.pixelColor(15, 60), QColor('black'))
        project = Project(media=[media], timeline=[item])
        left, right = project.split(item.id, 2)
        self.assertEqual(tracking.box_at(right.effects[0], media, right, right.source_time(right.start)), [.4, .3, .15, .3])
        project.retime_items([right.id], 2)
        at = right.source_time(right.start + .5)
        self.assertAlmostEqual(at, 3.)
        self.assertAlmostEqual(tracking.box_at(right.effects[0], media, right, at)[0], .55)
        right.duration = 2.; self.assertFalse(tracking.valid(right.effects[0], media, right))
        self.assertIn('range changed', tracking.export_error(right.effects[0], media, right))

    def test_censor_losses_and_invalid_analysis_fail_closed_even_with_low_opacity(self):
        media, item, effect, image = fixture(self.root)
        for mode in tracking.CENSOR_MODES:
            effect['mode'] = mode; effect['opacity'] = 10.
            effect['analysis']['frames'][1]['status'] = 'lost'
            for at in (1., 2., 3.):
                result = tracking.apply(image, item, media, at)
                self.assertEqual(result.pixelColor(0, 0), QColor('black'))
                self.assertEqual(result.pixelColor(200, 100), QColor('black'))
            effect['loss_policy'] = 'Hide'; effect['loss_reviewed'] = False
            self.assertEqual(tracking.apply(image, item, media, 2).pixelColor(0, 0), QColor('black'))
            self.assertIn('Review', tracking.export_error(effect, media, item))
            effect['loss_reviewed'] = True
            self.assertEqual(tracking.apply(image, item, media, 2), image)
            self.assertFalse(tracking.export_error(effect, media, item))
            effect['loss_policy'] = 'Full frame'; effect['loss_reviewed'] = False
        effect['analysis'] = {}
        self.assertEqual(tracking.apply(image, item, media, 0).pixelColor(0, 0), QColor('black'))
        self.assertIn('analyse', tracking.export_error(effect, media, item))
        effect['enabled'] = False; self.assertEqual(tracking.apply(image, item, media, 0), image)

    def test_marker_loss_hides_and_explicit_hold_uses_last_observed_box(self):
        media, item, effect, image = fixture(self.root)
        effect.update(mode='Rectangle', loss_policy='Hide', color='#ff0022')
        effect['analysis']['frames'][1]['status'] = 'lost'
        self.assertEqual(tracking.apply(image, item, media, 2), image)
        self.assertIn('hidden', tracking.status(item, media, 2))
        effect['loss_policy'] = 'Hold'
        self.assertEqual(tracking.box_at(effect, media, item, 3), [.1, .3, .15, .3])
        self.assertNotEqual(tracking.apply(image, item, media, 3), image)
        self.assertEqual(tracking.box_at(effect, media, item, 4), [.7, .3, .15, .3])

    def test_all_marker_modes_settings_image_identity_and_malformed_effects(self):
        media, item, effect, image = fixture(self.root)
        stamp = self.root / 'stamp.png'; solid = QImage(40, 40, QImage.Format_RGBA8888)
        solid.fill(QColor('red')); solid.save(str(stamp))
        for mode in tracking.MODES:
            if mode=='Follow Crop':continue # Dynamic viewport checked separately below.
            effect.update(mode=mode, color='#fb2060', loss_policy='Full frame' if mode in tracking.CENSOR_MODES else 'Hide',
                          image=str(stamp), label='Target', font_size=16., arrow_length=40., arrow_head=12.)
            rendered = tracking.apply(image, item, media, 1.)
            self.assertNotEqual(rendered, image, mode)
            self.assertEqual(rendered.size(), image.size())
            self.assertFalse(tracking.export_error(effect, media, item), mode)
        effect['mode'] = 'Image'; stamp.unlink()
        self.assertIn('image marker', tracking.export_error(effect, media, item))
        effect['mode'] = 'Censor Bar'; effect['opacity'] = float('nan')
        self.assertFalse(tracking.valid(effect, media, item))
        self.assertEqual(tracking.apply(image, item, media, 0).pixelColor(0, 0), QColor('black'))
        effect['opacity'] = 100.; effect['analysis']['frames'][1]['box'] = ['bad']
        self.assertIn('analyse', tracking.export_error(effect, media, item))
        effect.update(follow_scale=False, loss_policy='Hold', loss_reviewed=True)
        effect['analysis']['reference_time']=2.
        effect['analysis']['frames'][0]['status']='lost'
        # The current exact endpoint is valid, while reference/interior data is
        # damaged. Viewing cannot throw or adopt an invalid fixed-size box.
        self.assertFalse(tracking.apply(image,item,media,4).isNull())

    def test_dynamic_still_cache_background_and_static_worker_bypass(self):
        from kinetic_cut.preview_raster import RasterContext, prepare_layer_image
        from kinetic_cut.widgets import PreviewCanvas
        media, item, effect, image = fixture(self.root)
        project = Project(media=[media], timeline=[item]); project.settings.width=256; project.settings.height=144
        rect = QRectF(0, 0, 256, 144); context = RasterContext(project, False, 1.)
        first = prepare_layer_image(context, item, image, rect, rect)
        project.playhead = 2.; second = prepare_layer_image(context, item, image, rect, rect)
        self.assertNotEqual(first, second)
        again = prepare_layer_image(context, item, image, rect, rect)
        self.assertEqual(again.cacheKey(), second.cacheKey())
        canvas = PreviewCanvas(); canvas.set_project(project); canvas.active_frames[item.id]='decode'
        self.assertIsNone(canvas.frame_work('decode', image))
        canvas.close(); canvas.deleteLater()
        item.role = 'background'; item.crop = Crop(.25, .25, .5, .5)
        effect['analysis']['frames'][1]['status'] = 'lost'
        result = prepare_layer_image(context, item, image, rect, rect)
        self.assertEqual(result.pixelColor(10, 10), QColor('black'))
        self.assertEqual(result.pixelColor(250, 140), QColor('black'))

    def test_size_scale_padding_offsets_rotation_and_legacy_stack_order(self):
        from kinetic_cut.preview_raster import RasterContext, prepare_layer_image
        media, item, effect, image = fixture(self.root)
        effect.update(mode='Censor Bar', color='#0033aa', width=150., height=50., offset_x=20., rotation=90.)
        result = tracking.apply(image, item, media, 0.)
        self.assertEqual(result.pixelColor(65, 64), QColor('#0033aa'))
        self.assertNotEqual(result.pixelColor(44, 60), QColor('#0033aa'))
        effect.update(rotation=0., width=100., height=100., offset_x=0.)
        effect['analysis']['frames'][-1]['box'][2] = .3
        effect['analysis']['frames'][-1]['box'][0] = .6
        effect['follow_scale'] = False
        small = tracking.apply(image, item, media, 4.)
        effect['follow_scale'] = True; large = tracking.apply(image, item, media, 4.)
        self.assertNotEqual(small, large)
        project = Project(media=[media], timeline=[item]); project.settings.width=256; project.settings.height=144
        red = QImage(image); red.fill(QColor('red'))
        rect = QRectF(0, 0, 256, 144)
        with patch('kinetic_cut.vision_effects.apply', return_value=red):
            combined = prepare_layer_image(RasterContext(project, False, 1.), item, image, rect, rect)
        self.assertEqual(combined.pixelColor(0, 0), QColor('red'))
        self.assertEqual(combined.pixelColor(45, 60), QColor('#0033aa'))

    def test_cache_prunes_only_generated_tracking_files_preserves_active_and_user_files(self):
        for name in ('track-old.mkv', 'track-used.mkv', 'user.mkv'):
            (self.root / name).write_bytes(b'12345678')
        os.utime(self.root / 'track-old.mkv', (1, 1))
        tracking.prune(self.root, {str(self.root / 'track-used.mkv')}, budget=8)
        self.assertFalse((self.root / 'track-old.mkv').exists())
        self.assertTrue((self.root / 'track-used.mkv').exists())
        self.assertTrue((self.root / 'user.mkv').exists())

    def test_follow_crop_clamp_loss_fallback_last_enabled_and_original_geometry(self):
        media,item,effect,image=fixture(self.root)
        item.crop=Crop(.25,.2,.5,.5); effect.update(mode='Follow Crop',loss_policy='Hold')
        first=tracking.effective_crop(item,media,0.)
        self.assertEqual((first.x,first.width,first.height),(0.,.5,.5)); self.assertAlmostEqual(first.y,.2)
        final=tracking.effective_crop(item,media,4.)
        self.assertEqual((final.x,final.width,final.height),(.5,.5,.5)); self.assertAlmostEqual(final.y,.2)
        followed=tracking.crop_source(image,item,media,4.)
        self.assertEqual((followed.width(),followed.height()),(128,72))
        self.assertEqual(item.crop,Crop(.25,.2,.5,.5))
        effect['analysis']['frames'][1]['status']='lost'
        self.assertEqual(tracking.effective_crop(item,media,2.),first)
        self.assertFalse(tracking.export_error(effect,media,item))
        effect['loss_policy']='Hide'; self.assertEqual(tracking.effective_crop(item,media,2.),item.crop)
        effect['loss_policy']='Full frame'; self.assertEqual(tracking.effective_crop(item,media,2.),Crop())
        effect['loss_policy']='Hold'; effect['analysis']['frames'][0]['status']='lost'
        self.assertEqual(tracking.effective_crop(item,media,0.),item.crop)
        effect['analysis']['frames'][0]['status']='manual'
        override=copy.deepcopy(effect); override.update(width=50.,height=50.); item.effects.append(override)
        self.assertEqual(tracking.effective_crop(item,media,0.).width,.25)
        self.assertEqual(tracking.render_effects(item),[override])
        override['enabled']=False; self.assertEqual(tracking.effective_crop(item,media,0.),first)
        effect.update(width=1000.,height=1.,offset_x=32768.,offset_y=-32768.)
        bounded=tracking.effective_crop(item,media,4.)
        self.assertEqual(bounded,Crop(0.,0.,1.,.02))
        self.assertEqual(tracking.default_effect('Follow Crop')['loss_policy'],'Hold')

    def test_follow_crop_markers_use_moving_source_viewport_and_legacy_conflicts_are_explicit(self):
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        media,item,follow,image=fixture(self.root)
        follow.update(mode='Follow Crop',loss_policy='Hold'); item.crop=Crop(.25,.2,.5,.5)
        marker=copy.deepcopy(follow); marker.update(mode='Censor Bar',loss_policy='Full frame')
        item.effects=[follow,marker]
        viewport=tracking.effective_crop(item,media,2.)
        cropped=tracking.crop_source(image,item,media,2.)
        result=tracking.apply(cropped,item,media,2.,viewport)
        self.assertEqual(result.pixelColor(64,36),QColor('black'))
        self.assertNotEqual(result.pixelColor(5,5),QColor('black'))
        project=Project(media=[media],timeline=[item]); project.settings.width=256; project.settings.height=144; project.playhead=2.
        rect=QRectF(0,0,256,144)
        self.assertEqual(prepare_layer_image(RasterContext(project,False,1.),item,image,rect,rect),result)
        item.effects.append(dict(name='Party Hat',enabled=True))
        self.assertIn('cannot be combined',tracking.export_error(follow,media,item))
        self.assertIn('unavailable',tracking.status(item,media,2.))
        self.assertEqual(tracking.effective_crop(item,media,2.),item.crop)
        from kinetic_cut.vision_effects import prepare_export
        with self.assertRaisesRegex(ValueError,'cannot be combined'):
            prepare_export(project,'ffmpeg',None,threading.Event())
        item.effects=[dict(name='Party Hat',enabled=True)]
        self.assertIn('cannot be combined',tracking.export_error(follow,media,item)) # A proposed dialog effect, not yet installed.

    def test_follow_crop_real_export_cropped_facecam_retime_and_held_loss_parity(self):
        from kinetic_cut.exporter import export,PRESETS
        from kinetic_cut.process import run
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        media,item,effect,image=fixture(self.root,duration=2.,width=128,height=128)
        effect.update(mode='Follow Crop',loss_policy='Hold')
        item.crop=Crop(.25,.25,.5,.5); item.role='facecam'; item.start=0.; item.duration=1.; item.speed=2.
        # A 64px viewport occupies the same 64px media rectangle throughout:
        # the normal facecam factor .92 is cancelled for exact pixel comparison.
        item.transform.scale=item.transform.scale_y=1/.92
        project=Project(media=[media],timeline=[item]); project.settings.width=128; project.settings.height=128; project.settings.fps=30
        project.settings.normalize_audio=False
        before=copy.deepcopy(item)
        rect=QRectF(0,0,128,128)
        for loss in (False,True):
            if loss:effect['analysis']['frames'][1]['status']='lost'
            output=self.root/('follow-crop-loss.mp4' if loss else 'follow-crop.mp4')
            export(project,str(output),next(iter(PRESETS.values())),False,'CPU',export_audio=False)
            raw=run(['ffmpeg','-v','error','-i',str(output),'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
            frames=np.frombuffer(raw,np.uint8).reshape(-1,128,128,3); self.assertEqual(len(frames),30)
            for n in (0,8,15,23,29):
                project.playhead=n/30
                expected=prepare_layer_image(RasterContext(project,False,1.),item,image,QRectF(32,32,64,64),rect)
                rgba=np.frombuffer(expected.constBits(),np.uint8).reshape(64,64,4)
                self.assertLess(np.abs(frames[n,32:96,32:96].astype(float)-rgba[:,:,:3]).mean(),4.)
                self.assertLess(frames[n,:30].mean(),1.)
            if loss:self.assertLess(np.abs(frames[0].astype(float)-frames[29]).mean(),1.)
            else:self.assertGreater(np.abs(frames[0].astype(float)-frames[29]).mean(),3.)
        effect['analysis']['frames'][1]['status']='tracked'; self.assertEqual(item,before)

    def test_real_decoded_export_is_source_timed_lossless_preparation_and_blocks_unprepared(self):
        from kinetic_cut.exporter import export, PRESETS, build_command
        from kinetic_cut.process import run
        media, item, effect, image = fixture(self.root, duration=1., width=128, height=128)
        project = Project(media=[media], timeline=[item]); project.settings.width=128; project.settings.height=128; project.settings.fps=30
        project.settings.normalize_audio=False; effect.update(color='#000000')
        with self.assertRaisesRegex(ValueError, 'tracking.*prepared'):
            build_command(project, str(self.root / 'unsafe.mp4'), next(iter(PRESETS.values())), False, 'CPU')
        output = self.root / 'safe.mp4'
        export(project, str(output), next(iter(PRESETS.values())), False, 'CPU', export_audio=False)
        raw = run(['ffmpeg', '-v', 'error', '-i', str(output), '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
                  capture_output=True, check=True).stdout
        frames = np.frombuffer(raw, np.uint8).reshape(-1, 128, 128, 3)
        self.assertEqual(len(frames), 30)
        for n in (0, 8, 15, 23, 29):
            expected = tracking.apply(image, item, media, n / 30)
            rgba = np.frombuffer(expected.constBits(), np.uint8).reshape(128, 128, 4)
            self.assertLess(np.abs(frames[n].astype(float) - rgba[:, :, :3]).mean(), 4.)
        effect['analysis']['frames'][1]['status']='lost'
        export(project, str(self.root / 'loss.mp4'), next(iter(PRESETS.values())), False, 'CPU', export_audio=False)
        lost = run(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', str(self.root / 'loss.mp4'), '-frames:v', '1',
                    '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
        self.assertLess(np.frombuffer(lost, np.uint8).mean(), 1.)
