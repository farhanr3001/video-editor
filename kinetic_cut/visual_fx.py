"""Visual FX effects catalog, procedural animation engine, and keyframe synergy."""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass
from typing import Any

VISUAL_FX_SUBSECTIONS: dict[str, list[str]] = {
    "Zooms": [
        "Punch Zoom",
        "Smooth Zoom",
        "Slow Push-In",
        "Slow Pull-Out",
        "Snap Zoom",
        "Crash Zoom",
        "Zoom Bounce",
        "Zoom + Shake",
        "Zoom to Face",
        "Zoom to Object",
        "Zoom to Cursor",
        "Zoom to Tracked Region",
        "Zoom Out Reveal",
    ],
    "Camera Movement": [
        "Pan Left/Right",
        "Pan Up/Down",
        "Push In",
        "Pull Out",
        "Dolly",
        "Tilt",
        "Rotation",
        "Handheld Movement",
        "Drift",
        "Follow Subject",
        "Auto-Centre Subject",
        "Ken Burns",
        "Whip Pan",
        "Camera Movement Shake",
    ],
    "Shake / Impact Effects": [
        "Camera Shake",
        "Micro Shake",
        "Heavy Impact",
        "Horizontal Shake",
        "Vertical Shake",
        "Rotation Shake",
        "Bass Shake",
        "Explosion Shake",
        "Text Shake",
        "Object Shake",
    ],
}

# Flat list of all 37 Visual FX names
VISUAL_FX_NAMES: list[str] = [name for sub in VISUAL_FX_SUBSECTIONS.values() for name in sub]
VISUAL_FX_SET: set[str] = set(VISUAL_FX_NAMES)

# Quick lookup from effect name to subsection
SUBSECTION_BY_EFFECT: dict[str, str] = {
    name: sub for sub, names in VISUAL_FX_SUBSECTIONS.items() for name in names
}

# Zoom-in effects that can return/ease-out to normal (excluding zoom-out effects like Slow Pull-Out, Zoom Out Reveal)
ZOOM_IN_EFFECTS: set[str] = {
    "Punch Zoom",
    "Smooth Zoom",
    "Slow Push-In",
    "Snap Zoom",
    "Crash Zoom",
    "Zoom Bounce",
    "Zoom + Shake",
    "Zoom to Face",
    "Zoom to Object",
    "Zoom to Cursor",
    "Zoom to Tracked Region",
}


@dataclass
class VisualFXTransform:
    delta_scale: float = 0.0       # Added to base scale multiplier (1.0 = base)
    delta_scale_y: float = 0.0     # Added to base scale_y multiplier
    delta_x: float = 0.0           # Added to normalized X position (-0.5 to +0.5 fraction of frame width)
    delta_y: float = 0.0           # Added to normalized Y position (-0.5 to +0.5 fraction of frame height)
    delta_rotation: float = 0.0    # Added to rotation (degrees)
    delta_pitch: float = 0.0       # Added to 3D pitch tilt (degrees)
    delta_yaw: float = 0.0         # Added to 3D yaw pan (degrees)
    is_active: bool = False


