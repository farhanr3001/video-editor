"""CPU-only layer preparation; no widgets or decoder-owned frames on workers."""
from dataclasses import dataclass, field
import math
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QImage, QPainter, QColor
from .model import Crop
from .creative_effects import NAMES as CREATIVE_NAMES, apply as apply_creative, clock as creative_clock, ANIMATED as CREATIVE_ANIMATED

@dataclass
class RasterContext:
    project: object
    interactive: bool
    raster_scale: float
    effect_cache: dict = field(default_factory=dict)
    crop_cache: dict = field(default_factory=dict)

    @staticmethod
    def _source_crop(image, crop):
        c=crop.clamped()
        rect=QRect(round(c.x*image.width()),round(c.y*image.height()),
                   max(1,round(c.width*image.width())),max(1,round(c.height*image.height())))
        return image.copy(rect.intersected(image.rect()))

    @staticmethod
    def _has_pixel_effects(item):
        from .effects import MATRICES
        from .chroma import NAMES
        from .vision_effects import active
        from .tracking_effect import active as tracking_active
        from .enhance import active as enhance_active
        return (item.crop_softness > 0 or item.grayscale or abs(item.brightness) > .001
                or abs(item.contrast-1) > .001 or abs(item.saturation-1) > .001
                or item.sharpen > .001 or active(item) or tracking_active(item) or enhance_active(item)
                or any(e.get('enabled',True) and (e.get('name')=='Gaussian Blur'
                       or e.get('name') in MATRICES or e.get('name') in NAMES or e.get('name') in CREATIVE_NAMES) for e in item.effects))

