"""Effect metadata shared by the library, drop validation and render pipelines."""
from .visual_fx import VISUAL_FX_NAMES, VISUAL_FX_SET, VISUAL_FX_SUBSECTIONS
from .transitions import (
    TRANSITION_NAMES,
    TRANSITION_SET,
    TRANSITION_SUBSECTIONS,
    TRANSITION_ICONS,
    TRANSITION_DESCRIPTIONS,
)

CATALOG = {
    "Visual FX": VISUAL_FX_NAMES,
    "Video Transitions": TRANSITION_NAMES,
    "Open FX / Blur": ["Gaussian Blur"],
    "Transform": ["Circle Facecam"],
    "Tracking": ["Object Tracking"],
    "Keying": ["Chroma Key", "Green Screen"],
    "Person / Background": ["Remove Person Background"],
    "Face Filters": ["Big Eyes", "Big Nose", "Big Lips", "Face Twist", "Custom Face", "Puppy Ears & Nose", "Cat Ears & Whiskers", "AR Plague Mask", "AR Pixel Glasses"],
    "Colour": ["Black & White", "Light Boost", "Cinematic Contrast", "Warm Tone", "Cool Tone", "Sepia", "Channel Swap"],
    "Titles": ["Text", "Headline"],
    "Audio": ["Noise Clean", "Voice Clarity", "Low Cut", "Auto Duck", "Fade In / Out", "Cut curse words", "Remove Silence", "Vocal Only"],
    "Graphics": ["Motion Composition", "Circle", "Pointing Arrow", "Square", "Rectangle", "Timer / Countdown", "Speech Bubble / Quote Card", "Progress Bar", "Callout Badge"],
}
# Browser-only grouping: keep the established Face Filters catalog and effect
# names intact so saved projects, drag/drop, and automation remain compatible.
FACE_FILTER_SUBSECTIONS = {
    "Face shape & colour": ("Custom Face", "Big Eyes", "Big Nose", "Big Lips", "Face Twist"),
    "Animal filters": ("Puppy Ears & Nose", "Cat Ears & Whiskers"),
    "Glasses": ("AR Pixel Glasses",),
    "Masks": ("AR Plague Mask",),
}
TITLES = set(CATALOG["Titles"])
GRAPHICS = set(CATALOG["Graphics"])