def default_visual_fx(name: str) -> dict[str, Any]:
    """Return default parameter dictionary for a Visual FX effect."""
    subsection = SUBSECTION_BY_EFFECT.get(name, "Zooms")
    data: dict[str, Any] = {
        "name": name,
        "category": "Visual FX",
        "subsection": subsection,
        "enabled": True,
        # Common timing & scope
        "timing_mode": "clip_start",  # "clip_start", "clip_end", "playhead", "entire_clip"
        "start_time": 0.0,            # seconds offset
        "duration": 1.0,              # seconds
        "easing": "Smooth",           # "Smooth", "Ease Out", "Ease In", "Linear", "Snap", "Bounce"
        
        # Zooms parameters
        "zoom_start": 1.0,
        "zoom_target": 1.35,
        "zoom_return": (name in {"Punch Zoom", "Zoom Bounce", "Zoom + Shake"}),
        "zoom_hold_duration": 0.15,
        "zoom_attack_duration": 0.25,
        "show_timeline_overlay": True,
        "center_x": 0.5,
        "center_y": 0.5,
        "bounce_amplitude": 0.20,
        "shake_intensity": 15.0,
        
        # Camera Movement parameters
        "pan_x_start": 0.0,
        "pan_x_end": 0.15,
        "pan_y_start": 0.0,
        "pan_y_end": 0.0,
        "tilt_angle": 10.0,
        "rotation_angle": 15.0,
        "dolly_amount": 0.25,
        "handheld_speed": 1.2,
        "handheld_amount": 12.0,
        "ken_burns_start_scale": 1.0,
        "ken_burns_end_scale": 1.30,
        "ken_burns_start_x": 0.50,
        "ken_burns_start_y": 0.50,
        "ken_burns_end_x": 0.56,
        "ken_burns_end_y": 0.44,
        "whip_direction": "Right",    # "Right", "Left", "Up", "Down"
        "whip_blur": 25.0,
        
        # Shake / Impact parameters
        "shake_amplitude_x": 20.0,
        "shake_amplitude_y": 15.0,
        "shake_rotation": 2.0,
        "shake_frequency": 14.0,       # Hz
        "shake_decay": "Exponential",  # "Exponential", "Linear", "Constant"
        "shake_decay_rate": 3.5,
    }

    # Custom tuned defaults per effect
    if name == "Punch Zoom":
        data.update(duration=0.45, zoom_start=1.0, zoom_target=1.35, zoom_return=False, zoom_hold_duration=0.15, easing="Snap")
    elif name == "Smooth Zoom":
        data.update(duration=1.5, zoom_start=1.0, zoom_target=1.25, easing="Smooth")
    elif name == "Slow Push-In":
        data.update(timing_mode="entire_clip", duration=3.0, zoom_start=1.0, zoom_target=1.18, easing="Linear")
    elif name == "Slow Pull-Out":
        data.update(timing_mode="entire_clip", duration=3.0, zoom_start=1.20, zoom_target=1.0, easing="Linear")
    elif name == "Snap Zoom":
        data.update(duration=0.18, zoom_start=1.0, zoom_target=1.50, easing="Snap")
    elif name == "Crash Zoom":
        data.update(duration=0.20, zoom_start=1.0, zoom_target=1.85, easing="Snap")
    elif name == "Zoom Bounce":
        data.update(duration=0.60, zoom_start=1.0, zoom_target=1.40, easing="Bounce", bounce_amplitude=0.30)
    elif name == "Zoom + Shake":
        data.update(duration=0.40, zoom_start=1.0, zoom_target=1.35, easing="Snap", shake_intensity=20.0)
    elif name == "Zoom to Face":
        data.update(duration=1.2, zoom_start=1.0, zoom_target=1.45, center_x=0.50, center_y=0.35, easing="Smooth")
    elif name == "Zoom to Object":
        data.update(duration=1.0, zoom_start=1.0, zoom_target=1.40, center_x=0.65, center_y=0.40, easing="Smooth")
    elif name == "Zoom to Cursor":
        data.update(duration=0.8, zoom_start=1.0, zoom_target=1.50, center_x=0.50, center_y=0.50, easing="Smooth")
    elif name == "Zoom to Tracked Region":
        data.update(duration=1.2, zoom_start=1.0, zoom_target=1.40, center_x=0.50, center_y=0.50, easing="Smooth")
    elif name == "Zoom Out Reveal":
        data.update(duration=1.2, zoom_start=2.20, zoom_target=1.0, easing="Ease Out")
    elif name == "Pan Left/Right":
        data.update(duration=2.0, pan_x_start=-0.12, pan_x_end=0.12, pan_y_start=0.0, pan_y_end=0.0, zoom_start=1.15, zoom_target=1.15, easing="Smooth")
    elif name == "Pan Up/Down":
        data.update(duration=2.0, pan_x_start=0.0, pan_x_end=0.0, pan_y_start=-0.10, pan_y_end=0.10, zoom_start=1.15, zoom_target=1.15, easing="Smooth")
    elif name == "Push In":
        data.update(duration=2.5, zoom_start=1.0, zoom_target=1.25, tilt_angle=3.0, easing="Smooth")
    elif name == "Pull Out":
        data.update(duration=2.5, zoom_start=1.25, zoom_target=1.0, tilt_angle=-3.0, easing="Smooth")
    elif name == "Dolly":
        data.update(duration=2.0, pan_x_start=-0.08, pan_x_end=0.08, zoom_start=1.10, zoom_target=1.20, easing="Smooth")
    elif name == "Tilt":
        data.update(duration=1.5, tilt_angle=12.0, zoom_start=1.10, zoom_target=1.10, easing="Smooth")
    elif name == "Rotation":
        data.update(duration=1.5, rotation_angle=15.0, zoom_start=1.12, zoom_target=1.12, easing="Smooth")
    elif name == "Handheld Movement":
        data.update(timing_mode="entire_clip", handheld_speed=1.4, handheld_amount=14.0, zoom_start=1.08, zoom_target=1.08)
    elif name == "Drift":
        data.update(timing_mode="entire_clip", handheld_speed=0.6, handheld_amount=8.0, zoom_start=1.05, zoom_target=1.05)
    elif name == "Follow Subject":
        data.update(timing_mode="entire_clip", center_x=0.55, center_y=0.45, zoom_start=1.20, zoom_target=1.20)
    elif name == "Auto-Centre Subject":
        data.update(timing_mode="entire_clip", center_x=0.50, center_y=0.40, zoom_start=1.25, zoom_target=1.25)
    elif name == "Ken Burns":
        data.update(timing_mode="entire_clip", ken_burns_start_scale=1.05, ken_burns_end_scale=1.35, ken_burns_start_x=0.46, ken_burns_start_y=0.54, ken_burns_end_x=0.54, ken_burns_end_y=0.44, easing="Smooth")
    elif name == "Whip Pan":
        data.update(duration=0.22, whip_direction="Right", whip_blur=35.0, easing="Snap", zoom_start=1.15, zoom_target=1.15)
    elif name == "Camera Movement Shake":
        data.update(timing_mode="entire_clip", shake_amplitude_x=8.0, shake_amplitude_y=6.0, shake_rotation=0.8, shake_frequency=4.0, shake_decay="Constant", zoom_start=1.06, zoom_target=1.06)
    elif name == "Camera Shake":
        data.update(duration=0.60, shake_amplitude_x=22.0, shake_amplitude_y=16.0, shake_rotation=2.5, shake_frequency=16.0, shake_decay="Exponential", shake_decay_rate=3.5, zoom_start=1.08, zoom_target=1.08)
    elif name == "Micro Shake":
        data.update(duration=0.45, shake_amplitude_x=4.0, shake_amplitude_y=4.0, shake_rotation=0.5, shake_frequency=28.0, shake_decay="Linear", zoom_start=1.02, zoom_target=1.02)
    elif name == "Heavy Impact":
        data.update(duration=0.75, shake_amplitude_x=55.0, shake_amplitude_y=40.0, shake_rotation=6.0, shake_frequency=12.0, shake_decay="Exponential", shake_decay_rate=4.0, zoom_start=1.15, zoom_target=1.15)
    elif name == "Horizontal Shake":
        data.update(duration=0.50, shake_amplitude_x=30.0, shake_amplitude_y=0.0, shake_rotation=0.0, shake_frequency=18.0, shake_decay="Exponential", zoom_start=1.08, zoom_target=1.08)
    elif name == "Vertical Shake":
        data.update(duration=0.50, shake_amplitude_x=0.0, shake_amplitude_y=28.0, shake_rotation=0.0, shake_frequency=18.0, shake_decay="Exponential", zoom_start=1.08, zoom_target=1.08)
    elif name == "Rotation Shake":
        data.update(duration=0.50, shake_amplitude_x=5.0, shake_amplitude_y=5.0, shake_rotation=7.0, shake_frequency=15.0, shake_decay="Exponential", zoom_start=1.08, zoom_target=1.08)
    elif name == "Bass Shake":
        data.update(duration=0.65, shake_amplitude_x=16.0, shake_amplitude_y=24.0, shake_rotation=1.5, shake_frequency=8.0, shake_decay="Exponential", shake_decay_rate=2.8, zoom_start=1.08, zoom_target=1.08)
    elif name == "Explosion Shake":
        data.update(duration=0.90, shake_amplitude_x=65.0, shake_amplitude_y=50.0, shake_rotation=8.0, shake_frequency=20.0, shake_decay="Exponential", shake_decay_rate=3.0, zoom_start=1.18, zoom_target=1.18)
    elif name == "Text Shake":
        data.update(duration=0.40, shake_amplitude_x=12.0, shake_amplitude_y=12.0, shake_rotation=2.0, shake_frequency=22.0, shake_decay="Exponential", zoom_start=1.04, zoom_target=1.04)
    elif name == "Object Shake":
        data.update(duration=0.45, shake_amplitude_x=18.0, shake_amplitude_y=18.0, shake_rotation=3.0, shake_frequency=16.0, shake_decay="Exponential", zoom_start=1.06, zoom_target=1.06)

    return data