def prepare_layer_image(self, item, layer_source, target, frame_rect):
    from .enhance import active as enhance_active
    if enhance_active(item):
        import copy
        from pathlib import Path
        from .enhance import render_frame, range_at
        at=item.source_time(self.project.playhead)
        media=self.project.media_by_id(item.media_id)
        stamps=[]
        for index,_ in enhance_active(item):
            record=range_at(self.project,media,item,index,at)
            try:stamp=(record['key'],(Path(record['root'])/'info.json').stat().st_mtime_ns) if record else None
            except OSError:stamp=None
            stamps.append(stamp)
        tag=('enhance',item.id)
        key=(layer_source.cacheKey(),repr(item),at,repr(self.project.settings),tuple(stamps),
             round(target.x()-frame_rect.x(),6),round(target.y()-frame_rect.y(),6),
             target.width(),target.height(),frame_rect.width(),frame_rect.height(),self.interactive,self.raster_scale)
        cached=self.effect_cache.get(tag)
        if cached and cached[0]==key:return cached[1]
        # Read/blend at the physical display size only when the enhancement is
        # the final pixel operation. Full-resolution export uses render_frame.
        last=enhance_active(item)[-1][0]
        eligible=(item.role!='background' and not item.crop_softness
                  and not any(e.get('enabled',True) for e in item.effects[last+1:]))
        image=QImage()
        if eligible:
            from .enhance_preview import frame
            size=QSize(max(1,math.ceil(abs(target.width())*self.raster_scale)),
                       max(1,math.ceil(abs(target.height())*self.raster_scale)))
            image=frame(self.project,media,item,last,at,size)
        if image.isNull():image=render_frame(self.project,item,layer_source,at)
        baked=copy.copy(item);baked.effects=[];baked.crop=Crop();baked.grayscale=False;baked.brightness=0.;baked.contrast=baked.saturation=1.;baked.sharpen=0.
        result=prepare_layer_image(self,baked,image,target,frame_rect)
        if len(self.effect_cache)>=16:self.effect_cache.pop(next(iter(self.effect_cache)))
        self.effect_cache[tag]=(key,result)
        return result
    interactive = self.interactive
    # Filter at the actual on-screen layer resolution during motion, not at
    # export resolution. Include viewer zoom and HiDPI; never upscale a source
    # or downsample sharp, unfiltered webcam/gameplay crops. Pausing restores
    # the original-quality path, including for screenshots/export parity.
    raster_scale = self.raster_scale
    from .tracking_effect import active as tracking_active, apply as apply_tracking, cache_key as tracking_cache_key, follow_effect, effective_crop, crop_source
    tracking = tracking_active(item)
    source_time = item.source_time(self.project.playhead)
    media = self.project.media_by_id(item.media_id) if tracking else None
    effect_key = tracking_cache_key(item, media, source_time) if tracking else repr(item.effects)
    if any(e.get("enabled",True) and e.get("name") in CREATIVE_ANIMATED for e in item.effects):
        effect_key=(effect_key,self.project.playhead)
    follow = bool(follow_effect(item))
    if item.role == "background":
        from .chroma import apply_stack
        from .visuals import grade_image, blur_image
        from .effects import MATRICES, apply_color_effect
        cache_key = (layer_source.cacheKey(), effect_key, item.grayscale,
                     item.brightness, item.contrast, item.saturation, item.sharpen,
                     self.project.settings.blur, self.project.settings.background_brightness,
                     frame_rect.width(), frame_rect.height(), interactive)
        cached = self.effect_cache.get(item.id)
        if cached and cached[0] == cache_key:return cached[1]
        source = layer_source
        if tracking:
            from .vision_effects import active as vision_active, apply as apply_vision
            # Backgrounds normally show the full original source. Preserve that
            # behavior while protecting it before background blur/stretch. When
            # stacked with legacy vision effects, their crop-domain analysis is
            # retained consistently in both viewer and prepared export.
            track_crop = item.crop.clamped() if vision_active(item) else Crop()
            if follow:source = crop_source(source, item, media, source_time, track_crop)
            elif track_crop != Crop():source = self._source_crop(source, track_crop)
            if vision_active(item):source = apply_vision(source, item, media, source_time)
            source = apply_tracking(source, item, media, source_time, effective_crop(item, media, source_time, track_crop))
        small = source.scaled(270, 480, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        small = apply_stack(small, item)
        small = grade_image(small, item.grayscale, item.brightness, item.contrast, item.saturation, item.sharpen)
        for effect in item.effects:
            if effect.get("enabled",True) and effect.get("name") in CREATIVE_NAMES:
                small = apply_creative(small,effect,creative_clock(effect,item,self.project.playhead))
            if effect.get("enabled", True) and effect.get("name") == "Gaussian Blur":
                small = blur_image(small, effect.get("horizontal", 12), effect.get("vertical", 12), effect.get("blend", 100) / 100, effect.get("border", "Reflect"), preview_fast=interactive)
            if effect.get("enabled", True) and effect.get("name") in MATRICES:
                small = apply_color_effect(small, effect)
        bg = blur_image(small, self.project.settings.blur * 0.25, self.project.settings.blur * 0.25, preview_fast=interactive).scaled(frame_rect.size().toSize(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        bg_rect = QRect((bg.width() - round(frame_rect.width())) // 2, (bg.height() - round(frame_rect.height())) // 2, round(frame_rect.width()), round(frame_rect.height()))
        bg_copy = bg.copy(bg_rect)
        if self.project.settings.background_brightness < 1.0:
            p_tint = QPainter(bg_copy)
            p_tint.fillRect(bg_copy.rect(), QColor(0, 0, 0, round(255 * (1 - min(1, self.project.settings.background_brightness)))))
            p_tint.end()
        if len(self.effect_cache) >= 16:self.effect_cache.pop(next(iter(self.effect_cache)))
        self.effect_cache[item.id] = (cache_key, bg_copy)
        return bg_copy
    else:
        from .effects import MATRICES, apply_color_effect
        from .chroma import apply_stack
        from .vision_effects import apply as apply_vision
        from .visuals import blur_image, grade_image, soften_edges
        has_pixel_effects = self._has_pixel_effects(item)
        if not has_pixel_effects:
            key = (layer_source.cacheKey(), repr(item.crop))
            cached = self.crop_cache.get(item.id)
            if cached and cached[0] == key:return cached[1]
            crop = item.crop.clamped()
            result = layer_source if crop == Crop() else self._source_crop(layer_source, crop)
            if len(self.crop_cache) >= 16:self.crop_cache.pop(next(iter(self.crop_cache)))
            self.crop_cache[item.id] = (key, result)
            return result
        # Viewer translation changes presentation, not filtered source pixels.
        # Interactive ROI blur additionally depends on the layer's position
        # relative to the canvas, never the canvas's absolute widget position.
        # Quantize sub-pixel cancellation noise from translating both rectangles.
        relative_position = (round(target.x()-frame_rect.x(),6),round(target.y()-frame_rect.y(),6)) if interactive else None
        cache_key = (layer_source.cacheKey(), repr(item.crop), effect_key, item.crop_softness, item.grayscale, item.brightness, item.contrast, item.saturation, item.sharpen, item.transform.rotation, item.transform.pitch, item.transform.yaw, item.transform.flip_horizontal, item.transform.flip_vertical, relative_position, target.width(), target.height(), frame_rect.width(), frame_rect.height(), interactive, raster_scale)
        cached = self.effect_cache.get(item.id)
        if cached and cached[0] == cache_key:
            return cached[1]
        cropped = crop_source(layer_source, item, media, source_time) if follow else layer_source if item.crop.clamped() == Crop() else self._source_crop(layer_source, item.crop)
        from .finishing_effects import CONTROLS as FINISHING_CONTROLS
        finishing=any(e.get('enabled',True) and e.get('name') in FINISHING_CONTROLS for e in item.effects)
        max_w = max(self.project.settings.width, self.project.settings.height)
        if not finishing and (cropped.width() > max_w or cropped.height() > max_w):
            cropped = cropped.scaled(max_w, max_w, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if finishing:
            # Procedural fields (grain/scanlines/halftone) must be evaluated at
            # the same layer raster as the GPU, not generated on a small source
            # and enlarged afterwards. This also preserves nonuniform scaling.
            limit=2048 if interactive else 8192
            size=QSize(max(2,min(limit,math.ceil(target.width()*raster_scale))),max(2,min(limit,math.ceil(target.height()*raster_scale))))
            if cropped.size()!=size:cropped=cropped.scaled(size,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        elif interactive:
            scale = min(1., max(target.width()*raster_scale/max(1,cropped.width()),
                                target.height()*raster_scale/max(1,cropped.height())))
            if scale < 1.:
                cropped = cropped.scaled(max(1,math.ceil(cropped.width()*scale)),
                                         max(1,math.ceil(cropped.height()*scale)),
                                         Qt.KeepAspectRatio, Qt.SmoothTransformation)
        cropped = apply_vision(cropped, item, self.project.media_by_id(item.media_id), item.source_time(self.project.playhead))
        if tracking:cropped = apply_tracking(cropped, item, media, source_time, effective_crop(item, media, source_time))
        cropped = apply_stack(cropped, item)
        cropped = grade_image(cropped, item.grayscale, item.brightness, item.contrast, item.saturation, item.sharpen)
        sx = cropped.width() / max(1.0, target.width() / frame_rect.width() * self.project.settings.width)
        sy = cropped.height() / max(1.0, target.height() / frame_rect.height() * self.project.settings.height)
        for effect in item.effects:
            if effect.get("enabled",True) and effect.get("name") in CREATIVE_NAMES:
                cropped = apply_creative(cropped,effect,creative_clock(effect,item,self.project.playhead))
            if effect.get("enabled", True) and effect.get("name") == "Gaussian Blur":
                rx, ry = effect.get("horizontal", 12) * sx, effect.get("vertical", 12) * sy
                region = None
                transform = item.transform
                # Only a single isotropic blur on an axis-aligned layer is
                # eligible. Everything else retains the complete-image path.
                # Output remains source-sized; no visible pixel is downsampled.
                single = sum(e.get("enabled",True) and e.get("name")=="Gaussian Blur" for e in item.effects)==1
                visible = target.intersected(frame_rect)
                if (interactive and single and abs(rx-ry)<1e-9 and not follow
                        and not transform.rotation and not transform.pitch and not transform.yaw
                        and not transform.flip_horizontal and not transform.flip_vertical
                        and not visible.isEmpty() and target.width()>0 and target.height()>0
                        and abs(target.width()/cropped.width()-target.height()/cropped.height())<1e-6):
                    region = (max(0,math.floor((visible.left()-target.left())/target.width()*cropped.width())-3),
                              max(0,math.floor((visible.top()-target.top())/target.height()*cropped.height())-3),
                              min(cropped.width(),math.ceil((visible.right()-target.left())/target.width()*cropped.width())+3),
                              min(cropped.height(),math.ceil((visible.bottom()-target.top())/target.height()*cropped.height())+3))
                cropped = blur_image(cropped, rx, ry, effect.get("blend", 100) / 100, effect.get("border", "Reflect"), preview_fast=interactive, region=region)
            if effect.get("enabled", True) and effect.get("name") in MATRICES:
                cropped = apply_color_effect(cropped, effect)
        if item.crop_softness > 0:
            cropped = soften_edges(cropped, item.crop_softness * sx, item.crop_softness * sy)
        if len(self.effect_cache) > 16:
            self.effect_cache.clear()
        self.effect_cache[item.id] = (cache_key, cropped)
        return cropped

def prepare_frame(image, context, requests):
    for item, target, frame_rect in requests:
        prepare_layer_image(context, item, image, target, frame_rect)
    return image, context.effect_cache