EFFECT_ICONS = {
    "Object Tracking": "crosshair",
    "Puppy Ears & Nose": "smile",
    "Cat Ears & Whiskers": "smile",
    "AR Plague Mask": "smile",
    "AR Pixel Glasses": "smile",
    "Custom Face": "smile",
    # Graphics
    "Motion Composition": "layers",
    "Circle": "circle",
    "Pointing Arrow": "arrow-up-right",
    "Square": "square",
    "Rectangle": "rectangle-horizontal",
    "Timer / Countdown": "timer",
    "Speech Bubble / Quote Card": "message-square",
    "Progress Bar": "progress-bar",
    "Callout Badge": "badge-alert",
    # Zooms
    "Punch Zoom": "zoom-in",
    "Smooth Zoom": "zoom-in",
    "Slow Push-In": "zoom-in",
    "Slow Pull-Out": "zoom-out",
    "Snap Zoom": "zap",
    "Crash Zoom": "zap",
    "Zoom Bounce": "activity",
    "Zoom + Shake": "vibrate",
    "Zoom to Face": "smile",
    "Zoom to Object": "box-select",
    "Zoom to Cursor": "mouse-pointer-2",
    "Zoom to Tracked Region": "scan",
    "Zoom Out Reveal": "zoom-out",
    # Camera Movement
    "Pan Left/Right": "move",
    "Pan Up/Down": "move",
    "Push In": "maximize-2",
    "Pull Out": "zoom-out",
    "Dolly": "camera",
    "Tilt": "sliders-horizontal",
    "Rotation": "rotate-cw",
    "Handheld Movement": "camera",
    "Drift": "move",
    "Follow Subject": "crosshair",
    "Auto-Centre Subject": "crosshair",
    "Ken Burns": "crop",
    "Whip Pan": "zap",
    "Camera Movement Shake": "camera",
    # Shake / Impact
    "Camera Shake": "vibrate",
    "Micro Shake": "activity",
    "Heavy Impact": "zap",
    "Horizontal Shake": "flip-horizontal-2",
    "Vertical Shake": "flip-vertical-2",
    "Rotation Shake": "rotate-cw",
    "Bass Shake": "volume-2",
    "Explosion Shake": "zap",
    "Text Shake": "vibrate",
    "Object Shake": "activity",
    # Transitions
    **TRANSITION_ICONS,
}
MATRICES = {
    "Warm Tone": ((1.08, .025, 0), (0, 1.01, 0), (0, 0, .86)),
    "Cool Tone": ((.88, 0, 0), (0, 1.015, 0), (.025, 0, 1.09)),
    "Sepia": ((.393, .769, .189), (.349, .686, .168), (.272, .534, .131)),
    "Channel Swap": ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
}
ADJUSTABLE = set(MATRICES) | {"Voice Clarity", "Low Cut"}
DESCRIPTIONS = {
    "Object Tracking": "Follow a selected region with censor blur, pixelation, a censor bar, arrows, outlines, labels, an image or a following crop. Analyse locally and refine with correction points.",
    **TRANSITION_DESCRIPTIONS,
    # Visual FX - Zooms
    "Punch Zoom": "Dynamic quick punch-in zoom to emphasize a punchline or moment. Fully adjustable duration, scale, and focal center.",
    "Smooth Zoom": "Smooth cinematic zoom-in with S-curve easing. Ideal for dramatic emphasis and transitions.",
    "Slow Push-In": "Subtle, gradual camera push-in over the clip duration for documentary atmosphere and intensity.",
    "Slow Pull-Out": "Gradual cinematic camera pull-out to slowly reveal the surrounding context.",
    "Snap Zoom": "Ultra-fast snappy zoom to catch viewer attention instantly with cubic deceleration.",
    "Crash Zoom": "Dramatic, aggressive high-speed zoom into the subject, Tarantino-style.",
    "Zoom Bounce": "Elastic zoom that overshoots and settles with a natural physics-based bounce.",
    "Zoom + Shake": "High-impact punch zoom synchronized with a camera rumble shake on arrival.",
    "Zoom to Face": "Targeted zoom framing centered on the upper third or tracked face focal point.",
    "Zoom to Object": "Targeted zoom focusing on a specific quadrant or object of interest in the frame.",
    "Zoom to Cursor": "Smooth zoom targeting a presentation cursor or focal action point.",
    "Zoom to Tracked Region": "Targeted zoom centered on a custom tracked region of the video.",
    "Zoom Out Reveal": "Starts tight on a cropped detail and zooms out smoothly to reveal the full widescreen/vertical shot.",
    # Visual FX - Camera Movement
    "Pan Left/Right": "Smooth virtual camera horizontal slide across the frame with adjustable speed and range.",
    "Pan Up/Down": "Smooth vertical camera tilt/slide up or down to frame content dynamically.",
    "Push In": "Virtual camera movement stepping closer toward the scene with subtle perspective enhancement.",
    "Pull Out": "Virtual camera movement stepping back from the scene.",
    "Dolly": "Simulated physical camera dolly tracking movement across the scene.",
    "Tilt": "Vertical pitch tilt angle adjustment simulating camera gimbal tilt.",
    "Rotation": "Dutch angle roll rotation to tilt the camera horizon dynamically.",
    "Handheld Movement": "Organic natural multi-frequency camera drift simulating human handheld shooting.",
    "Drift": "Subtle ambient slow-floating camera drift to add life to static shots.",
    "Follow Subject": "Virtual camera movement that tracks and follows a focal target across the frame.",
    "Auto-Centre Subject": "Automatically keeps the primary focal subject centered in the 9:16 vertical canvas.",
    "Ken Burns": "Classic documentary pan-and-scan: simultaneous smooth pan and zoom from start to end framing.",
    "Whip Pan": "High-speed rapid camera flick to the side with simulated motion blur displacement.",
    "Camera Movement Shake": "Continuous organic camera wobble simulating walking or running with a camera.",
    # Visual FX - Shake / Impact
    "Camera Shake": "Sudden impact tremor with natural harmonic wobble and exponential decay.",
    "Micro Shake": "Subtle high-frequency micro-jitter adding tension and kinetic energy.",
    "Heavy Impact": "Massive shockwave jolt with rotational twitch and damped recovery for heavy beats and hits.",
    "Horizontal Shake": "Clean directional shudder constrained purely to the horizontal axis.",
    "Vertical Shake": "Powerful directional shudder constrained purely to the vertical axis.",
    "Rotation Shake": "Rotational twitch shake oscillating around the horizon axis.",
    "Bass Shake": "Rhythmic low-frequency rumble shudder tuned for bass drops and music accents.",
    "Explosion Shake": "Violent multi-axis explosion shockwave with initial outward spike and turbulent decay.",
    "Text Shake": "Energetic localized vibration designed to make captions and text pop.",
    "Object Shake": "Localized vibration emphasizing a specific layer element or reaction frame.",
    # Graphics
    "Circle": "A customizable circle overlay. Drag onto a video track to highlight key moments with adjustable line color, thickness, and fill.",
    "Pointing Arrow": "A crisp pointing arrow graphic. Direct viewer attention with customizable direction, length, head size, and color.",
    "Square": "A clean square shape overlay with adjustable border thickness, rounded corners, and fill.",
    "Rectangle": "A versatile rectangle box overlay. Great for framing, highlights, or backdrop cards.",
    "Timer / Countdown": "An animated timer or stopwatch overlay (default 10s). Supports countdown or count-up, custom font, colors, and background card.",
    "Speech Bubble / Quote Card": "An editable quote card or speech bubble callout with customizable tail pointer, colors, and text.",
    "Progress Bar": "A modern video duration progress indicator for short-form clips.",
    "Callout Badge": "A bold, punchy pill badge overlay for 'Wait for it', 'Part 2', or key moments.",
    # Legacy & Other Effects
    "Remove Person Background": "Optional local person segmentation on the current crop. Analyse once; changing the crop requires Re-analyse. Hair and motion edges may need review.",
    "Party Hat": "A colourful hat tracked to the face in the current crop. Hidden when a face is not detected. Requires optional local analysis.",
    "Face Mask": "A stylised mask tracked over the lower face. Hidden when tracking is lost. Requires optional local analysis.",
    "Big Eyes": "Gently magnify the tracked eyes. Hidden when tracking is lost. Requires optional local analysis.",
    "Big Nose": "Magnify the tracked nose with a smoothly blended distortion. Uses the existing optional face analysis.",
    "Big Lips": "Enlarge the mouth with an oval, face-aligned distortion. Hidden when no face is detected.",
    "Face Twist": "Twist the centre of the tracked face, smoothly blending back into the original image at its edges.",
    "Puppy Ears & Nose": "Textured puppy ears and muzzle follow tracked face pose, roll and size; forehead occlusion adds depth. Requires fresh local face analysis.",
    "Cat Ears & Whiskers": "Textured cat ears and whiskers follow tracked face pose, roll and size; forehead occlusion adds depth. Requires fresh local face analysis.",
    "AR Plague Mask": "A textured 3D plague mask and hat follow face yaw, pitch, size and roll. Locally rendered model views make the side of the beak visible on head turns. Requires local face analysis.",
    "AR Pixel Glasses": "3D pixel glasses follow face yaw, pitch, size and roll; their modeled frame and arms are visible as the head turns. Requires local face analysis.",
    "Custom Face": "Locally track this clip's facial mesh, then adjust face, eyes, nose and mouth in a clip-only preview. Optional skin tint preserves source texture. Customize again in this inspector; Cancel keeps the clip unchanged.",
    "Vocal Only": "Optional local download on first use. Separate vocals from this audio clip, save an MP3 and optionally replace its timeline audio. Source video and original files stay unchanged.",
    "Chroma Key": "Make a selected colour transparent. Sample the original clip with the eyedropper; adjust similarity and edge softness.",
    "Green Screen": "Chroma key preset for a bright green (#00ff00) screen. Sample your actual screen for the cleanest result.",
    "Cut curse words": "Recognize common English curse words locally and cut them from this audio clip, leaving gaps. Requires word-timed Whisper recognition; review results.",
    "Remove Silence": "Remove dead air from aligned, linked video and audio clips and pack their retained sections locally. Other clips stay in place.",
    "Gaussian Blur": "Adjustable horizontal and vertical blur with a blend control.",
    "Circle Facecam": "Mask a webcam or reaction layer into a circle.",
    "Black & White": "A crisp monochrome colour preset.",
    "Light Boost": "Lift a dark clip with a gentle contrast and detail boost.",
    "Cinematic Contrast": "Deeper contrast with restrained saturation.",
    "Warm Tone": "Add warm highlights. Adjust strength in the Effects inspector.",
    "Cool Tone": "Cool the image for a blue-toned look. Adjustable strength.",
    "Sepia": "A warm vintage treatment with adjustable strength.",
    "Channel Swap": "Swap red and blue for a stylised reaction or gaming insert.",
    "Text": "A clean, fully editable basic title.",
    "Hook Card": "An animated opening hook with a readable background card.",
    "Caption Pop": "A bold, animated callout near the bottom of the frame.",
    "Lower Third": "An editable name or context label with a dark backing.",
    "Headline": "Bold black text on a fitted white, multi-line social headline. One size control scales the whole card.",
    "Noise Clean": "Reduce steady background noise on this audio clip.",
    "Voice Clarity": "Reduce rumble and lift speech presence. Adjustable strength.",
    "Low Cut": "Reduce low-frequency rumble. Strength sets the cutoff from 60–240 Hz.",
    "Auto Duck": "Project-wide: lower music-role tracks while source speech plays.",
    "Fade In / Out": "Add a quarter-second fade to the selected video or audio clip.",
}
CATEGORY_STYLE = {
    "Visual FX": ("camera", "#8ba2bd"),
    "Video Transitions": ("sparkles", "#5ec2f8"),
    "Graphics": ("shapes", "#62d0ff"),
    "Person / Background": ("smile", "#7ab6a0"),
    "Face Filters": ("sparkles", "#d8ad78"),
    "Keying": ("palette", "#7ab6a0"),
    "Open FX / Blur": ("wand-sparkles", "#a6a0d8"),
    "Transform": ("crop", "#7eafdc"),
    "Tracking": ("crosshair", "#7eafdc"),
    "Colour": ("sparkles", "#d8ad78"),
    "Titles": ("captions", "#d5bd87"),
    "Audio": ("audio-waveform", "#7ab6a0"),
}