def interpolate_progress(raw_t: float, easing: str) -> float:
    """Calculate 0.0 to 1.0 progress using easing curve."""
    t = max(0.0, min(1.0, raw_t))
    if easing == "Linear":
        return t
    if easing == "Ease In":
        return t * t
    if easing == "Ease Out":
        return t * (2.0 - t)
    if easing == "Snap":
        return 1.0 - (1.0 - t) ** 3
    if easing == "Bounce":
        return 1.0 - math.exp(-5.5 * t) * math.cos(3.5 * math.pi * t)
    # Smooth (Ease In-Out cubic)
    return t * t * (3.0 - 2.0 * t)


def evaluate_single_effect(effect: dict[str, Any], local_time: float, clip_duration: float,
                           width: float = 1080.0, height: float = 1920.0) -> VisualFXTransform:
    """Compute transform deltas for a single Visual FX effect at local_time."""
    if not effect.get("enabled", True):
        return VisualFXTransform()

    timing_mode = effect.get("timing_mode", "clip_start")
    raw_duration = float(effect.get("duration", 1.0))
    duration = clip_duration if timing_mode == "entire_clip" else max(0.01, raw_duration)
    
    if timing_mode == "clip_end":
        start_t = max(0.0, clip_duration - duration)
    elif timing_mode == "entire_clip":
        start_t = 0.0
    else:
        start_t = max(0.0, float(effect.get("start_time", 0.0)))

    is_continuous = timing_mode == "entire_clip" or effect.get("shake_decay") == "Constant"
    name = effect.get("name", "")
    sub = effect.get("subsection", SUBSECTION_BY_EFFECT.get(name, "Zooms"))
    has_return = bool(effect.get("zoom_return", False)) and sub == "Zooms" and name in ZOOM_IN_EFFECTS
    
    if not is_continuous:
        if local_time < start_t:
            return VisualFXTransform()
        elapsed = local_time - start_t
        if elapsed > duration:
            if has_return or sub != "Zooms":
                return VisualFXTransform()
    else:
        elapsed = max(0.0, local_time - start_t)

    progress = min(1.0, elapsed / max(0.01, duration))
    easing = effect.get("easing", "Smooth")

    if has_return:
        hold_s = max(0.0, float(effect.get("zoom_hold_duration", 0.15)))
        hold_s = min(hold_s, max(0.0, duration - 0.02))
        r_avail = max(0.02, duration - hold_s)
        # Customizable attack duration: if not specified or out of range, default to half available transition time
        attack_req = effect.get("zoom_attack_duration")
        if attack_req is not None:
            attack_s = max(0.01, min(r_avail - 0.01, float(attack_req)))
        else:
            attack_s = r_avail / 2.0
        release_s = max(0.01, duration - hold_s - attack_s)

        if elapsed <= attack_s:
            sub_p = elapsed / attack_s
            eased = interpolate_progress(sub_p, easing)
        elif elapsed <= attack_s + hold_s:
            eased = 1.0
        elif elapsed <= duration:
            rel_p = (elapsed - attack_s - hold_s) / release_s
            return_easing = "Ease Out" if easing in ("Smooth", "Snap", "Bounce") else easing
            eased = max(0.0, 1.0 - interpolate_progress(rel_p, return_easing))
        else:
            return VisualFXTransform()
    else:
        eased = interpolate_progress(progress, easing)

    tf = VisualFXTransform(is_active=True)

    # --- Zooms ---
    if sub == "Zooms":
        z_start = float(effect.get("zoom_start", 1.0))
        z_target = float(effect.get("zoom_target", 1.35))
        current_zoom = z_start + (z_target - z_start) * eased
        
        tf.delta_scale = current_zoom - 1.0
        tf.delta_scale_y = current_zoom - 1.0

        cx = float(effect.get("center_x", 0.5))
        cy = float(effect.get("center_y", 0.5))
        if abs(current_zoom - 1.0) > 0.0001:
            tf.delta_x = (0.5 - cx) * (current_zoom - 1.0)
            tf.delta_y = (0.5 - cy) * (current_zoom - 1.0)

        if name == "Zoom Bounce" and elapsed < duration:
            bounce_amp = float(effect.get("bounce_amplitude", 0.25))
            decay = math.exp(-4.5 * progress)
            tf.delta_scale += bounce_amp * decay * math.sin(4.0 * math.pi * progress)
            tf.delta_scale_y = tf.delta_scale
        elif name == "Zoom + Shake" and elapsed < duration:
            intensity = float(effect.get("shake_intensity", 15.0))
            shake_env = math.exp(-5.0 * progress)
            tf.delta_x += (intensity / max(1.0, width)) * shake_env * math.sin(24.0 * math.pi * elapsed)
            tf.delta_y += (intensity / max(1.0, height)) * shake_env * math.cos(20.0 * math.pi * elapsed)

    # --- Camera Movement ---
    elif sub == "Camera Movement":
        if name == "Ken Burns":
            s1 = float(effect.get("ken_burns_start_scale", 1.0))
            s2 = float(effect.get("ken_burns_end_scale", 1.30))
            x1 = float(effect.get("ken_burns_start_x", 0.50))
            y1 = float(effect.get("ken_burns_start_y", 0.50))
            x2 = float(effect.get("ken_burns_end_x", 0.55))
            y2 = float(effect.get("ken_burns_end_y", 0.45))
            curr_s = s1 + (s2 - s1) * eased
            curr_x = x1 + (x2 - x1) * eased
            curr_y = y1 + (y2 - y1) * eased
            tf.delta_scale = curr_s - 1.0
            tf.delta_scale_y = curr_s - 1.0
            tf.delta_x = (0.5 - curr_x) * curr_s
            tf.delta_y = (0.5 - curr_y) * curr_s
        elif name in ("Handheld Movement", "Drift"):
            speed = float(effect.get("handheld_speed", 1.2))
            amp = float(effect.get("handheld_amount", 12.0))
            phase = elapsed * speed
            px = math.sin(phase * 1.1) * 0.6 + math.sin(phase * 2.3) * 0.3 + math.sin(phase * 0.4) * 0.1
            py = math.cos(phase * 0.9) * 0.6 + math.cos(phase * 1.7) * 0.3 + math.sin(phase * 0.5) * 0.1
            prot = math.sin(phase * 0.7) * 0.7 + math.cos(phase * 1.4) * 0.3
            tf.delta_x = (px * amp) / max(1.0, width)
            tf.delta_y = (py * amp) / max(1.0, height)
            tf.delta_rotation = prot * (amp * 0.1)
            zoom_pad = max(0.0, float(effect.get("zoom_start", 1.06)) - 1.0)
            tf.delta_scale = zoom_pad
            tf.delta_scale_y = zoom_pad
        elif name == "Whip Pan":
            direction = effect.get("whip_direction", "Right")
            amp = 0.8
            sign = 1.0 if direction in ("Right", "Down") else -1.0
            flick = math.sin(math.pi * progress) ** 2 * amp * sign
            if direction in ("Right", "Left"):
                tf.delta_x = flick
            else:
                tf.delta_y = flick
            tf.delta_scale = max(0.0, float(effect.get("zoom_start", 1.15)) - 1.0)
            tf.delta_scale_y = tf.delta_scale
        else:
            px_start = float(effect.get("pan_x_start", 0.0))
            px_end = float(effect.get("pan_x_end", 0.0))
            py_start = float(effect.get("pan_y_start", 0.0))
            py_end = float(effect.get("pan_y_end", 0.0))
            tf.delta_x = px_start + (px_end - px_start) * eased
            tf.delta_y = py_start + (py_end - py_start) * eased
            
            tilt = float(effect.get("tilt_angle", 0.0))
            rot = float(effect.get("rotation_angle", 0.0))
            tf.delta_pitch = tilt * eased
            tf.delta_rotation = rot * eased
            
            z_start = float(effect.get("zoom_start", 1.0))
            z_target = float(effect.get("zoom_target", 1.0))
            curr_z = z_start + (z_target - z_start) * eased
            tf.delta_scale = curr_z - 1.0
            tf.delta_scale_y = curr_z - 1.0

    # --- Shake / Impact Effects ---
    elif sub == "Shake / Impact Effects" or name == "Camera Movement Shake":
        decay_mode = effect.get("shake_decay", "Exponential")
        decay_rate = float(effect.get("shake_decay_rate", 3.5))
        freq = float(effect.get("shake_frequency", 15.0))
        amp_x = float(effect.get("shake_amplitude_x", 20.0))
        amp_y = float(effect.get("shake_amplitude_y", 15.0))
        amp_rot = float(effect.get("shake_rotation", 2.0))

        if decay_mode == "Constant":
            env = 1.0
        elif decay_mode == "Linear":
            env = max(0.0, 1.0 - progress)
        else:
            env = math.exp(-decay_rate * progress)

        t_sec = elapsed
        sx = env * (math.sin(2.0 * math.pi * freq * t_sec) * 0.7 +
                    math.sin(2.0 * math.pi * (freq * 1.618) * t_sec) * 0.3)
        sy = env * (math.cos(2.0 * math.pi * (freq * 0.88) * t_sec) * 0.7 +
                    math.sin(2.0 * math.pi * (freq * 2.14) * t_sec) * 0.3)
        srot = env * math.sin(2.0 * math.pi * (freq * 1.23) * t_sec)

        tf.delta_x = (sx * amp_x) / max(1.0, width)
        tf.delta_y = (sy * amp_y) / max(1.0, height)
        tf.delta_rotation = srot * amp_rot
        
        pad_zoom = max(0.0, float(effect.get("zoom_start", 1.08)) - 1.0)
        tf.delta_scale = pad_zoom
        tf.delta_scale_y = pad_zoom

    return tf