def compatible(name, item, project):
    if not item or name in TITLES or name in GRAPHICS or name in TRANSITION_SET or project.track_states.get(item.track, {}).get("locked", False):
        return False
    if name in VISUAL_FX_SET:
        return item.track in project.video_tracks and item.role not in {"title", "graphic"}
    if name in CATALOG['Person / Background']+CATALOG['Face Filters'] and item.role=='background':return False
    if name == "Fade In / Out":
        return item.role not in {"title", "graphic"}
    if name in CATALOG["Audio"]:
        return item.track in project.audio_tracks
    return name in DESCRIPTIONS and item.track in project.video_tracks and item.role not in {"title", "graphic"}


def color_matrix(effect):
    matrix = MATRICES[effect["name"]]
    amount = max(0., min(1., float(effect.get("amount", 100))/100))
    return [[(1-amount if row == col else 0)+amount*matrix[row][col] for col in range(3)] for row in range(3)]


def color_filter(effect):
    matrix = color_matrix(effect)
    return "format=rgba,colorchannelmixer=" + ":".join(
        f"{r}{c}={matrix[ri][ci]:.6f}" for ri,r in enumerate("rgb") for ci,c in enumerate("rgb"))


def apply_color_effect(image, effect):
    from PySide6.QtGui import QImage
    import numpy as np
    rgba=image.convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(rgba.constBits(),dtype=np.uint8).reshape(rgba.height(),rgba.width(),4).copy()
    pixels[:,:,:3]=np.rint(pixels[:,:,:3].astype(np.float32) @ np.array(color_matrix(effect),dtype=np.float32).T).clip(0,255).astype(np.uint8)
    return QImage(pixels.data,rgba.width(),rgba.height(),QImage.Format_RGBA8888).copy()


def preset_owner(item, name):
    return item.transform if name in {"Circle Facecam", "Punch Zoom"} else item


def toggle_preset(item, effect, enabled):
    """Rebuild affected preset properties so bypass/removal also works in stacks."""
    owner=preset_owner(item,effect.get("name"))
    keys=set(effect.get("before", {}))
    for candidate in item.effects:
        if candidate.get("before") and "after" not in candidate:
            target=preset_owner(item,candidate.get("name"))
            candidate["after"]={key:getattr(target,key) for key in candidate["before"]}
    effect["enabled"]=enabled
    for key in keys:
        matching=[e for e in item.effects if key in e.get("before",{}) and preset_owner(item,e.get("name")) is owner]
        value=matching[0]["before"][key]
        for candidate in matching:
            if candidate.get("enabled",True):value=candidate["after"].get(key,value)
        setattr(owner,key,value)