def evaluate_visual_fx(item: Any, local_time: float, width: float = 1080.0,
                        height: float = 1920.0) -> VisualFXTransform:
    """Compute the combined transform delta from all active Visual FX effects on an item."""
    effects = getattr(item, "effects", [])
    if not effects:
        return VisualFXTransform()

    combined = VisualFXTransform()
    clip_dur = getattr(item, "duration", 1.0)

    for effect in effects:
        if not effect.get("enabled", True) or effect.get("category") != "Visual FX":
            continue
        single = evaluate_single_effect(effect, local_time, clip_dur, width, height)
        if single.is_active:
            combined.is_active = True
            combined.delta_scale += single.delta_scale
            combined.delta_scale_y += single.delta_scale_y
            combined.delta_x += single.delta_x
            combined.delta_y += single.delta_y
            combined.delta_rotation += single.delta_rotation
            combined.delta_pitch += single.delta_pitch
            combined.delta_yaw += single.delta_yaw

    return combined


def apply_visual_fx_to_transform(transform: Any, vfx: VisualFXTransform) -> None:
    """Modify a clip's Transform in place with Visual FX deltas."""
    if not vfx.is_active:
        return
    transform.scale = max(0.05, min(8.0, transform.scale * (1.0 + vfx.delta_scale)))
    effective_y = transform.effective_scale_y * (1.0 + vfx.delta_scale_y)
    transform.scale_y = max(0.05, min(8.0, effective_y))
    transform.x = max(-5.0, min(5.0, transform.x + vfx.delta_x))
    transform.y = max(-5.0, min(5.0, transform.y + vfx.delta_y))
    transform.rotation = transform.rotation + vfx.delta_rotation
    transform.pitch = transform.pitch + vfx.delta_pitch
    transform.yaw = transform.yaw + vfx.delta_yaw


def bake_visual_fx_to_keyframes(item: Any, effect: dict[str, Any], fps: int = 30) -> bool:
    """Sample an active Visual FX effect into native item.keyframes and deactivate effect."""
    from .keyframes import put
    if not effect.get("enabled", True):
        return False

    duration = float(effect.get("duration", 1.0))
    timing_mode = effect.get("timing_mode", "clip_start")
    clip_dur = float(getattr(item, "duration", 1.0))
    if timing_mode == "entire_clip":
        duration = clip_dur
        start_t = 0.0
    elif timing_mode == "clip_end":
        start_t = max(0.0, clip_dur - duration)
    else:
        start_t = float(effect.get("start_time", 0.0))

    sub = effect.get("subsection", "")
    is_shake = sub == "Shake / Impact Effects" or "Shake" in effect.get("name", "")
    sample_rate = 30 if is_shake else 15
    steps = max(2, int(duration * sample_rate))
    dt = duration / steps

    base_scale = item.transform.scale
    base_scale_y = item.transform.effective_scale_y
    base_x = item.transform.x
    base_y = item.transform.y
    base_rot = item.transform.rotation

    for step in range(steps + 1):
        t = start_t + step * dt
        vfx = evaluate_single_effect(effect, t, clip_dur)
        sampled_scale = base_scale * (1.0 + vfx.delta_scale)
        sampled_scale_y = base_scale_y * (1.0 + vfx.delta_scale_y)
        sampled_x = base_x + vfx.delta_x
        sampled_y = base_y + vfx.delta_y
        sampled_rot = base_rot + vfx.delta_rotation

        put(item, "scale", t, sampled_scale, "Smooth" if not is_shake else "Linear")
        put(item, "scale_y", t, sampled_scale_y, "Smooth" if not is_shake else "Linear")
        put(item, "x", t, sampled_x, "Smooth" if not is_shake else "Linear")
        put(item, "y", t, sampled_y, "Smooth" if not is_shake else "Linear")
        if abs(vfx.delta_rotation) > 0.01 or abs(base_rot) > 0.01:
            put(item, "rotation", t, sampled_rot, "Smooth" if not is_shake else "Linear")

    effect["enabled"] = False
    effect["baked_to_keyframes"] = True
    return True


def visual_fx_synthetic_keyframes(item: Any, sample_fps: int = 30) -> dict[str, list[dict[str, Any]]]:
    """Generate synthetic keyframes from active Visual FX for FFmpeg export rendering."""
    effects = [e for e in getattr(item, "effects", []) if e.get("enabled", True) and e.get("category") == "Visual FX"]
    if not effects:
        return {}

    clip_dur = getattr(item, "duration", 1.0)
    has_shake = any(e.get("subsection") == "Shake / Impact Effects" or "Shake" in e.get("name", "") for e in effects)
    fps = 30 if has_shake else 15
    steps = max(2, int(clip_dur * fps))
    dt = clip_dur / steps

    base_scale = item.transform.scale
    base_scale_y = item.transform.effective_scale_y
    base_x = item.transform.x
    base_y = item.transform.y
    base_rot = item.transform.rotation

    keys: dict[str, list[dict[str, Any]]] = {"scale": [], "scale_y": [], "x": [], "y": [], "rotation": []}

    for step in range(steps + 1):
        t = min(clip_dur, step * dt)
        vfx = evaluate_visual_fx(item, t)
        keys["scale"].append({"time": t, "value": max(0.05, min(8.0, base_scale * (1.0 + vfx.delta_scale))), "interpolation": "Smooth"})
        keys["scale_y"].append({"time": t, "value": max(0.05, min(8.0, base_scale_y * (1.0 + vfx.delta_scale_y))), "interpolation": "Smooth"})
        keys["x"].append({"time": t, "value": max(-5.0, min(5.0, base_x + vfx.delta_x)), "interpolation": "Smooth"})
        keys["y"].append({"time": t, "value": max(-5.0, min(5.0, base_y + vfx.delta_y)), "interpolation": "Smooth"})
        keys["rotation"].append({"time": t, "value": base_rot + vfx.delta_rotation, "interpolation": "Smooth"})

    return keys
